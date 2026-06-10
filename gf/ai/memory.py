"""Long-term memory — fact extraction, summarization, emotion logging, shared moments.

All LLM calls use moonshot-v1-8k (temperature=0) for stable JSON output.
"""

import logging
import json
import random
from openai import AsyncOpenAI
from .llm import LLMClient

logger = logging.getLogger(__name__)

# Lightweight client for structured extraction (stable JSON, cheap, fast)
_LITE_MODEL = "moonshot-v1-8k"
_LITE_CLIENT = None  # initialized lazily


def _get_lite_client() -> AsyncOpenAI:
    global _LITE_CLIENT
    if _LITE_CLIENT is None:
        from ..config import get_config
        cfg = get_config()
        _LITE_CLIENT = AsyncOpenAI(api_key=cfg.llm.api_key, base_url=cfg.llm.base_url)
    return _LITE_CLIENT


async def _lite_chat(system_prompt: str, user_content: str, max_tokens: int = 200) -> str:
    """Call moonshot-v1-8k with temperature=0 for stable structured output."""
    client = _get_lite_client()
    resp = await client.chat.completions.create(
        model=_LITE_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        max_tokens=max_tokens,
        temperature=0,
    )
    return resp.choices[0].message.content.strip()


def _parse_json(text: str) -> dict:
    """Robust JSON extraction from LLM output."""
    text = text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        return json.loads(text[start:end])
    return {}

EXTRACT_FACTS_PROMPT = """你是一个记忆提取器。阅读以下对话片段，提取**双向**的关键事实。

## 需要提取的信息

**关于用户**：
- 个人信息、偏好、人际关系、健康、学业/工作、经历、习惯

**关于我（AI女友）**：
- 我分享了关于自己的事（我的生活、我的感受、我的经历）
- 我做出了承诺（"我会帮你复习""我明天叫你起床"）
- 我表达了重要的感受

## 输出格式

只输出 JSON。importance: 1-10。

```json
{
  "facts": [
    {"subject": "user", "category": "preferences", "content": "用户喜欢FPS游戏", "importance": 8},
    {"subject": "me", "category": "self_disclosure", "content": "我告诉用户我的设计项目快做完了", "importance": 6},
    {"subject": "me", "category": "promise", "content": "我答应明天早上叫用户起床", "importance": 9}
  ]
}
```"""

SUMMARIZE_PROMPT = """你是一个对话摘要器。将下面的对话压缩成简洁的摘要。

保留：主要话题、情绪变化、重要事件、关键信息。
丢弃：寒暄、重复内容、琐碎闲聊。
如果对话中包含倾诉/深情告白/重要承诺，在摘要中标注为重要内容。

## 输出格式

只输出 JSON。

```json
{
  "summary": "这段对话中，用户在准备期末考试...",
  "key_topics": ["期末考试", "迷宫饭"],
  "high_importance": false
}
```"""


class MemoryManager:
    """Orchestrates fact extraction and summarization.

    Counters are persisted in UserProfile.preferences so they survive restarts.
    """

    def __init__(self, llm: LLMClient):
        self._llm = llm

    def _counter(self, store, user_id: str, key: str) -> int:
        """Get persisted counter for a user."""
        prefs = store.get_user(user_id).preferences
        return prefs.get(key, 0)

    def _inc_counter(self, store, user_id: str, key: str) -> int:
        """Increment and save a persisted counter. Returns new value."""
        profile = store.get_user(user_id)
        val = profile.preferences.get(key, 0) + 1
        profile.preferences[key] = val
        store.save_user(profile)
        return val

    async def maybe_extract_facts(self, user_id: str, recent_messages: list[dict],
                                   store) -> list[dict]:
        """Extract facts using stable moonshot-v1-8k (temperature=0)."""
        val = self._inc_counter(store, user_id, "mem_fact_counter")
        if val < 25:
            return []
        store.get_user(user_id).preferences["mem_fact_counter"] = 0
        store.save_user(store.get_user(user_id))

        conversation = "\n".join(
            f"{'👤' if m['role'] == 'user' else '🤖'}: {m['content'][:200]}"
            for m in recent_messages[-30:]
        )
        try:
            raw = await _lite_chat(EXTRACT_FACTS_PROMPT, conversation[:3000], max_tokens=400)
            data = _parse_json(raw)
            facts = data.get("facts", [])
            if facts:
                logger.info(f"Extracted {len(facts)} facts for {user_id}")
            return facts
        except Exception as e:
            logger.debug(f"Fact extraction skipped: {e}")
            return []

    async def maybe_summarize(self, user_id: str, recent_messages: list[dict],
                              existing_summaries: list[dict], store) -> dict | None:
        """Summarize using stable moonshot-v1-8k (temperature=0)."""
        val = self._inc_counter(store, user_id, "mem_summary_counter")
        if val < 30:
            return None
        store.get_user(user_id).preferences["mem_summary_counter"] = 0
        store.save_user(store.get_user(user_id))

        conversation = "\n".join(
            f"{'👤' if m['role'] == 'user' else '🤖'}: {m['content'][:150]}"
            for m in recent_messages[-40:]
        )
        try:
            raw = await _lite_chat(SUMMARIZE_PROMPT, conversation[:4000], max_tokens=300)
            data = _parse_json(raw)
            if data.get("summary"):
                data["high_importance"] = data.get("high_importance", False)
                logger.info(f"Summarized for {user_id}: {data.get('key_topics', [])}")
            return data
        except Exception as e:
            logger.debug(f"Summarization skipped: {e}")
            return None

    # ------------------------------------------------------------------
    # Emotion logging (daily)
    # ------------------------------------------------------------------

    async def log_daily_emotion(self, user_id: str, recent_messages: list[dict],
                                emotion_engine) -> None:
        """Summarize today's interaction atmosphere using stable moonshot-v1-8k."""
        from datetime import date
        today = date.today().isoformat()
        user_msgs = [m["content"] for m in recent_messages[-50:] if m["role"] == "user"]
        if not user_msgs:
            return
        try:
            combined = "\n".join(msg[:120] for msg in user_msgs[-20:])
            raw = await _lite_chat(
                "总结今天互动的整体氛围。不只用户情绪，也包括：对话的温暖程度、是否有高光或低谷时刻、是否比平时更亲密。只输出JSON：{\"dominant\":\"warm|happy|intimate|anxious|tired|cold|neutral\",\"note\":\"一句话（20字内），包含氛围和情绪\"}",
                combined[:2000], max_tokens=100,
            )
            data = _parse_json(raw)
            traj = emotion_engine.get_trajectory(user_id) if emotion_engine else None
            intensity = traj.mood_stability if traj else 0.5
            dominant = data.get("dominant", "neutral")
            note = data.get("note", "")
            logger.info(f"Emotion log [{today}]: {dominant} — {note}")
            return {"dominant": dominant, "intensity": intensity, "note": note, "msg_count": len(user_msgs)}
        except Exception as e:
            logger.debug(f"Emotion log skipped: {e}")
            return None

    # ------------------------------------------------------------------
    # Shared moments extraction
    # ------------------------------------------------------------------

    async def extract_moments(self, user_id: str, recent_messages: list[dict],
                               total_msgs: int) -> list[dict]:
        """Scan conversation for shared moments using stable moonshot-v1-8k."""
        conversation = "\n".join(
            f"{'👤' if m['role'] == 'user' else '🤖'}: {m['content'][:100]}"
            for m in recent_messages[-40:]
        )
        milestones = []
        if total_msgs in (100, 200, 500, 1000, 2000):
            milestones.append({
                "type": "milestone", "content": f"我们聊到了第{total_msgs}条消息！",
                "importance": 9 if total_msgs >= 500 else 7,
            })
        try:
            raw = await _lite_chat(
                "扫描对话，提取值得记住的共同瞬间。只输出JSON：{\"moments\":[{\"content\":\"...\",\"importance\":1-10}]}",
                conversation[:3000], max_tokens=300,
            )
            data = _parse_json(raw)
            for m in data.get("moments", []):
                milestones.append({
                    "type": "memorable", "content": m["content"],
                    "importance": m.get("importance", 5),
                })
        except Exception as e:
            logger.debug(f"Moment extraction skipped: {e}")
        return milestones
