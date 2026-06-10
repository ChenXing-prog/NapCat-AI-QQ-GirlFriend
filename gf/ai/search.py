"""LLM-driven web search: light model judges need → DuckDuckGo → inject results."""

import logging
from openai import AsyncOpenAI
from ..config import get_config

logger = logging.getLogger(__name__)

_SEARCH_JUDGE_PROMPT = """判断用户消息是否需要联网搜索才能准确回答。
- 需要 → 回复 SEARCH:<搜索词>
- 不需要 → 回复 NONE

判断标准：
- 询问实时信息（天气、新闻、股价、比赛）→ 搜索
- 提到你不确定的具体事物（歌名、作品名、冷门知识、产品）→ 搜索
- 需要最新数据的（排行榜、近期事件、新番、游戏）→ 搜索
- 日常闲聊、情感倾诉、打招呼、已知常识 → 不需要

只回复 SEARCH:xxx 或 NONE，不要其他文字。"""


async def should_search(message: str, context: list[str] = None) -> str | None:
    """Light LLM call to decide if web search is needed. Returns query or None.

    Args:
        message: Current user message
        context: Recent conversation messages for context (max 5)
    """
    cfg = get_config()
    client = AsyncOpenAI(api_key=cfg.llm.api_key, base_url=cfg.llm.base_url)
    user_content = message[:500]
    if context:
        ctx = "\n".join(f"- {m[:120]}" for m in context[-5:])
        user_content = f"对话上下文：\n{ctx}\n\n最新消息：{message[:500]}"
    try:
        resp = await client.chat.completions.create(
            model="moonshot-v1-8k",
            messages=[
                {"role": "system", "content": _SEARCH_JUDGE_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_tokens=30,
            temperature=0,
        )
        text = resp.choices[0].message.content.strip()
        if text.upper().startswith("NONE"):
            return None
        if "SEARCH:" in text.upper():
            query = text.split(":", 1)[1].strip()
            logger.info(f"LLM decided to search: {query[:80]}")
            return query
        return None
    except Exception as e:
        logger.debug(f"Search judge failed: {e}, falling back to keyword check")
        # Fallback: keyword detection
        triggers = ["天气", "新闻", "最近", "今天", "新番", "热搜", "最新", "实时", "查一"]
        for t in triggers:
            if t in message:
                return message[:200]
        return None


async def search_web(query: str, max_results: int = 3) -> list[dict]:
    """Search DuckDuckGo for query. Returns [{title, url, snippet}]."""
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r["title"],
                    "url": r.get("href", ""),
                    "snippet": r["body"][:200],
                })
        if results:
            logger.info(f"DuckDuckGo '{query[:50]}' → {len(results)} results")
        return results
    except Exception as e:
        logger.debug(f"DuckDuckGo failed: {e}")
        return []


def format_results(results: list[dict]) -> str:
    """Format search results for LLM context."""
    if not results:
        return ""
    lines = ["[以下是从网上搜索到的实时信息，供你参考：]"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}\n   {r['snippet']}")
    return "\n".join(lines)


async def maybe_search(message: str, context: list[str] = None) -> str | None:
    """Full pipeline: judge (with context) → search → format."""
    query = await should_search(message, context)
    if not query:
        return None
    results = await search_web(query)
    return format_results(results) if results else None
