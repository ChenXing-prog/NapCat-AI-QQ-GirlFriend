"""Proactive messaging scheduler.

Phase 2: Manages morning/evening greetings, silence detection,
and context-aware proactive check-ins.

Architecture:
    - Runs as a background asyncio task alongside the main bot
    - Every 60s, scans all users for scheduled actions
    - Uses the same LLM + memory system as the chat handler
    - Each user has independent clinginess settings and rate limits
"""

import asyncio
import logging
import random
import time
from datetime import datetime, date
from typing import Optional

from .config import get_config
from .ai.llm import LLMClient
from .ai.persona import build_proactive_prompt
from .ai.personas import get_persona
from .ai.events import build_followup_context
from .memory.store import MemoryStore
from .bot.client import QQClient
from .stickers.engine import StickerEngine

logger = logging.getLogger("gf.scheduler")

# ---------------------------------------------------------------------------
# Clinginess presets
# ---------------------------------------------------------------------------
CLINGINESS_PRESETS = {
    "clingy": {
        "label": "黏人",
        "silence_hours": 2,     # Check after 2h of silence
        "max_per_day": 5,       # Up to 5 proactive messages/day
    },
    "normal": {
        "label": "正常",
        "silence_hours": 5,
        "max_per_day": 3,
    },
    "chill": {
        "label": "佛系",
        "silence_hours": 8,
        "max_per_day": 1,
    },
}

# Default morning/evening windows (local time)
DEFAULT_MORNING_START = 7   # 7:00
DEFAULT_MORNING_END = 10    # 10:00
DEFAULT_EVENING_START = 21  # 21:00
DEFAULT_EVENING_END = 0     # 00:00 (midnight)

# Window jitter: random +/- minutes to make it feel natural
TIME_JITTER_MINUTES = 15


class ProactiveScheduler:
    """Background scheduler for proactive messages.

    Usage:
        scheduler = ProactiveScheduler(llm, memory, stickers, qq_client)
        task = asyncio.create_task(scheduler.run())

    Call scheduler.stop() to cleanly shut down.
    """

    def __init__(
        self,
        llm: LLMClient,
        memory: MemoryStore,
        stickers: StickerEngine,
        qq_client: QQClient,
    ):
        self._llm = llm
        self._memory = memory
        self._stickers = stickers
        self._qq = qq_client
        self._running = False
        self._check_interval = 60  # seconds

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def run(self):
        """Main scheduler loop. Runs every 60 seconds."""
        self._running = True
        logger.info(
            "ProactiveScheduler started "
            f"(interval={self._check_interval}s)"
        )

        # Wait 10s after startup before first check
        await asyncio.sleep(10)

        while self._running:
            try:
                await self._tick()
            except Exception as e:
                logger.error(f"Scheduler tick error: {e}")

            await asyncio.sleep(self._check_interval)

    def stop(self):
        """Signal the scheduler to stop."""
        self._running = False
        logger.info("ProactiveScheduler stopped")

    # ------------------------------------------------------------------
    # Core tick
    # ------------------------------------------------------------------

    async def _tick(self):
        """One scheduler cycle: scan all users, check triggers."""
        user_ids = self._get_all_user_ids()
        if not user_ids:
            return

        now = time.time()
        now_dt = datetime.now()

        for user_id in user_ids:
            try:
                await self._check_user(user_id, now, now_dt)
            except Exception as e:
                logger.warning(f"Scheduler error for user {user_id}: {e}")

    async def _check_user(self, user_id: str, now: float, now_dt: datetime):
        """Check all triggers for a single user."""
        user = self._memory.get_user(user_id)

        # Skip users who haven't set their name (not onboarded yet)
        if not user.name:
            return

        prefs = user.preferences
        clinginess = prefs.get("clinginess", "normal")
        preset = CLINGINESS_PRESETS.get(clinginess, CLINGINESS_PRESETS["normal"])

        # Reset daily counter if it's a new day
        today_str = now_dt.strftime("%Y-%m-%d")
        if prefs.get("proactive_date") != today_str:
            prefs["proactive_date"] = today_str
            prefs["proactive_count_today"] = 0

        count_today = prefs.get("proactive_count_today", 0)
        max_today = preset["max_per_day"]

        # Don't exceed daily limit
        if count_today >= max_today:
            return

        # Check each trigger type
        triggered = False
        trigger_type = ""

        # 1. Morning greeting
        if self._is_morning_time(now_dt) and not self._already_sent_today(prefs, "morning"):
            triggered = True
            trigger_type = "morning"

        # 2. Evening greeting
        elif self._is_evening_time(now_dt) and not self._already_sent_today(prefs, "evening"):
            triggered = True
            trigger_type = "evening"

        # 3. Daily random share (2-3/day during active hours)
        if not triggered and self._should_share_now(now_dt, user, now, prefs):
            await self._send_share(user_id)
            prefs["last_share"] = now
            user.preferences = prefs
            self._memory.save_user(user)
            return

        # 4. Silence detection — 50% share instead of check-in
        if not triggered and self._is_silent(user, now, preset["silence_hours"]) \
                and self._cooldown_ok(prefs, now, min_interval_hours=1):
            if random.random() < 0.5:
                await self._send_share(user_id)
                prefs["last_proactive"] = now
                prefs["proactive_count_today"] = count_today + 1
                user.preferences = prefs
                self._memory.save_user(user)
                return
            else:
                triggered = True
                trigger_type = "silence"

        if not triggered:
            return

        # Generate and send proactive message
        await self._send_proactive(user_id, trigger_type, now)

        # Update state
        prefs["last_proactive"] = now
        prefs["proactive_count_today"] = count_today + 1
        if trigger_type in ("morning", "evening"):
            prefs[f"{trigger_type}_sent_date"] = today_str
        user.preferences = prefs
        self._memory.save_user(user)

        logger.info(
            f"Proactive [{trigger_type}] → {user_id} "
            f"(count: {count_today + 1}/{max_today})"
        )

    # ------------------------------------------------------------------
    # Trigger checks
    # ------------------------------------------------------------------

    def _is_morning_time(self, dt: datetime) -> bool:
        """Check if current time is within morning greeting window."""
        hour = dt.hour
        return DEFAULT_MORNING_START <= hour < DEFAULT_MORNING_END

    def _is_evening_time(self, dt: datetime) -> bool:
        """Check if current time is within evening greeting window."""
        hour = dt.hour
        # 21:00 to midnight
        return hour >= DEFAULT_EVENING_START or hour < DEFAULT_EVENING_END

    def _already_sent_today(self, prefs: dict, trigger_type: str) -> bool:
        """Check if a timed greeting was already sent today."""
        today = date.today().isoformat()
        return prefs.get(f"{trigger_type}_sent_date") == today

    def _is_silent(self, user, now: float, silence_hours: int) -> bool:
        """Check if the user has been silent for too long."""
        if not user.recent_messages:
            return False

        last_msg = user.recent_messages[-1]
        last_time = last_msg.get("time", 0)
        hours_since = (now - last_time) / 3600

        return hours_since >= silence_hours

    def _cooldown_ok(self, prefs: dict, now: float, min_interval_hours: int = 1) -> bool:
        """Ensure we don't spam — at least min_interval_hours between proactive messages."""
        last = prefs.get("last_proactive", 0)
        return (now - last) / 3600 >= min_interval_hours

    def _should_share_now(self, dt: datetime, user, now: float, prefs: dict) -> bool:
        """Check if it's a good time for a random daily share."""
        hour = dt.hour
        # Active hours only (9-23), skip morning/evening window edges
        if hour < 9 or hour >= 23:
            return False
        # Skip if user was active in last 2h
        if user.recent_messages:
            last_msg = user.recent_messages[-1]
            hours_since = (now - last_msg.get("time", 0)) / 3600
            if hours_since < 2:
                return False
        # At least 3h since last share
        last_share = prefs.get("last_share", 0)
        if (now - last_share) / 3600 < 3:
            return False
        # Max 3 per day
        today = date.today().isoformat()
        share_count = prefs.get("share_count_today", 0)
        if share_count >= 3:
            return False
        # Random chance to actually send (avoid all users triggering at once)
        if random.random() > 0.3:
            return False
        prefs["share_count_today"] = share_count + 1
        return True

    async def _send_share(self, user_id: str):
        """Generate and send a daily share using LLM with full memory context."""
        from .ai.persona import build_share_prompt
        from .ai.personas import get_persona
        user = self._memory.get_user(user_id)
        persona = get_persona(user.persona_id)
        if user.recent_messages:
            last_time = user.recent_messages[-1].get("time", 0)
            hours_silent = (time.time() - last_time) / 3600
        else:
            hours_silent = 24
        # Collect memory context
        facts = [f["content"] for f in self._memory.get_context_facts(user_id, limit=6)]
        summaries = [s["summary"] for s in self._memory.get_context_summaries(user_id, limit=2)]
        emotions = [f"{e['date'][-5:]}({e.get('note','')})" for e in self._memory.get_emotion_trajectory(user_id, 3)]
        # Archive/moment hint
        archive = self._memory.search_archive(user_id, limit=1)
        archive_hint = ""
        if archive:
            a = archive[0]
            ts = time.strftime("%m月%d日", time.localtime(a.get("created_at", time.time())))
            archive_hint = f"{ts}，他说过'{a['content'][:60]}'"
        moment = self._memory.get_random_moment(user_id)
        moment_hint = moment["content"] if moment else ""
        prompt = build_share_prompt(
            self._memory.get_user(user_id).name or user_id, user.name or "主人",
            persona, hours_silent, facts, summaries, emotions, archive_hint, moment_hint,
        )
        try:
            reply, sticker_tag = await self._llm.chat([
                self._llm.system_message(prompt),
                self._llm.user_message("[系统：现在主动给ta发一条消息]"),
            ])
        except Exception as e:
            logger.error(f"Share generation error: {e}")
            return
        if not reply:
            return
        await self._qq.send_private_msg(user_id, reply)
        self._memory.add_message(user_id, "assistant", reply)
        if sticker_tag:
            path = self._stickers.pick(sticker_tag)
            if path:
                await asyncio.sleep(1.0)
                try:
                    await self._qq.send_image(user_id, str(path))
                except Exception:
                    pass
        logger.info(f"Daily share sent to {user_id}: {reply[:60]}...")

    # ------------------------------------------------------------------
    # Proactive message generation & sending
    # ------------------------------------------------------------------

    async def _send_proactive(self, user_id: str, trigger_type: str, now: float):
        """Generate a persona-aware proactive message and send it."""
        user = self._memory.get_user(user_id)
        persona = get_persona(user.persona_id)
        days_known = max(1, int((time.time() - user.first_chat) / 86400))

        # Build event context
        reminders = self._memory.get_due_reminders(user_id)
        event_context = build_followup_context(reminders) if reminders else ""
        events_text = "\n".join(
            f"- {e['event']}" for e in user.events[-3:]
        ) if user.events else ""

        # Build persona-aware proactive prompt
        system_prompt = build_proactive_prompt(
            user_name=user.name or "主人",
            persona=persona,
            trigger_type=trigger_type,
            days_known=days_known,
            relationship=user.relationship,
            events_text=events_text,
            emotion_context=event_context,
        )

        # Get recent conversation for context
        recent = self._memory.get_recent_messages(user_id, count=6)
        llm_messages = [LLMClient.system_message(system_prompt)]

        for msg in recent:
            llm_messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

        llm_messages.append(LLMClient.user_message(
            f"[系统指令：现在{trigger_type}，请主动给{user.name}发一条消息]"
        ))

        try:
            reply, sticker_tag = await self._llm.chat(llm_messages)
        except Exception as e:
            logger.error(f"LLM error during proactive [{trigger_type}] for {user_id}: {e}")
            return

        if not reply:
            return

        # Simulate a short thinking delay
        delay = random.uniform(1.5, 3.5)
        await asyncio.sleep(delay)

        # Send the message
        await self._qq.send_private_msg(user_id, reply)
        self._memory.add_message(user_id, "assistant", reply)

        # Send sticker if tagged
        if sticker_tag:
            sticker_path = self._stickers.pick(sticker_tag)
            if sticker_path:
                await asyncio.sleep(1.0)
                try:
                    await self._qq.send_image(user_id, str(sticker_path))
                except Exception as e:
                    logger.warning(f"Sticker send failed: {e}")

        logger.info(
            f"Proactive sent [{trigger_type}] to {user_id}"
            f"[{persona.display_name}]: {reply[:60]}..."
        )

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def _get_all_user_ids(self) -> list[str]:
        """Get all user IDs from the data directory."""
        ids = []
        for f in self._memory.users_dir.glob("*.json"):
            ids.append(f.stem)
        return ids
