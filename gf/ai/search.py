"""Web search module — DuckDuckGo free API, auto-detects when to search."""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Keywords that suggest the message needs real-time info
_SEARCH_TRIGGERS = [
    r"天气", r"新闻", r"最近", r"今天", r"现在", r"当前",
    r"最新", r"刚[才刚]", r"实时", r"热搜", r"热点",
    r"新番.*推荐", r"好看.*番", r"漫展.*202[0-9]",
    r"什么.*游戏.*火", r"推荐.*游戏", r"steam.*新",
    r"多少[钱价]", r"怎么[样么]", r"好不[好听看玩]",
    r"有.*(?:新|好|火|推荐).*(?:吗|么|没有)",
    r"(?:今天|明天|后天|这周|下周|最近).*(?:天气|温度|下雨|晴)",
]

# Questions that likely need current info
_QUESTION_PATTERNS = [
    r"(?:有没有|有什么|哪些|推荐|怎么|怎么样|如何|为什么|是什么|谁是)",
    r"(?:告诉我|搜一下|查一下|帮我查|找一下)",
]

_SEARCH_NEEDED_RE = re.compile(
    "|".join(_SEARCH_TRIGGERS + _QUESTION_PATTERNS), re.IGNORECASE
)


def needs_search(message: str) -> bool:
    """Quick check if message likely needs web search."""
    return bool(_SEARCH_NEEDED_RE.search(message))


async def search_web(query: str, max_results: int = 3) -> list[dict]:
    """Search DuckDuckGo and return top results.

    Returns list of {title, url, snippet}.
    """
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
            logger.info(f"Web search '{query[:50]}' → {len(results)} results")
        return results
    except Exception as e:
        logger.debug(f"Web search failed: {e}")
        return []


def format_results(results: list[dict]) -> str:
    """Format search results for LLM context injection."""
    if not results:
        return ""
    lines = ["[以下是从网上搜索到的实时信息，你可以参考：]"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}\n   {r['snippet']}")
    return "\n".join(lines)


async def maybe_search(message: str) -> Optional[str]:
    """Check if search is needed, do it, return formatted results or None."""
    if not needs_search(message):
        return None
    # Use the message itself as the query
    results = await search_web(message[:200])
    return format_results(results) if results else None
