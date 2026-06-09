#!/usr/bin/env python3
"""Restore duplicate images to their matching categories."""

import sys
from pathlib import Path

try:
    from imagehash import phash
    from PIL import Image
except ImportError:
    print("pip install imagehash Pillow")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).parent.parent
DUPLICATES_DIR = PROJECT_ROOT / "data" / "images" / "_duplicates"
STICKERS_DIR = PROJECT_ROOT / "stickers"
VALID_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def compute_hash(img_path: Path) -> str:
    img = Image.open(img_path)
    if getattr(img, "is_animated", False):
        img.seek(0)
    return str(phash(img))


def find_best_match(dup_path: Path, candidates: list[Path]) -> tuple[Path, int]:
    dup_hash = compute_hash(dup_path)
    best = None
    best_dist = 999
    for c in candidates:
        try:
            dist = sum(a != b for a, b in zip(dup_hash, compute_hash(c)))
            if dist < best_dist:
                best_dist = dist
                best = c
        except Exception:
            continue
    return best, best_dist


def main():
    dup_files = [f for f in DUPLICATES_DIR.iterdir()
                 if f.is_file() and f.suffix.lower() in VALID_EXTS]
    if not dup_files:
        print("No duplicate files found in _duplicates/")
        return

    # Collect all existing stickers
    all_stickers = []
    for folder in STICKERS_DIR.iterdir():
        if folder.is_dir() and not folder.name.startswith("_"):
            for f in folder.iterdir():
                if f.is_file() and f.suffix.lower() in VALID_EXTS:
                    all_stickers.append(f)

    print(f"Restoring {len(dup_files)} duplicates to matching categories...")
    print(f"Comparing against {len(all_stickers)} existing stickers\n")

    for dup in dup_files:
        match, dist = find_best_match(dup, all_stickers)
        if match and dist <= 10:
            target_dir = match.parent
            # Find next available number
            existing = [f for f in target_dir.iterdir()
                        if f.is_file() and f.suffix.lower() in VALID_EXTS]
            next_num = len(existing) + 1
            new_name = f"{next_num}{dup.suffix.lower()}"
            target = target_dir / new_name
            dup.rename(target)
            print(f"  {dup.name} → {target_dir.name}/{new_name} (match={match.name}, dist={dist})")
        else:
            print(f"  {dup.name} → no good match found (kept in _duplicates/)")

    # Check if duplicates dir is empty
    remaining = [f for f in DUPLICATES_DIR.iterdir() if f.is_file()]
    if not remaining:
        print(f"\nAll duplicates restored! {DUPLICATES_DIR} is now empty.")
    else:
        print(f"\n{len(remaining)} files could not be matched, still in _duplicates/")


if __name__ == "__main__":
    main()
