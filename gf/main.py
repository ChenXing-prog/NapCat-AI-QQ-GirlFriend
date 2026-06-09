"""Main application — AI Girlfriend QQ Bot.

Wires together all components:
- NapCatQQ WebSocket adapter (receives QQ messages)
- Kimi LLM client (generates replies + vision for sticker classification)
- Memory store (user profiles and conversation history)
- Sticker engine (30 categories, position-aware placement)
- Proactive scheduler (morning/evening/silence check-ins)
- FastAPI server (health check + management endpoints)

Start with:
    python -m gf.main
"""

import asyncio
import logging
import re
import time
import random
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
import uvicorn

from .config import load_config, get_config
from .ai.llm import LLMClient
from .ai.persona import build_system_prompt
from .ai.personas import get_persona, list_personas, get_persona_selection_text
from .ai.emotion import EmotionEngine
from .ai.events import EventExtractor, build_followup_context
from .memory.store import MemoryStore
from .stickers.engine import StickerEngine
from .bot.client import QQClient
from .bot.adapter import QQAdapter
from .scheduler import ProactiveScheduler

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("gf")

# ---------------------------------------------------------------------------
# Application components (initialized at startup)
# ---------------------------------------------------------------------------
_qq_client: Optional[QQClient] = None
_qq_adapter: Optional[QQAdapter] = None
_llm: Optional[LLMClient] = None
_memory: Optional[MemoryStore] = None
_stickers: Optional[StickerEngine] = None
_emotion: Optional[EmotionEngine] = None
_events: Optional[EventExtractor] = None

# Track last sticker sent to each user (for ban command)
_last_sticker_sent: dict[str, str] = {}  # user_id -> sticker filename

# Message buffering for adaptive multi-message merging
_message_buffer: dict[str, list[str]] = {}   # user_id -> pending messages
_buffer_tasks: dict[str, asyncio.Task] = {}  # user_id -> flush timer
_last_msg_time: dict[str, float] = {}        # user_id -> last message timestamp

MSG_BUFFER_MIN = 3.0    # Absolute minimum wait
MSG_BUFFER_MAX = 20.0   # Absolute maximum wait
MSG_BUFFER_DEFAULT = 8.0  # Default for new users
MSG_GAP_RESET = 300.0   # Gaps >5min reset the session
MSG_SESSION_WEIGHT = 0.7  # Weight for current session (0.7 = current, 0.3 = history)
MSG_BUFFER_MULTIPLIER = 1.5  # Multiply calculated gap to leave margin


# ---------------------------------------------------------------------------
# Application lifecycle
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background services on startup, clean up on shutdown."""
    global _qq_client, _qq_adapter, _llm, _memory, _stickers, _emotion, _events

    cfg = load_config()
    logger.info(f"Starting {cfg.bot.bot_name} (QQ: {cfg.bot.bot_qq})")

    # Initialize all components
    _llm = LLMClient(cfg.llm)
    _memory = MemoryStore(cfg.data_dir)
    _stickers = StickerEngine(cfg.stickers_dir)
    _qq_client = QQClient(cfg.napcat)
    _emotion = EmotionEngine()
    _events = EventExtractor(_llm)

    # Initialize QQ adapter with message handler
    _qq_adapter = QQAdapter(cfg.napcat, cfg.bot)
    _qq_adapter.on_private_message = handle_private_message
    _qq_adapter.on_friend_add = handle_friend_add

    # Start the WebSocket listener in background
    ws_task = asyncio.create_task(_qq_adapter.start())
    logger.info("WebSocket adapter started")

    # Start the proactive scheduler
    _scheduler = None
    scheduler_task = None
    if cfg.scheduler.enabled:
        _scheduler = ProactiveScheduler(_llm, _memory, _stickers, _qq_client)
        scheduler_task = asyncio.create_task(_scheduler.run())
        logger.info("ProactiveScheduler started")

    yield  # Application runs here

    # Shutdown
    logger.info("Shutting down...")
    if _scheduler:
        _scheduler.stop()
    if scheduler_task:
        scheduler_task.cancel()
    await _qq_adapter.stop()
    await _qq_client.close()
    ws_task.cancel()
    logger.info("Shutdown complete")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="AI Girlfriend QQ Bot",
    version="0.2.0",
    lifespan=lifespan,
)


# ======================================================================
# MESSAGE HANDLER — Phase 3+ pipeline
# ======================================================================

# ======================================================================
# Adaptive message buffering
# ======================================================================

def _calc_wait(user_id: str) -> float:
    """Adaptive buffer wait: current session gaps weighted 70%, history 30%.

    After each message, session gaps are updated. The next timer uses the
    latest calculation. When the user stops sending for `wait` seconds,
    all buffered messages are merged into one reply.
    """
    global _memory
    if _memory is None:
        return MSG_BUFFER_DEFAULT
    prefs = _memory.get_user(user_id).preferences
    session_gaps = prefs.get("msg_session_gaps", [])
    all_gaps = prefs.get("msg_gaps", [])

    # No data at all → default
    if not all_gaps:
        return MSG_BUFFER_DEFAULT

    hist_avg = sum(all_gaps) / len(all_gaps)

    # Current session: 1 gap = use it directly; 2+ = average
    if len(session_gaps) == 1:
        sess_avg = session_gaps[0]
    elif len(session_gaps) >= 2:
        sess_avg = sum(session_gaps) / len(session_gaps)
    else:
        sess_avg = None

    if sess_avg is not None:
        wait = MSG_SESSION_WEIGHT * sess_avg + (1 - MSG_SESSION_WEIGHT) * hist_avg
    else:
        wait = hist_avg  # No session data yet, use history

    # Add buffer margin — wait 1.5x longer than typical gap to avoid cutting user off
    wait = wait * MSG_BUFFER_MULTIPLIER

    return min(MSG_BUFFER_MAX, max(MSG_BUFFER_MIN, wait))


def _is_command(message: str) -> bool:
    """Check if message is a command that should bypass buffering."""
    text = message.strip()
    return _is_ban_command(text) or _is_admin_command(text) or \
           _check_persona_command(text) is not None or \
           text in ("换人设", "选人设", "切换人设")


async def _flush_buffer(user_id: str, delay: float):
    """Wait for buffer timeout, then process all buffered messages."""
    global _message_buffer, _buffer_tasks
    await asyncio.sleep(delay)
    messages = _message_buffer.pop(user_id, [])
    _buffer_tasks.pop(user_id, None)
    if not messages:
        return
    combined = "\n".join(messages)
    logger.info(f"Buffer flush for {user_id}: {len(messages)} msgs after {delay:.1f}s → merged")
    await _real_handle_message(user_id, combined)


async def handle_private_message(user_id: str, message: str):
    """Entry point for incoming QQ messages. Buffers non-command messages."""
    global _memory, _message_buffer, _buffer_tasks, _last_msg_time

    cfg = get_config()

    # Commands: process immediately
    if _is_command(message):
        # Flush any pending buffer first
        if user_id in _message_buffer:
            old_task = _buffer_tasks.pop(user_id, None)
            if old_task:
                old_task.cancel()
            await _flush_buffer(user_id, 0)
        # Process command
        await _handle_command_direct(user_id, message)
        return

    # Record inter-message gap (for adaptive timing)
    now = time.time()
    last_ts = _last_msg_time.get(user_id)
    if last_ts and _memory:
        gap = now - last_ts
        if gap < MSG_GAP_RESET:
            # Same session: record to both session and history
            _memory.record_msg_gap(user_id, gap)
            # Also track session gaps (reset on long pause)
            profile = _memory.get_user(user_id)
            sess = profile.preferences.get("msg_session_gaps", [])
            sess.append(round(gap, 2))
            if len(sess) > 10:
                sess = sess[-10:]
            profile.preferences["msg_session_gaps"] = sess
            _memory.save_user(profile)
        else:
            # Long gap: reset session, flush old buffer
            profile = _memory.get_user(user_id)
            profile.preferences["msg_session_gaps"] = []
            _memory.save_user(profile)
            if user_id in _message_buffer:
                old_task = _buffer_tasks.pop(user_id, None)
                if old_task:
                    old_task.cancel()
                await _flush_buffer(user_id, 0)
    _last_msg_time[user_id] = now

    # Add to buffer
    _message_buffer.setdefault(user_id, []).append(message)

    # Reset timer
    if user_id in _buffer_tasks:
        _buffer_tasks[user_id].cancel()
    wait = _calc_wait(user_id)
    _buffer_tasks[user_id] = asyncio.create_task(_flush_buffer(user_id, wait))
    logger.debug(f"Buffered msg for {user_id}, flush in {wait:.1f}s")


async def _handle_command_direct(user_id: str, message: str):
    """Process a command immediately (bypasses buffer)."""
    global _memory, _qq_client, _stickers, _llm
    cfg = get_config()
    user = _memory.get_user(user_id)

    if _is_ban_command(message):
        await _handle_sticker_ban(user_id)
        return
    if _check_persona_command(message.strip()) is not None:
        persona_cmd = _check_persona_command(message.strip())
        await _handle_persona_selection(user_id, persona_cmd)
        return
    is_admin = bool(cfg.admin_qq) and user_id == cfg.admin_qq
    if is_admin and _is_admin_command(message):
        await _handle_admin_command(user_id, message)
        return


async def _real_handle_message(user_id: str, message: str):
    """Actual message processing pipeline (called after buffer flush)."""
    global _llm, _memory, _stickers, _qq_client, _emotion, _events

    if _llm is None or _memory is None or _stickers is None or _qq_client is None:
        logger.error("Components not initialized")
        return

    cfg = get_config()
    user = _memory.get_user(user_id)

    # ===== Onboarding =====
    if not user.name and not _is_greeting(message):
        name = _extract_name(message)
        if name:
            _memory.update_name(user_id, name)
            user.name = name
        else:
            await _qq_client.send_private_msg(
                user_id,
                f"嗨～我是{cfg.bot.bot_name} 💕\n"
                f"你希望我怎么称呼你呀～"
            )
            _memory.add_message(user_id, "assistant", "询问称呼")
            return

    # ===== Load persona =====
    persona = get_persona(user.persona_id)

    # ===== Emotion analysis =====
    emotion_ctx = ""
    if _emotion:
        emotion_result = _emotion.analyze(message)
        _emotion.update_trajectory(user_id, emotion_result)
        emotion_ctx = _emotion.get_response_guidance(emotion_result)
        traj_ctx = _emotion.get_trajectory_context(user_id)
        if traj_ctx:
            emotion_ctx = traj_ctx + "\n" + emotion_ctx

    # ===== Event extraction =====
    if _events:
        asyncio.create_task(_extract_events_async(user_id, message))

    # ===== Event follow-up context =====
    reminders = _memory.get_due_reminders(user_id)
    event_ctx = build_followup_context(reminders) if reminders else ""

    # ===== Build system prompt =====
    system_prompt = build_system_prompt(
        bot_name=cfg.bot.bot_name,
        user_name=user.name or "主人",
        persona=persona,
        emotion_context=emotion_ctx,
        event_context=event_ctx,
    )

    # ===== Build messages for LLM =====
    llm_messages = [LLMClient.system_message(system_prompt)]
    llm_messages.append(LLMClient.system_message(
        f"[当前时间：{time.strftime('%Y年%m月%d日 %H:%M')}] "
        f"[关系：{user.relationship}] [聊了{user.total_messages}条]"
    ))
    recent = _memory.get_recent_messages(user_id)
    for msg in recent:
        llm_messages.append({"role": msg["role"], "content": msg["content"]})
    llm_messages.append(LLMClient.user_message(message))

    # ===== Call LLM =====
    try:
        parts, _ = await _llm.chat_multi(llm_messages)
    except Exception as e:
        logger.error(f"LLM error for {user_id}: {e}")
        await _qq_client.send_private_msg(user_id, "唔...刚才走神了，你再说一遍好不好～")
        return

    if not parts:
        return

    # ===== Save to memory =====
    _memory.add_message(user_id, "user", message)
    combined = " ||| ".join(
        p.get("content", "") if p["type"] in ("text", "sticker_end") else f"[{p['type']}:{p.get('tag','')}]"
        for p in parts
    )
    _memory.add_message(user_id, "assistant", combined)

    # ===== Send with position-aware logic =====
    banned = _memory.get_banned_stickers(user_id)
    logger.info(f"Reply to {user_id}[{persona.display_name}]: {len(parts)} parts")

    for i, part in enumerate(parts):
        ptype = part.get("type", "text")

        if ptype == "sticker_mid":
            await _send_sticker(part["tag"], user_id, banned)
            await asyncio.sleep(random.uniform(0.6, 1.5))

        elif ptype == "sticker_only":
            await _send_sticker(part["tag"], user_id, banned)
            return  # Pure sticker, no text follows

        elif ptype in ("text", "sticker_end"):
            await asyncio.sleep(random.uniform(0.8, 2.5))
            text = part.get("content", "")
            if text:
                await _qq_client.send_private_msg(user_id, text)

            if ptype == "sticker_end":
                await asyncio.sleep(random.uniform(0.3, 1.0))
                await _send_sticker(part["tag"], user_id, banned)

        logger.debug(f"  [{i+1}/{len(parts)}] {ptype} → {user_id}")


async def _send_sticker(tag: str, user_id: str, banned: set) -> bool:
    """Send a sticker, track it for potential ban. Returns True if sent."""
    global _stickers, _qq_client
    if _stickers is None or _qq_client is None:
        return False

    path = _stickers.pick(tag, banned=banned)
    if path is None:
        return False

    try:
        await _qq_client.send_image(user_id, str(path))
        _last_sticker_sent[user_id] = path.name
        logger.info(f"Sticker [{tag}] → {user_id}: {path.name}")
        return True
    except Exception as e:
        logger.warning(f"Sticker send failed: {e}")
        return False


# ======================================================================
# Commands
# ======================================================================

_STICKER_BAN_PATTERNS = [
    "不喜欢这个表情包", "删掉这个表情包", "不要发这个了",
    "换一个", "这个表情包不好", "拉黑这个表情包",
]


def _is_ban_command(msg: str) -> bool:
    return any(p in msg for p in _STICKER_BAN_PATTERNS)


async def _handle_sticker_ban(user_id: str):
    global _memory, _qq_client
    last = _last_sticker_sent.get(user_id)
    if last:
        _memory.ban_sticker(user_id, last)
        await _qq_client.send_private_msg(user_id, "好哒～以后不发这个给你了 (｡･ω･｡)")
        logger.info(f"User {user_id} banned sticker: {last}")
    else:
        await _qq_client.send_private_msg(user_id, "嗯？你指的是哪个表情包呀～")


def _is_admin_command(msg: str) -> bool:
    admin_cmds = ["添加表情包", "表情包分类", "表情包统计", "删除表情包"]
    return any(c in msg for c in admin_cmds)


async def _handle_admin_command(user_id: str, message: str):
    global _stickers, _qq_client, _llm
    cfg = get_config()

    if "表情包分类" in message:
        cats = _stickers.category_counts()
        lines = [f"📁 表情包分类（{len(cats)}个）："]
        for tag, count in sorted(cats.items(), key=lambda x: -x[1]):
            meta = _stickers.get_meta(tag)
            label = meta.get("label", tag) if meta else tag
            lines.append(f"  [{tag}] {label}: {count}张")
        empty = [t for t in [d.name for d in _stickers.stickers_dir.iterdir()
                             if d.is_dir() and not d.name.startswith("_")]
                 if t not in cats]
        if empty:
            lines.append(f"\n空分类（{len(empty)}个）: {', '.join(empty)}")
        await _qq_client.send_private_msg(user_id, "\n".join(lines))

    elif "表情包统计" in message:
        import collections
        counts = _stickers.category_counts()
        total = sum(counts.values())
        lines = [f"📊 表情包统计：共{total}张，{len(counts)}个分类有图"]
        lines.append(f"Top 5: " + ", ".join(
            f"{t}({c})" for t, c in
            sorted(counts.items(), key=lambda x: -x[1])[:5]
        ))
        await _qq_client.send_private_msg(user_id, "\n".join(lines))

    elif "删除表情包" in message:
        last = _last_sticker_sent.get("admin_last")
        if last:
            import os
            # Find and delete the file
            for tag in _stickers.list_categories():
                folder = _stickers.stickers_dir / tag
                target = folder / last
                if target.exists():
                    target.unlink()
                    _stickers.refresh()
                    await _qq_client.send_private_msg(user_id, f"已删除 [{tag}] {last}")
                    return
        await _qq_client.send_private_msg(user_id, "没有找到要删除的表情包")

    elif "添加表情包" in message:
        # This is triggered after admin sends an image
        # For now, the image would be sent as a separate message
        # We handle it below in _handle_admin_image
        await _qq_client.send_private_msg(
            user_id,
            "请发送图片，然后发指令「分类到 {标签}」（如：分类到 cute）"
        )


async def handle_admin_image(user_id: str, file_path: str, file_name: str):
    """Called when admin sends an image — auto-classify with Kimi Vision.

    This function is triggered by the QQ adapter when an admin sends
    an image. It uses Kimi Vision API to classify the image, then
    saves it to the correct sticker category folder.
    """
    global _stickers, _qq_client
    cfg = get_config()

    if not cfg.admin_qq or user_id != cfg.admin_qq:
        return

    # Use Kimi Vision to classify
    from .ai.sticker_meta import get_all_tags

    try:
        import base64, io, httpx
        from PIL import Image

        img = Image.open(file_path)
        if img.width > 800:
            ratio = 800 / img.width
            img = img.resize((800, int(img.height * ratio)), Image.LANCZOS)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        b64 = base64.b64encode(buf.getvalue()).decode()

        tags_str = ", ".join(get_all_tags())
        resp = await httpx.AsyncClient(timeout=60).post(
            f"{cfg.llm.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {cfg.llm.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": cfg.llm.vision_model,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        {"type": "text", "text": f"请判断这张表情包的情绪分类。可选：{tags_str}。只输出JSON：{{\"tag\":\"xxx\",\"description\":\"描述\"}}"},
                    ],
                }],
                "temperature": 0.3,
                "max_tokens": 80,
            },
        )
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        if "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            if content.startswith("json"):
                content = content[4:].strip()
        result = __import__("json").loads(content)
        tag = result.get("tag", "").strip().lower()
        desc = result.get("description", "")

        if tag not in get_all_tags():
            await _qq_client.send_private_msg(user_id, f"分类失败，未知标签: {tag}")
            return

        # Save to stickers/{tag}/
        folder = _stickers.stickers_dir / tag
        folder.mkdir(exist_ok=True)
        existing = [f for f in folder.iterdir() if f.is_file()]
        next_num = len(existing) + 1
        ext = Path(file_name).suffix.lower() or ".jpg"
        new_path = folder / f"{next_num}{ext}"
        shutil.copy(file_path, str(new_path))
        _stickers.refresh()

        await _qq_client.send_private_msg(
            user_id,
            f"✅ 已添加到 [{tag}] = {desc} → {tag}/{next_num}{ext}"
        )
        logger.info(f"Admin added sticker: {tag}/{next_num}{ext} ({desc})")

    except Exception as e:
        logger.error(f"Admin sticker classification failed: {e}")
        await _qq_client.send_private_msg(user_id, f"添加失败: {e}")


async def handle_friend_add(user_id: str):
    """Handle a new friend being added."""
    global _qq_client, _memory
    if _qq_client is None or _memory is None:
        return
    cfg = get_config()
    try:
        info = await _qq_client.get_stranger_info(user_id)
        nickname = info.get("nickname", "新朋友")
    except Exception:
        nickname = "新朋友"

    welcome = (
        f"嗨～{nickname}！我是{cfg.bot.bot_name} 💕\n"
        f"以后就让我来陪你聊天吧～\n"
        f"首先，你希望我怎么称呼你呀？\n\n"
        f"(设置名字后发「换人设」可以选我的人设哦～"
        f"温柔女友/傲娇青梅/元气学妹/御姐前辈/二次元同好)"
    )
    await _qq_client.send_private_msg(user_id, welcome)
    _memory.add_message(user_id, "assistant", welcome)
    logger.info(f"Welcomed new friend: {user_id}")


# ======================================================================
# Helpers
# ======================================================================

def _is_greeting(text: str) -> bool:
    g = {"你好", "嗨", "hi", "hello", "在吗", "在不在", "哈喽", "早", "嗨嗨"}
    return text.strip().lower() in g


def _extract_name(text: str) -> Optional[str]:
    for pat in [r"我叫(.+?)(?:[，。,\.\s]|$)", r"我是(.+?)(?:[，。,\.\s]|$)",
                r"叫我(.+?)(?:[，。,\.\s]|$)", r"称呼我(.+?)(?:[，。,\.\s]|$)"]:
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()[:10]
    return None


def _check_persona_command(message: str) -> Optional[str]:
    text = message.strip()
    m = {"1": "gentle", "2": "tsundere", "3": "genki", "4": "oneesan", "5": "otaku"}
    if text in m:
        return m[text]
    n = {"温柔女友": "gentle", "温柔": "gentle", "傲娇青梅": "tsundere", "傲娇": "tsundere",
         "元气学妹": "genki", "元气": "genki", "御姐前辈": "oneesan", "御姐": "oneesan",
         "二次元同好": "otaku", "同好": "otaku", "换人设": None}
    if text in n:
        return n[text]
    if "换人设" in text or "选人设" in text:
        return None  # Return None triggers persona selection list
    for label, pid in n.items():
        if pid and (f"我要{label}" in text or f"选{label}" in text):
            return pid
    return None


async def _handle_persona_selection(user_id: str, persona_id: Optional[str]):
    global _memory, _qq_client
    if persona_id is None:
        await _qq_client.send_private_msg(user_id, get_persona_selection_text())
        return
    persona = get_persona(persona_id)
    _memory.set_persona(user_id, persona_id)
    _memory.add_message(user_id, "user", f"选择人设：{persona.display_name}")
    await _qq_client.send_private_msg(
        user_id,
        f"好呀～以后我就是你的**{persona.display_name}**「{persona.name}」啦！\n\n"
        f"{persona.tagline}\n\n你可以随时说「换人设」来重新选择哦～"
    )
    _memory.add_message(user_id, "assistant", f"已切换人设到{persona.display_name}")


async def _extract_events_async(user_id: str, message: str):
    global _events, _memory
    if _events is None or _memory is None:
        return
    try:
        extracted = await _events.extract(message)
        for evt in extracted:
            _memory.add_event(
                user_id=user_id, event=evt.event,
                event_type=evt.type, remind_in_hours=evt.remind_in_hours,
                extracted_at=evt.extracted_at,
            )
            if evt.remind_in_hours > 0:
                logger.info(f"Event recorded for {user_id}: [{evt.type}] {evt.event}")
    except Exception as e:
        logger.debug(f"Event extraction skipped: {e}")


# ======================================================================
# API routes
# ======================================================================

@app.post("/napcat/event")
async def napcat_event(request: Request):
    """Receive events from NapCatQQ via HTTP POST (fallback)."""
    try:
        data = await request.json()
    except Exception:
        return {"status": "bad_request"}

    post_type = data.get("post_type")
    if post_type == "message":
        msg_type = data.get("message_type")
        user_id = str(data.get("user_id", ""))
        raw_message = data.get("raw_message", data.get("message", ""))
        if msg_type == "private" and user_id != get_config().bot.bot_qq:
            await handle_private_message(user_id, raw_message)
    elif post_type == "notice" and data.get("notice_type") == "friend_add":
        await handle_friend_add(str(data.get("user_id", "")))

    return {"status": "ok"}


@app.get("/health")
async def health():
    cfg = get_config()
    return {"status": "ok", "bot": cfg.bot.bot_name, "qq": cfg.bot.bot_qq}


@app.get("/users")
async def list_users():
    global _memory
    if _memory is None:
        return {"error": "Memory not initialized"}
    users = []
    for f in sorted(_memory.users_dir.glob("*.json")):
        try:
            u = _memory.get_user(f.stem)
            users.append({
                "user_id": u.user_id, "name": u.name,
                "persona": u.persona_id, "relationship": u.relationship,
                "total_messages": u.total_messages,
                "banned_stickers": len(u.banned_stickers),
            })
        except Exception:
            pass
    return {"users": users, "total": len(users)}


@app.get("/stickers")
async def list_stickers():
    global _stickers
    if _stickers is None:
        return {"error": "Sticker engine not initialized"}
    return {"categories": _stickers.category_counts()}


# ======================================================================
# Entry point
# ======================================================================

def main():
    cfg = load_config()
    logger.info(f"Starting {cfg.bot.bot_name} on {cfg.server.host}:{cfg.server.port}")
    uvicorn.run("gf.main:app", host=cfg.server.host, port=cfg.server.port, log_level="info")


if __name__ == "__main__":
    main()
