"""Sticker engine.

Maps LLM emotion tags to actual image files on disk.
Supports random selection from category folders with user blacklist filtering.

Directory structure:
  stickers/
    ├── cute/      meta.json + 1.jpg, 2.jpg...
    ├── shy/       meta.json + 1.jpg, 2.jpg...
    └── ...
"""

import random
import json
from pathlib import Path
from typing import Optional

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


class StickerEngine:
    """Selects sticker images based on emotion tags.

    Usage:
        engine = StickerEngine(stickers_dir=Path("./stickers"))
        path = engine.pick("shy")           # random shy sticker
        path = engine.pick("cute", banned={"1.jpg", "3.jpg"})  # blacklist
    """

    def __init__(self, stickers_dir: Path):
        self.stickers_dir = Path(stickers_dir)
        self._file_cache: dict[str, list[Path]] = {}
        self.refresh()

    def refresh(self):
        """Rebuild file cache (call after adding/removing stickers)."""
        self._file_cache.clear()
        if not self.stickers_dir.exists():
            return
        for folder in self.stickers_dir.iterdir():
            if not folder.is_dir() or folder.name.startswith("_"):
                continue
            files = [f for f in folder.iterdir()
                     if f.is_file() and not f.name.startswith("._")
                     and f.suffix.lower() in IMAGE_EXTS]
            if files:
                self._file_cache[folder.name] = sorted(files)

    def pick(self, tag: str, banned: Optional[set] = None) -> Optional[Path]:
        """Pick a random sticker from a category.

        Args:
            tag: Emotion tag (e.g., "shy", "cute")
            banned: Set of filenames to exclude (user blacklist)

        Returns:
            Path to image, or None if empty/banned everything.
        """
        files = self._file_cache.get(tag, [])
        if not files:
            return None

        if banned:
            available = [f for f in files if f.name not in banned]
        else:
            available = list(files)

        if not available:
            return None
        return random.choice(available)

    def pick_any(self, tags: list[str], banned: Optional[set] = None) -> Optional[Path]:
        """Pick a random sticker from any of the given categories.

        Useful when the LLM suggests multiple categories and we just
        want to pick one that has images available.
        """
        available_tags = [t for t in tags if self._file_cache.get(t)]
        if not available_tags:
            return None
        tag = random.choice(available_tags)
        return self.pick(tag, banned=banned)

    def has_images(self, tag: str) -> bool:
        """Check if a category has any images."""
        return len(self._file_cache.get(tag, [])) > 0

    def list_categories(self) -> list[str]:
        """List categories that have images."""
        return sorted(self._file_cache.keys())

    def category_counts(self) -> dict[str, int]:
        """Get count of images per category."""
        return {k: len(v) for k, v in self._file_cache.items()}

    def get_meta(self, tag: str) -> Optional[dict]:
        """Get metadata for an emotion category."""
        meta_file = self.stickers_dir / tag / "meta.json"
        if meta_file.exists():
            return json.loads(meta_file.read_text(encoding="utf-8"))
        return None
