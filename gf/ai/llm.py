"""LLM API client.

Supports DeepSeek, OpenAI, Kimi, and other OpenAI-compatible providers.
Parses position-aware sticker tags: [S:xxx], [S-MID:xxx], [S-ONLY:xxx].
"""

import re
from typing import Optional, Tuple, List, Dict, Union
from openai import AsyncOpenAI
from ..config import LLMConfig

# Load tags from meta.json at import time
from .sticker_meta import get_all_tags

_KNOWN_TAGS = set(get_all_tags())

# Normalize common LLM-generated tag names to our valid categories
_TAG_ALIASES = {
    "heart": "love", "hearts": "love", "heart_eyes": "love",
    "happy": "smile", "joy": "laugh", "funny": "laugh",
    "sad": "cry", "crying": "cry", "sob": "cry",
    "angry": "rage", "mad": "rage", "furious": "rage",
    "surprised": "shocked", "surprise": "shocked", "wow": "shocked",
    "sleeping": "sleepy", "tired": "sleepy", "yawn": "sleepy",
    "confused": "questioning", "confusion": "questioning", "what": "questioning",
    "embarrassed": "shy", "blush": "shy",
    "sorry": "teary", "apologize": "teary",
    "wink": "smirk", "devil": "smirk",
    "beg": "begging", "please": "begging",
    "hugging": "hug", "cuddle": "hug",
    "kiss": "love", "kissing": "love",
    "yay": "excited", "celebrate": "excited",
    "awesome": "star_eyes", "amazing": "star_eyes",
    "sigh": "sigh", "tired_sigh": "sigh",
}
# All matchable tags (known + aliases)
_ALL_MATCHABLE = _KNOWN_TAGS | set(_TAG_ALIASES.keys())

def _normalize_tag(tag: str) -> Optional[str]:
    """Convert a tag to a valid known tag, applying aliases."""
    if tag in _KNOWN_TAGS:
        return tag
    return _TAG_ALIASES.get(tag)

# Message part types
# {"type": "text", "content": str}
# {"type": "sticker_mid", "tag": str}   — sticker BEFORE this text piece
# {"type": "sticker_end", "tag": str}   — sticker AFTER this text piece
# {"type": "sticker_only", "tag": str}  — pure sticker, no text
MessagePart = Dict[str, str]


class LLMClient:
    """Async client for the LLM chat API."""

    # Position-aware tag patterns
    # [S:xxx] = sticker at end of message (legacy: also matches bare [xxx])
    STICKER_END_RE = re.compile(r"\[S:([a-z_]+)\]")
    # [S-MID:xxx] = sticker mid-conversation (between messages)
    STICKER_MID_RE = re.compile(r"\[S-MID:([a-z_]+)\]")
    # [S-ONLY:xxx] = pure sticker, no text
    STICKER_ONLY_RE = re.compile(r"\[S-ONLY:([a-z_]+)\]")
    # Legacy: bare [xxx] for known tags
    PLAIN_TAG_RE = re.compile(r"\[(" + "|".join(re.escape(t) for t in sorted(_ALL_MATCHABLE, key=len, reverse=True)) + r")\]")

    # Delimiter for multi-message output
    MSG_DELIMITER = "|||"

    def __init__(self, config: LLMConfig):
        self.config = config
        self._client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
        )

    # ------------------------------------------------------------------
    # Chat methods
    # ------------------------------------------------------------------

    async def chat(self, messages: list[dict]) -> Tuple[str, Optional[str]]:
        """Send messages to the LLM and get a single reply."""
        response = await self._client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
        )
        raw_text = response.choices[0].message.content or ""
        text, tag = self._clean_response(raw_text)
        return text, tag

    async def chat_multi(self, messages: list[dict]) -> Tuple[List[MessagePart], Optional[str]]:
        """Send messages and parse into position-aware message parts.

        Returns:
            Tuple of (list_of_message_parts, fallback_sticker_tag_or_None).
            Each part is one of: text, sticker_mid, sticker_end, sticker_only.
        """
        response = await self._client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
        )
        raw_text = response.choices[0].message.content or ""

        # Check for sticker-only mode
        only_tag = self._extract_only_tag(raw_text)
        if only_tag and len(raw_text.strip()) <= len(f"[S-ONLY:{only_tag}]") + 5:
            return [{"type": "sticker_only", "tag": only_tag}], None

        # Split by delimiter
        parts_raw = [p.strip() for p in raw_text.split(self.MSG_DELIMITER) if p.strip()]
        if len(parts_raw) <= 1:
            parts_raw = [p.strip() for p in raw_text.split("\n\n") if p.strip()]

        # Parse each part for mid-tags, end-tags, and text
        result: List[MessagePart] = []
        for part_text in parts_raw:
            mid_tag = None
            end_tag = None

            # Extract [S-MID:xxx]
            mid_match = self.STICKER_MID_RE.search(part_text)
            if mid_match and _normalize_tag(mid_match.group(1)):
                mid_tag = _normalize_tag(mid_match.group(1))
                result.append({"type": "sticker_mid", "tag": mid_tag})
                part_text = self.STICKER_MID_RE.sub("", part_text).strip()

            # Extract [S:xxx] (preferred format)
            end_match = self.STICKER_END_RE.search(part_text)
            if end_match and _normalize_tag(end_match.group(1)):
                end_tag = _normalize_tag(end_match.group(1))
                part_text = self.STICKER_END_RE.sub("", part_text).strip()

            # Also detect bare [xxx] tags and treat them as sticker_end
            if end_tag is None:
                bare_match = self.PLAIN_TAG_RE.search(part_text)
                if bare_match and _normalize_tag(bare_match.group(1)):
                    end_tag = _normalize_tag(bare_match.group(1))

            # Clean ALL tag formats from text
            part_text = self.STICKER_END_RE.sub("", part_text)
            part_text = self.STICKER_MID_RE.sub("", part_text)
            part_text = self.PLAIN_TAG_RE.sub("", part_text)
            # Catch-all: strip any remaining [...] patterns (kaomoji, Chinese, improvised tags)
            part_text = self._strip_any_brackets(part_text).strip()

            if part_text:
                if end_tag:
                    result.append({"type": "sticker_end", "tag": end_tag, "content": part_text})
                else:
                    result.append({"type": "text", "content": part_text})
            elif end_tag:
                result.append({"type": "sticker_end", "tag": end_tag, "content": ""})

        # Also check for a legacy overall fallback sticker
        fallback_tag = self._extract_tag(raw_text)

        if not result:
            result.append({"type": "text", "content": "嗯嗯～"})

        return result, fallback_tag

    # ------------------------------------------------------------------
    # Tag extraction
    # ------------------------------------------------------------------

    # Catch-all: strip any [...] text (kaomoji, Chinese tags, improvised English)
    _ANY_BRACKET_RE = re.compile(r"\[[^\]]*\]")

    def _strip_any_brackets(self, text: str) -> str:
        """Remove all [...] patterns from text.

        Only applied AFTER known sticker tags are extracted,
        so valid tags like [love] or [S:cute] are processed first.
        This catches kaomoji like [◍•ᴗ•◍], Chinese like [爱], and
        made-up tags like [coffee] [poke] that the LLM sometimes generates.
        """
        return self._ANY_BRACKET_RE.sub("", text)

    def _extract_tag(self, text: str) -> Optional[str]:
        """Extract any sticker tag from text (check all formats)."""
        for pat in [self.STICKER_END_RE, self.STICKER_MID_RE, self.PLAIN_TAG_RE]:
            m = pat.search(text)
            if m and _normalize_tag(m.group(1)):
                return _normalize_tag(m.group(1))
        return None

    def _extract_only_tag(self, text: str) -> Optional[str]:
        """Check if the ENTIRE response is just [S-ONLY:xxx]."""
        m = self.STICKER_ONLY_RE.search(text)
        if m and _normalize_tag(m.group(1)):
            return _normalize_tag(m.group(1))
        return None

    def _clean_response(self, raw_text: str) -> Tuple[str, Optional[str]]:
        """Remove all tag formats from text, return (clean_text, tag)."""
        tag = self._extract_tag(raw_text)
        clean = self.STICKER_END_RE.sub("", raw_text)
        clean = self.STICKER_MID_RE.sub("", clean)
        clean = self.STICKER_ONLY_RE.sub("", clean)
        clean = self.PLAIN_TAG_RE.sub("", clean)
        clean = self._strip_any_brackets(clean).strip()
        return clean, tag

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def user_message(content: str) -> dict:
        return {"role": "user", "content": content}

    @staticmethod
    def assistant_message(content: str) -> dict:
        return {"role": "assistant", "content": content}

    @staticmethod
    def system_message(content: str) -> dict:
        return {"role": "system", "content": content}
