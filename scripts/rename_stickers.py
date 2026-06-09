#!/usr/bin/env python3
"""Rename all sticker images to numbered filenames (1.jpg, 2.jpg, ...)."""

import json
from pathlib import Path

STICKERS_DIR = Path(__file__).parent.parent / "stickers"
VALID_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def rename_category(folder: Path):
    """Rename all images in a category folder to numbered names."""
    images = sorted([
        f for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in VALID_EXTS
    ])

    if not images:
        return 0

    for i, img in enumerate(images, 1):
        new_name = f"{i}{img.suffix.lower()}"
        new_path = folder / new_name
        if img.name != new_name:
            img.rename(new_path)

    return len(images)


def main():
    total = 0
    for folder in sorted(STICKERS_DIR.iterdir()):
        if not folder.is_dir() or folder.name.startswith("_"):
            continue

        count = rename_category(folder)
        if count > 0:
            print(f"  {folder.name:15s} → {count} images renamed")
            total += count

    print(f"\nTotal: {total} images renamed across all categories")


if __name__ == "__main__":
    main()
