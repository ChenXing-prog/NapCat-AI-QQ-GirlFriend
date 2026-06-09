"""Intelligent event extraction and follow-up system.

Uses LLM to extract important events from conversations, calculate
natural follow-up timing, and generate context-aware check-in messages.

Events are stored in the user's memory and used by:
- The chat handler (to reference past events during conversation)
- The scheduler (to trigger follow-up check-ins)
"""

import re
import time
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from .llm import LLMClient
from ..config import get_config


# ---------------------------------------------------------------------------
# Event extraction
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = """你是一个事件提取器。分析用户的发言，判断是否提到了值得记住的重要事件。

## 需要提取的事件类型

以下事件需要提取（符合任一即可）：
- 考试、面试、答辩、汇报
- 生病、不舒服、看医生
- 出差、旅行、搬家
- 入职、离职、跳槽
- 生日、纪念日
- 买了新东西（游戏机、电脑、手机等）
- 最近在玩/肝的游戏
- 最近在追的番/剧
- 重要的约定或计划
- 表达了不想出门/社交的想法（频率高时标记）

## 输出格式

只输出 JSON，不要其他文字。如果没有值得提取的事件，输出 {"events": []}。

```json
{
  "events": [
    {
      "event": "简短描述（15字以内）",
      "type": "exam|health|travel|work|personal|gaming|anime|social",
      "remind_in_hours": 多少小时后适合回访（0=不需要回访, 24=明天问, 168=下周问）
    }
  ]
}
```

## 回访时间参考
- 考试/面试：第二天（24h）
- 生病：几小时后（6h）
- 旅行：回来后（根据时长定）
- 买游戏机：第二天问好不好玩（24h）
- 追番：下周问看到哪了（168h）
- 其他：不紧急就下周（168h）"""


@dataclass
class ExtractedEvent:
    """A single event extracted from conversation."""
    event: str                     # Short description
    type: str                      # exam|health|travel|work|personal|gaming|anime|social
    remind_in_hours: int           # Hours until follow-up (0 = no follow-up)
    extracted_at: float            # Unix timestamp
    reminded: bool = False         # Already followed up?


class EventExtractor:
    """Extracts important events and generates follow-up messages.

    Usage:
        extractor = EventExtractor(llm_client)
        events = await extractor.extract("我明天有个重要的面试！")
        # events = [ExtractedEvent(event="用户有面试", type="exam", remind_in_hours=24)]
    """

    def __init__(self, llm: LLMClient):
        self._llm = llm
        self._last_extraction: dict[str, float] = {}  # user_id -> last extraction time

    async def extract(self, message: str) -> list[ExtractedEvent]:
        """Analyze a message and extract any important events.

        Uses LLM for deep understanding of the message content.
        Only runs extraction if the message is substantive (>10 chars).
        """
        if len(message) < 10:
            return []

        # Quick keyword pre-check to avoid unnecessary LLM calls
        if not self._might_contain_event(message):
            return []

        try:
            msgs = [
                LLMClient.system_message(EXTRACTION_PROMPT),
                LLMClient.user_message(f"用户发言：「{message[:300]}」"),
            ]
            reply, _ = await self._llm.chat(msgs)
            return self._parse_response(reply)
        except Exception:
            return []

    async def extract_batch(
        self, user_id: str, messages: list[str]
    ) -> list[ExtractedEvent]:
        """Extract events from multiple messages, with rate limiting.

        Only runs extraction if at least 10 messages since last check,
        to avoid excessive LLM API calls.
        """
        now = time.time()
        last = self._last_extraction.get(user_id, 0)

        # Rate limit: don't extract more than once per 20 messages
        if now - last < 300 and len(messages) < 20:
            return []

        # Only analyze the most recent 5 substantive messages
        substantive = [m for m in messages[-10:] if len(m) > 10]
        if not substantive:
            return []

        self._last_extraction[user_id] = now

        combined = "\n---\n".join(substantive[-5:])

        try:
            msgs = [
                LLMClient.system_message(EXTRACTION_PROMPT),
                LLMClient.user_message(f"用户最近的发言：\n{combined[:500]}"),
            ]
            reply, _ = await self._llm.chat(msgs)
            return self._parse_response(reply)
        except Exception:
            return []

    def _might_contain_event(self, text: str) -> bool:
        """Quick keyword check before spending LLM cost on extraction.

        Returns True if the text likely contains an event worth extracting.
        """
        event_keywords = [
            "明天", "后天", "下周", "下个月", "下星期",
            "考试", "面试", "答辩", "汇报", "出差", "旅行",
            "生病", "不舒服", "发烧", "感冒", "看医生",
            "搬家", "入职", "离职", "跳槽", "辞职",
            "生日", "纪念日", "周年",
            "买了", "新", "到了", "入手",
            "在玩", "在肝", "在追", "在看",
            "不想出门", "不想社交", "社恐",
            "要", "准备", "打算", "计划",
        ]
        return any(kw in text for kw in event_keywords)

    def _parse_response(self, raw: str) -> list[ExtractedEvent]:
        """Parse the LLM's JSON response into ExtractedEvent objects."""
        try:
            # Handle markdown code blocks
            json_str = raw
            if "```json" in raw:
                json_str = raw.split("```json")[1].split("```")[0]
            elif "```" in raw:
                json_str = raw.split("```")[1].split("```")[0]

            data = json.loads(json_str.strip())
        except (json.JSONDecodeError, IndexError):
            # Try to find a JSON object directly
            match = re.search(r'\{.*"events".*\}', raw, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    return []
            else:
                return []

        now = time.time()
        events = []
        for evt in data.get("events", []):
            if not evt.get("event"):
                continue
            events.append(ExtractedEvent(
                event=evt["event"][:50],
                type=evt.get("type", "personal"),
                remind_in_hours=int(evt.get("remind_in_hours", 0)),
                extracted_at=now,
            ))

        return events


# ---------------------------------------------------------------------------
# Follow-up message generation
# ---------------------------------------------------------------------------

FOLLOWUP_PROMPT = """你是一个贴心的AI女友，你需要很自然地问起对方之前提到的某件事。

## 要求
- 一句话即可，自然地提到这件事
- 不要像在完成任务，要像真的突然想起来了
- 语气符合你的人设
- 如果事情可能不顺利（考试、面试），先表达关心再问
- 如果事情令人期待（新游戏、旅行），带着兴奋感问

## 对方之前提到的事
{event_description}

## 现在已经过了
{hours_ago} 小时 / 约 {days_ago} 天"""


class FollowUpGenerator:
    """Generates natural follow-up messages for past events.

    Usage:
        generator = FollowUpGenerator(llm_client)
        message = await generator.generate(user_name, event, persona)
    """

    def __init__(self, llm: LLMClient):
        self._llm = llm

    async def generate(
        self,
        event: ExtractedEvent,
        user_name: str,
        bot_name: str,
    ) -> Optional[str]:
        """Generate a natural follow-up message about a past event.

        Args:
            event: The extracted event to follow up on
            user_name: User's name
            bot_name: Bot's name

        Returns:
            A one-line follow-up message, or None if generation fails.
        """
        now = time.time()
        hours_ago = int((now - event.extracted_at) / 3600)
        days_ago = max(1, hours_ago // 24)

        prompt = FOLLOWUP_PROMPT.format(
            event_description=event.event,
            hours_ago=hours_ago,
            days_ago=days_ago,
        )

        try:
            msgs = [
                LLMClient.system_message(
                    f"你是{bot_name}，你在和{user_name}聊天。"
                    f"自然地提起ta之前说的事。回复一句话。"
                ),
                LLMClient.user_message(prompt),
            ]
            reply, _ = await self._llm.chat(msgs)
            return reply.strip() if reply else None
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Scheduler integration helpers
# ---------------------------------------------------------------------------

def get_events_due_for_followup(events: list[dict], now: float) -> list[dict]:
    """Filter user events to find those due for a follow-up check-in.

    An event is "due" if:
    - It has remind_in_hours > 0
    - Enough time has passed since extraction
    - It hasn't been reminded yet

    Args:
        events: List of event dicts from UserProfile
        now: Current unix timestamp

    Returns:
        Events that are due for follow-up
    """
    due = []
    for evt in events:
        remind_hours = evt.get("remind_in_hours", 0)
        if remind_hours <= 0:
            continue
        if evt.get("reminded"):
            continue

        extracted_at = evt.get("extracted_at", 0)
        if extracted_at == 0:
            continue

        hours_since = (now - extracted_at) / 3600
        if hours_since >= remind_hours:
            due.append(evt)

    return due


def build_followup_context(due_events: list[dict]) -> str:
    """Build a context note for the system prompt about due follow-ups.

    Injects into the chat or proactive system prompt so the AI
    naturally weaves the follow-up into conversation.
    """
    if not due_events:
        return ""

    lines = ["\n[你有以下事情可以自然地关心一下对方：]"]
    for evt in due_events[:3]:
        hours = int((time.time() - evt.get("extracted_at", time.time())) / 3600)
        days = max(1, hours // 24)
        lines.append(f"- {evt['event']}（{days}天前提到的，可以问问怎么样了）")

    return "\n".join(lines)
