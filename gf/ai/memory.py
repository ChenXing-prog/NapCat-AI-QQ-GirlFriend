"""Long-term memory — fact extraction and conversation summarization.

Runs asynchronously in background to avoid blocking the chat pipeline.
"""

import logging
from .llm import LLMClient

logger = logging.getLogger(__name__)

EXTRACT_FACTS_PROMPT = """你是一个记忆提取器。阅读以下对话片段，从中提取关于用户的**关键事实**。

只提取值得长期记住的信息。如果对话中没有值得记住的新信息，返回空列表。

## 需要提取的信息类型

- **个人信息**：名字、年龄、生日、学校、专业、城市
- **偏好**：喜欢/不喜欢什么（食物、音乐、游戏、动漫等）
- **人际关系**：家人、朋友、恋人、宠物
- **健康**：过敏、疾病、作息习惯
- **学业/工作**：考试、面试、课题、项目
- **经历**：去过的地方、做过的事、有趣的经历
- **习惯**：日常作息、行为模式

## 输出格式

只输出 JSON，不要其他文字。

```json
{
  "facts": [
    {"category": "preferences", "content": "用户喜欢玩FPS游戏，尤其是CS:GO和瓦罗兰特", "importance": 8},
    {"category": "personal_info", "content": "用户对花生过敏", "importance": 9}
  ]
}
```

importance: 1-10。10 = 非常重要（过敏、生日、亲人），5 = 一般重要（喜欢什么游戏），1 = 琐碎"""

SUMMARIZE_PROMPT = """你是一个对话摘要器。将下面的对话压缩成简洁的摘要。

保留：主要话题、情绪变化、重要事件、关键信息。
丢弃：寒暄、重复内容、琐碎闲聊。

## 输出格式

只输出 JSON，不要其他文字。

```json
{
  "summary": "这段对话中，用户在准备期末考试，情绪比较焦虑。讨论了《迷宫饭》第二季定档的消息，用户表示很期待。用户提到周末想和朋友去漫展但没时间。",
  "key_topics": ["期末考试", "迷宫饭", "漫展"]
}
```"""


class MemoryManager:
    """Orchestrates fact extraction and summarization."""

    def __init__(self, llm: LLMClient):
        self._llm = llm
        self._extract_counters: dict[str, int] = {}  # user_id → msgs since last extract
        self._summary_counters: dict[str, int] = {}  # user_id → msgs since last summary

    async def maybe_extract_facts(self, user_id: str, recent_messages: list[dict]) -> list[dict]:
        """Extract facts if enough new messages accumulated (every ~25 msgs)."""
        self._extract_counters[user_id] = self._extract_counters.get(user_id, 0) + 1
        if self._extract_counters[user_id] < 25:
            return []
        self._extract_counters[user_id] = 0

        conversation = "\n".join(
            f"{'👤' if m['role'] == 'user' else '🤖'}: {m['content'][:200]}"
            for m in recent_messages[-30:]
        )
        try:
            msgs = [
                LLMClient.system_message(EXTRACT_FACTS_PROMPT),
                LLMClient.user_message(conversation[:3000]),
            ]
            reply, _ = await self._llm.chat(msgs)
            import json
            if "```" in reply:
                reply = reply.split("```")[1].split("```")[0]
                if reply.startswith("json"):
                    reply = reply[4:]
            data = json.loads(reply.strip())
            facts = data.get("facts", [])
            if facts:
                logger.info(f"Extracted {len(facts)} facts for {user_id}")
            return facts
        except Exception as e:
            logger.debug(f"Fact extraction skipped: {e}")
            return []

    async def maybe_summarize(self, user_id: str, recent_messages: list[dict],
                              existing_summaries: list[dict]) -> dict | None:
        """Summarize if enough messages accumulated (every ~30 msgs)."""
        self._summary_counters[user_id] = self._summary_counters.get(user_id, 0) + 1
        if self._summary_counters[user_id] < 30:
            return None
        self._summary_counters[user_id] = 0

        conversation = "\n".join(
            f"{'👤' if m['role'] == 'user' else '🤖'}: {m['content'][:150]}"
            for m in recent_messages[-40:]
        )
        try:
            msgs = [
                LLMClient.system_message(SUMMARIZE_PROMPT),
                LLMClient.user_message(conversation[:4000]),
            ]
            reply, _ = await self._llm.chat(msgs)
            import json
            if "```" in reply:
                reply = reply.split("```")[1].split("```")[0]
                if reply.startswith("json"):
                    reply = reply[4:]
            data = json.loads(reply.strip())
            logger.info(f"Summarized conversation for {user_id}: {data.get('key_topics', [])}")
            return data
        except Exception as e:
            logger.debug(f"Summarization skipped: {e}")
            return None
