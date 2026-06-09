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

    Uses per-category shuffle queues to avoid repeating the same image
    before cycling through all available images.

    Usage:
        engine = StickerEngine(stickers_dir=Path("./stickers"))
        path = engine.pick("shy")           # random shy sticker
        path = engine.pick("cute", banned={"1.jpg", "3.jpg"})  # blacklist
    """

    def __init__(self, stickers_dir: Path):
        self.stickers_dir = Path(stickers_dir)
        self._file_cache: dict[str, list[Path]] = {}
        self._queues: dict[str, list[str]] = {}  # tag → shuffled filenames
        self.refresh()

    def refresh(self):
        """Rebuild file cache and reset shuffle queues."""
        self._file_cache.clear()
        self._queues.clear()
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
                # Pre-shuffle for each category
                self._reshuffle(folder.name)

    def _reshuffle(self, tag: str):
        """Create a fresh shuffle queue for a category."""
        files = self._file_cache.get(tag, [])
        if files:
            names = [f.name for f in files]
            random.shuffle(names)
            self._queues[tag] = names

    # Fallback: if requested tag has no images, try similar ones
    _FALLBACK = {
        "pat": ["hug", "cute", "shy"], "caring": ["hug", "love", "smile"],
        "love": ["hug", "shy", "smile"], "hug": ["love", "cute", "shy"],
        "laugh": ["smile", "excited", "smirk"], "satisfied": ["smile", "smirk", "sleepy"],
        "heartbroken": ["cry", "teary", "corner"], "rage": ["pout", "speechless"],
        "panic": ["shocked", "speechless", "questioning"], "proud": ["smirk", "star_eyes", "excited"],
        "sigh": ["speechless", "corner", "sleepy"],
    }

    def pick(self, tag: str, banned: Optional[set] = None) -> Optional[Path]:
        """Pick a sticker. Falls back to similar tags if category is empty."""
        files = self._file_cache.get(tag, [])
        if files:
            return self._pick_one(tag, files, banned)
        # Fallback to similar tags
        for fb in self._FALLBACK.get(tag, []):
            fb_files = self._file_cache.get(fb, [])
            if fb_files:
                return self._pick_one(fb, fb_files, banned)
        return None

    def _pick_one(self, tag, files, banned):
        """Select one file from a category using shuffle queue."""
        if not self._queues.get(tag):
            self._reshuffle(tag)
        queue = self._queues[tag]
        attempts = 0
        while queue and attempts < len(files) * 2:
            name = queue[0]
            queue.pop(0)
            queue.append(name)
            attempts += 1
            if banned and name in banned:
                continue
            return files[0].parent / name
        return None

    def pick_any(self, tags: list[str], banned: Optional[set] = None) -> Optional[Path]:
        """Pick a random sticker from any of the given categories."""
        available_tags = [t for t in tags if self._file_cache.get(t)]
        if not available_tags:
            return None
        tag = random.choice(available_tags)
        return self.pick(tag, banned=banned)

    def has_images(self, tag: str) -> bool:
        return len(self._file_cache.get(tag, [])) > 0

    def list_categories(self) -> list[str]:
        return sorted(self._file_cache.keys())

    def category_counts(self) -> dict[str, int]:
        return {k: len(v) for k, v in self._file_cache.items()}

    def get_meta(self, tag: str) -> Optional[dict]:
        meta_file = self.stickers_dir / tag / "meta.json"
        if meta_file.exists():
            return json.loads(meta_file.read_text(encoding="utf-8"))
        return None

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
