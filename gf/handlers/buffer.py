"""Adaptive message buffering — merge rapid multi-messages into one turn."""

import asyncio
import logging
import time
from ..memory.store import MemoryStore

logger = logging.getLogger(__name__)

# ---- Constants ----
MSG_BUFFER_MIN = 3.0
MSG_BUFFER_MAX = 20.0
MSG_BUFFER_DEFAULT = 10.0
MSG_GAP_RESET = 300.0   # 5 min silence resets session
MSG_SESSION_WEIGHT = 0.7
MSG_BUFFER_MULTIPLIER = 1.5

# ---- State ----
_buffer: dict[str, list[str]] = {}
_tasks: dict[str, asyncio.Task] = {}
_last_msg_time: dict[str, float] = {}
_confide_mode: dict[str, bool] = {}


def calc_wait(user_id: str, memory: MemoryStore) -> float:
    """Adaptive buffer wait: current session + historical gaps."""
    prefs = memory.get_user(user_id).preferences
    session_gaps = prefs.get("msg_session_gaps", [])
    all_gaps = prefs.get("msg_gaps", [])
    if not all_gaps:
        return MSG_BUFFER_DEFAULT
    hist_avg = sum(all_gaps) / len(all_gaps)
    if len(session_gaps) == 1:
        sess_avg = session_gaps[0]
    elif len(session_gaps) >= 2:
        sess_avg = sum(session_gaps) / len(session_gaps)
    else:
        sess_avg = None
    if sess_avg is not None:
        wait = MSG_SESSION_WEIGHT * sess_avg + (1 - MSG_SESSION_WEIGHT) * hist_avg
    else:
        wait = hist_avg
    wait = wait * MSG_BUFFER_MULTIPLIER
    return min(MSG_BUFFER_MAX, max(MSG_BUFFER_MIN, wait))


async def flush_buffer(user_id: str, delay: float, handler_fn) -> None:
    """Wait, then dispatch all buffered messages as one."""
    global _buffer, _tasks
    await asyncio.sleep(delay)
    messages = _buffer.pop(user_id, [])
    _tasks.pop(user_id, None)
    if not messages:
        return
    combined = "\n".join(messages)
    logger.info(f"Buffer flush for {user_id}: {len(messages)} msgs after {delay:.1f}s")
    await handler_fn(user_id, combined)


def handle_incoming(user_id: str, message: str, memory: MemoryStore, handler_fn) -> bool:
    """Buffer a non-command message. Returns True if buffered, False if needs immediate flush."""
    global _buffer, _tasks, _last_msg_time

    # Record gap
    now = time.time()
    last_ts = _last_msg_time.get(user_id)
    if last_ts and memory:
        gap = now - last_ts
        if gap < MSG_GAP_RESET:
            memory.record_msg_gap(user_id, gap)
            profile = memory.get_user(user_id)
            sess = profile.preferences.get("msg_session_gaps", [])
            sess.append(round(gap, 2))
            if len(sess) > 10:
                sess = sess[-10:]
            profile.preferences["msg_session_gaps"] = sess
            memory.save_user(profile)
        elif user_id in _buffer:
            old = _tasks.pop(user_id, None)
            if old:
                old.cancel()
            asyncio.create_task(flush_buffer(user_id, 0, handler_fn))
    _last_msg_time[user_id] = now

    # Buffer
    _buffer.setdefault(user_id, []).append(message)
    if user_id in _tasks:
        _tasks[user_id].cancel()
    wait = calc_wait(user_id, memory)
    _tasks[user_id] = asyncio.create_task(flush_buffer(user_id, wait, handler_fn))
    return True


# ---- Confide mode ----

def confide_start(user_id: str) -> None:
    global _confide_mode, _buffer, _tasks, _last_msg_time
    _confide_mode[user_id] = True
    if user_id in _tasks:
        _tasks[user_id].cancel()
        _tasks.pop(user_id, None)
    _buffer[user_id] = []
    _last_msg_time.pop(user_id, None)


def confide_end(user_id: str) -> str:
    """End confide mode, return the combined message."""
    global _confide_mode, _buffer, _tasks, _last_msg_time
    _confide_mode[user_id] = False
    if user_id in _tasks:
        _tasks[user_id].cancel()
        _tasks.pop(user_id, None)
    combined = "\n".join(_buffer.pop(user_id, []))
    _last_msg_time.pop(user_id, None)
    return combined


def is_confide(user_id: str) -> bool:
    return _confide_mode.get(user_id, False)


def confide_collect(user_id: str, message: str) -> None:
    global _buffer
    _buffer.setdefault(user_id, []).append(message)
