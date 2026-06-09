"""Sticker emotion metadata.

Dynamically loads all categories from the stickers/ directory.
Each category folder contains a meta.json with:
  - emotion: English tag
  - label: Chinese label
  - use_when: When to use this emotion
  - example: Example scenario
"""

import json
from pathlib import Path
from typing import Optional


def _load_all_meta() -> list[dict]:
    """Load meta.json from all sticker category folders."""
    stickers_dir = Path(__file__).parent.parent.parent / "stickers"
    meta_list = []

    for folder in sorted(stickers_dir.iterdir()):
        if not folder.is_dir() or folder.name.startswith("_"):
            continue
        meta_file = folder / "meta.json"
        if meta_file.exists():
            data = json.loads(meta_file.read_text(encoding="utf-8"))
            data["emotion"] = folder.name  # Ensure tag matches folder name
            meta_list.append(data)

    return meta_list


# Auto-load on import
STICKER_META = _load_all_meta()


def get_meta(tag: str) -> Optional[dict]:
    """Get metadata for a specific emotion tag."""
    for m in STICKER_META:
        if m["emotion"] == tag:
            return m
    return None


def get_all_tags() -> list[str]:
    """Return all valid sticker emotion tags."""
    return [m["emotion"] for m in STICKER_META]


def build_tag_guide() -> str:
    """Build a markdown-style guide of all tags for the system prompt."""
    lines = []
    for m in STICKER_META:
        lines.append(
            f"- `[{m['emotion']}]` = {m.get('label', m['emotion'])}："
            f"{m.get('use_when', '')}"
        )
    return "\n".join(lines)
