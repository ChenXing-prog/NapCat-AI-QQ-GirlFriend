"""Main application — QQ AI Girlfriend Bot.

Wires together all components into a FastAPI server with WebSocket
event handling, adaptive message buffering, and confide mode.
"""

import asyncio
import logging
import re
import time
import random
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
import uvicorn

from .config import load_config, get_config
from .ai.llm import LLMClient
from .ai.persona import build_system_prompt, build_confide_prompt
from .ai.personas import get_persona
from .ai.emotion import EmotionEngine
from .ai.events import EventExtractor, build_followup_context
from .ai.memory import MemoryManager
from .ai.search import maybe_search
from .memory.store import MemoryStore
from .stickers.engine import StickerEngine
from .bot.client import QQClient
from .bot.adapter import QQAdapter
from .scheduler import ProactiveScheduler
from .handlers.commands import (
    is_ban_command, handle_ban, is_admin_command, handle_admin_cmd,
    classify_and_add, check_persona_cmd, handle_persona, is_any_command,
)
from .handlers.buffer import (
    handle_incoming, calc_wait, flush_buffer,
    confide_start, confide_end, confide_collect, is_confide,
)

# ---------------------------------------------------------------------------
logger = logging.getLogger("gf")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

# ------------------------------------------------------------------ Components
_llm: Optional[LLMClient] = None
_memory: Optional[MemoryStore] = None
_stickers: Optional[StickerEngine] = None
_qq_client: Optional[QQClient] = None
_qq_adapter: Optional[QQAdapter] = None
_emotion: Optional[EmotionEngine] = None
_events: Optional[EventExtractor] = None
_mem_mgr: Optional[MemoryManager] = None
_last_sticker_sent: dict[str, str] = {}

# ----------------------------------------------------------------- Lifecycle
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _qq_client, _qq_adapter, _llm, _memory, _stickers, _emotion, _events, _mem_mgr
    cfg = load_config()
    logger.info(f"Starting {cfg.bot.bot_name} (QQ: {cfg.bot.bot_qq})")
    _llm = LLMClient(cfg.llm)
    _memory = MemoryStore(cfg.data_dir)
    _stickers = StickerEngine(cfg.stickers_dir)
    _qq_client = QQClient(cfg.napcat)
    _emotion = EmotionEngine()
    _events = EventExtractor(_llm)
    _mem_mgr = MemoryManager(_llm)
    _qq_adapter = QQAdapter(cfg.napcat, cfg.bot)
    _qq_adapter.on_private_message = handle_private_message
    _qq_adapter.on_friend_add = handle_friend_add
    ws_task = asyncio.create_task(_qq_adapter.start())
    logger.info("WebSocket adapter started")
    _scheduler = None; sched_task = None
    if cfg.scheduler.enabled:
        _scheduler = ProactiveScheduler(_llm, _memory, _stickers, _qq_client)
        sched_task = asyncio.create_task(_scheduler.run())
        logger.info("ProactiveScheduler started")
    yield
    logger.info("Shutting down...")
    if _scheduler: _scheduler.stop()
    if sched_task: sched_task.cancel()
    await _qq_adapter.stop(); await _qq_client.close(); ws_task.cancel()
    logger.info("Shutdown complete")

app = FastAPI(title="AI Girlfriend QQ Bot", version="0.3.0", lifespan=lifespan)

# ================================================================== Entry point
async def handle_private_message(user_id: str, message: str):
    """Route incoming QQ messages: commands → immediate, confide → collect, chat → buffer."""
    cfg = get_config()

    # Commands
    if is_any_command(message):
        await _handle_command_direct(user_id, message)
        return

    # Confide mode: standalone "/" delimiters
    if message.strip() == "/":
        if is_confide(user_id):
            combined = confide_end(user_id)
            if combined.strip():
                await _handle_confide_reply(user_id, combined)
            else:
                await _qq_client.send_private_msg(user_id, "嗯？你还没说什么呢 (｡･ω･｡)")
        else:
            confide_start(user_id)
            logger.info(f"Confide mode ON for {user_id}")
        return

    # In confide mode, just collect
    if is_confide(user_id):
        confide_collect(user_id, message)
        return

    # Normal chat: buffer
    handle_incoming(user_id, message, _memory, _real_handle_message)


async def _handle_command_direct(user_id: str, message: str):
    """Process commands immediately (bypass buffer)."""
    cfg = get_config()
    user = _memory.get_user(user_id)

    if is_ban_command(message):
        await handle_ban(user_id, _last_sticker_sent, _memory, _qq_client)
        return

    persona_cmd = check_persona_cmd(message.strip())
    if persona_cmd is not None:
        await handle_persona(user_id, persona_cmd, _memory, _qq_client)
        return

    is_admin = bool(cfg.admin_qq) and user_id == cfg.admin_qq
    if is_admin and is_admin_command(message):
        await handle_admin_cmd(user_id, message, _stickers, _qq_client, cfg, _last_sticker_sent)
        return


async def _handle_confide_reply(user_id: str, combined: str):
    """Confide mode: deeper, fewer splits, richer emotion, still using persona."""
    global _llm, _memory
    cfg = get_config()
    user = _memory.get_user(user_id)
    persona = get_persona(user.persona_id)
    prompt = build_confide_prompt(cfg.bot.bot_name, user.name or "主人", persona)
    logger.info(f"Confide flush for {user_id}: {len(combined)} chars")
    try:
        parts, _ = await _llm.chat_multi([
            LLMClient.system_message(prompt),
            LLMClient.user_message(combined),
        ], max_tokens=cfg.llm.confide_max_tokens)
    except Exception as e:
        logger.error(f"Confide LLM error: {e}")
        await _qq_client.send_private_msg(user_id, "唔...刚才走神了，你再说一遍好不好～")
        return
    _memory.add_message(user_id, "user", combined)
    combined_text = " ||| ".join(p.get("content", "") for p in parts if p.get("type") in ("text", "sticker_end"))
    _memory.add_message(user_id, "assistant", combined_text)
    banned = _memory.get_banned_stickers(user_id)
    for i, part in enumerate(parts):
        ptype = part.get("type", "text")
        if ptype == "sticker_mid":
            await _send_sticker(part["tag"], user_id, banned)
            await asyncio.sleep(random.uniform(0.6, 1.5))
        elif ptype == "sticker_only":
            await _send_sticker(part["tag"], user_id, banned)
            return
        elif ptype in ("text", "sticker_end"):
            await asyncio.sleep(random.uniform(0.8, 2.5))
            text = part.get("content", "")
            if text:
                await _qq_client.send_private_msg(user_id, text)
            if ptype == "sticker_end":
                await asyncio.sleep(random.uniform(0.3, 1.0))
                await _send_sticker(part["tag"], user_id, banned)


async def _real_handle_message(user_id: str, message: str):
    """Normal chat pipeline."""
    global _llm, _memory, _stickers, _qq_client, _emotion, _events
    if None in (_llm, _memory, _stickers, _qq_client):
        logger.error("Components not initialized"); return
    cfg = get_config()
    user = _memory.get_user(user_id)
    # Onboarding
    if not user.name and not _is_greeting(message):
        name = _extract_name(message)
        if name: _memory.update_name(user_id, name); user.name = name
        else:
            await _qq_client.send_private_msg(user_id, f"嗨～我是{cfg.bot.bot_name} 💕\n你希望我怎么称呼你呀～")
            _memory.add_message(user_id, "assistant", "询问称呼"); return
    persona = get_persona(user.persona_id)
    # Emotion
    emotion_ctx = ""
    if _emotion:
        er = _emotion.analyze(message); _emotion.update_trajectory(user_id, er)
        emotion_ctx = _emotion.get_response_guidance(er)
        tc = _emotion.get_trajectory_context(user_id)
        if tc: emotion_ctx = tc + "\n" + emotion_ctx
    # Events
    if _events: asyncio.create_task(_extract_events(user_id, message))
    reminders = _memory.get_due_reminders(user_id)
    event_ctx = build_followup_context(reminders) if reminders else ""
    # Web search (with recent conversation context for better queries)
    recent_msgs = [m["content"] for m in _memory.get_recent_messages(user_id, 6)]
    search_ctx = await maybe_search(message, recent_msgs)
    if search_ctx:
        logger.info(f"Search results injected for {user_id}")

    # Prompt + LLM with long-term memory
    prompt = build_system_prompt(cfg.bot.bot_name, user.name or "主人", persona=persona, emotion_context=emotion_ctx, event_context=event_ctx)
    llm_msgs = [LLMClient.system_message(prompt)]
    # Web search results (injected before memory)
    if search_ctx:
        llm_msgs.append(LLMClient.system_message(search_ctx))
    # Tier 2: Core Facts
    facts = _memory.get_context_facts(user_id)
    if facts:
        fact_text = "关于" + (user.name or "对方") + "你记得这些：\n" + "\n".join(f"- {f['content']}" for f in facts)
        llm_msgs.append(LLMClient.system_message(fact_text))
    # Tier 3: Summaries
    summaries = _memory.get_context_summaries(user_id)
    if summaries:
        sum_text = "最近的对话概要：\n" + "\n".join(f"- [{s['date_range']}] {s['summary']}" for s in summaries)
        llm_msgs.append(LLMClient.system_message(sum_text))
    # Emotion trajectory (last 7 days)
    emotions = _memory.get_emotion_trajectory(user_id, 7)
    if len(emotions) >= 2:
        trend = "在好转" if emotions[-1].get("dominant","") not in ("sad","anxious","angry") else "需要注意"
        emo_text = "最近心情：" + " → ".join(f"{e['date'][-5:]}({e.get('note','')})" for e in emotions) + f"，整体{trend}"
        llm_msgs.append(LLMClient.system_message(emo_text))
    # Shared moment (20% chance, natural recall)
    if random.random() < 0.2:
        moment = _memory.get_random_moment(user_id)
        if moment:
            llm_msgs.append(LLMClient.system_message(
                f"[可以自然地提起：{moment['content']}。不要刻意，顺势说一下就好。]"))
    weekdays = ["周一","周二","周三","周四","周五","周六","周日"]
    now = time.localtime()
    time_note = f"[{time.strftime('%Y年%m月%d日', now)} {weekdays[now.tm_wday]} {time.strftime('%H:%M', now)}]"
    llm_msgs.append(LLMClient.system_message(f"{time_note} [关系:{user.relationship}] [聊了{user.total_messages}条]"))
    for m in _memory.get_recent_messages(user_id): llm_msgs.append({"role": m["role"], "content": m["content"]})
    llm_msgs.append(LLMClient.user_message(message))
    # Background: extract facts & summarize (fire-and-forget)
    asyncio.create_task(_run_memory_tasks(user_id))
    try:
        parts, _ = await _llm.chat_multi(llm_msgs)
    except Exception as e:
        logger.error(f"LLM error: {e}"); await _qq_client.send_private_msg(user_id, "唔...走神了，再说一遍好不好～"); return
    if not parts: return
    _memory.add_message(user_id, "user", message)
    combined = " ||| ".join(p.get("content", "") if p["type"] in ("text", "sticker_end") else f"[{p['type']}:{p.get('tag','')}]" for p in parts)
    _memory.add_message(user_id, "assistant", combined)
    banned = _memory.get_banned_stickers(user_id)
    logger.info(f"Reply to {user_id}[{persona.display_name}]: {len(parts)} parts")
    for i, part in enumerate(parts):
        ptype = part.get("type", "text")
        if ptype == "sticker_mid": await _send_sticker(part["tag"], user_id, banned); await asyncio.sleep(random.uniform(0.6, 1.5))
        elif ptype == "sticker_only": await _send_sticker(part["tag"], user_id, banned); return
        elif ptype in ("text", "sticker_end"):
            await asyncio.sleep(random.uniform(0.8, 2.5))
            text = part.get("content", "")
            if text: await _qq_client.send_private_msg(user_id, text)
            if ptype == "sticker_end": await asyncio.sleep(random.uniform(0.3, 1.0)); await _send_sticker(part["tag"], user_id, banned)

async def _send_sticker(tag: str, user_id: str, banned: set) -> bool:
    global _stickers, _qq_client
    if not _stickers or not _qq_client: return False
    path = _stickers.pick(tag, banned=banned)
    if not path: return False
    try:
        await _qq_client.send_image(user_id, str(path))
        _last_sticker_sent[user_id] = path.name
        logger.info(f"Sticker [{tag}] → {user_id}: {path.name}"); return True
    except Exception as e: logger.warning(f"Sticker failed: {e}"); return False

# ------------------------------------------------------------------ Helpers
def _is_greeting(t): return t.strip().lower() in {"你好","嗨","hi","hello","在吗","哈喽","早"}

def _extract_name(text):
    for p in [r"我叫(.+?)(?:[，。,\s]|$)",r"我是(.+?)(?:[，。,\s]|$)",r"叫我(.+?)(?:[，。,\s]|$)",r"称呼我(.+?)(?:[，。,\s]|$)"]:
        m = re.search(p, text)
        if m: return m.group(1).strip()[:10]
    return None

async def _run_memory_tasks(user_id: str):
    """Background: extract facts, summarize, log emotions, capture moments."""
    global _memory, _mem_mgr, _emotion
    if not _memory or not _mem_mgr:
        return
    try:
        recent = _memory.get_recent_messages(user_id, 40)
        facts = await _mem_mgr.maybe_extract_facts(user_id, recent)
        if facts:
            _memory.add_facts(user_id, facts)
        summary = await _mem_mgr.maybe_summarize(user_id, recent, _memory.get_context_summaries(user_id, 10))
        if summary:
            total_msgs = _memory.get_user(user_id).total_messages
            start = max(0, total_msgs - len(recent))
            date_range = f"msg{start}-{total_msgs}"
            _memory.add_summary(user_id, date_range, summary["summary"],
                               summary.get("key_topics", []), len(recent))
        # Daily emotion log + shared moments (once per N messages)
        total = _memory.get_user(user_id).total_messages
        if total % 15 == 0:
            emo = await _mem_mgr.log_daily_emotion(user_id, recent, _emotion)
            if emo:
                _memory.log_emotion(user_id, emo["dominant"], emo["intensity"], emo["note"], emo["msg_count"])
            moments = await _mem_mgr.extract_moments(user_id, recent, total)
            for m in moments:
                _memory.add_moment(user_id, m.get("type", "memorable"), m["content"], m.get("importance", 5))
    except Exception as e:
        logger.debug(f"Memory tasks skipped: {e}")

async def _extract_events(user_id, msg):
    global _events, _memory
    if not _events or not _memory: return
    try:
        for evt in await _events.extract(msg):
            _memory.add_event(user_id=user_id, event=evt.event, event_type=evt.type, remind_in_hours=evt.remind_in_hours, extracted_at=evt.extracted_at)
            if evt.remind_in_hours > 0: logger.info(f"Event: [{evt.type}] {evt.event}")
    except Exception: pass

async def handle_friend_add(user_id: str):
    global _qq_client, _memory
    if not _qq_client or not _memory: return
    cfg = get_config()
    try: nickname = (await _qq_client.get_stranger_info(user_id)).get("nickname", "新朋友")
    except: nickname = "新朋友"
    welcome = f"嗨～{nickname}！我是{cfg.bot.bot_name} 💕\n以后就让我来陪你聊天吧～\n首先，你希望我怎么称呼你呀？\n\n(设置名字后发「换人设」可以选我的人设哦～温柔女友/傲娇青梅/元气学妹/御姐前辈/二次元同好/码农女友)"
    await _qq_client.send_private_msg(user_id, welcome)
    _memory.add_message(user_id, "assistant", welcome)
    logger.info(f"Welcomed: {user_id}")

# ------------------------------------------------------------------ Routes
@app.post("/napcat/event")
async def napcat_event(request: Request):
    try: data = await request.json()
    except: return {"status": "bad_request"}
    pt = data.get("post_type")
    if pt == "message":
        mt = data.get("message_type"); uid = str(data.get("user_id",""))
        raw = data.get("raw_message", data.get("message",""))
        if mt == "private" and uid != get_config().bot.bot_qq:
            await handle_private_message(uid, raw)
    elif pt == "notice" and data.get("notice_type") == "friend_add":
        await handle_friend_add(str(data.get("user_id","")))
    return {"status": "ok"}

@app.get("/health")
async def health():
    c = get_config(); return {"status":"ok","bot":c.bot.bot_name,"qq":c.bot.bot_qq}

@app.get("/users")
async def list_users():
    if not _memory: return {"error":"not initialized"}
    return {"users":[{"user_id":u.user_id,"name":u.name,"persona":u.persona_id,"msgs":u.total_messages,"banned":len(u.banned_stickers)} for f in sorted(_memory.users_dir.glob("*.json")) if (u:=_memory.get_user(f.stem))],"total":len(list(_memory.users_dir.glob("*.json")))}

@app.get("/stickers")
async def list_stickers():
    return {"categories":_stickers.category_counts()} if _stickers else {"error":"not initialized"}

def main():
    cfg = load_config()
    logger.info(f"Starting {cfg.bot.bot_name} on {cfg.server.host}:{cfg.server.port}")
    uvicorn.run("gf.main:app", host=cfg.server.host, port=cfg.server.port, log_level="info")

if __name__ == "__main__":
    main()
