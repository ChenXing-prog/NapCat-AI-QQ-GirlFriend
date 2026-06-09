#!/usr/bin/env python3
"""
表情包自动分类脚本 — Kimi Vision API 批量分类

Usage:
    # 完整流程：预处理 → 分类 → 移动 → 报告
    python scripts/classify_stickers.py

    # 仅预处理
    python scripts/classify_stickers.py --step preprocess

    # 仅分类（支持断点续传）
    python scripts/classify_stickers.py --step classify

    # 仅生成报告
    python scripts/classify_stickers.py --step report

    # 干跑（不实际移动文件）
    python scripts/classify_stickers.py --dry-run

Env:
    MOONSHOT_API_KEY (in scripts/.env or environment)
"""

import argparse
import asyncio
import base64
import hashlib
import io
import json
import logging
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx
from PIL import Image
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("classify")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
DATA_IMAGES = PROJECT_ROOT / "data" / "images"
STICKERS_DIR = PROJECT_ROOT / "stickers"
DUPLICATES_DIR = DATA_IMAGES / "_duplicates"
CORRUPTED_DIR = DATA_IMAGES / "_corrupted"
REVIEW_DIR = STICKERS_DIR / "_review"
PROGRESS_FILE = Path(__file__).parent / "classification_progress.json"
REPORT_FILE = Path(__file__).parent / "classification_report.md"

# ---------------------------------------------------------------------------
# Valid image extensions
# ---------------------------------------------------------------------------
VALID_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# ---------------------------------------------------------------------------
# 30 categories (must match stickers/ subdirectories)
# ---------------------------------------------------------------------------
VALID_TAGS = [
    "laugh", "smile", "smirk", "star_eyes", "satisfied", "excited",
    "shy", "cute", "clingy", "begging", "pout",
    "tsundere", "eye_roll", "speechless", "questioning", "sigh",
    "caring", "pat", "hug", "love",
    "cry", "teary", "heartbroken", "corner",
    "shocked", "panic",
    "peek", "proud", "sleepy", "rage",
]

# ---------------------------------------------------------------------------
# Kimi API config
# ---------------------------------------------------------------------------
KIMI_BASE_URL = "https://api.moonshot.cn/v1"
KIMI_MODEL = "moonshot-v1-8k-vision-preview"
API_TIMEOUT = 60.0
RETRY_DELAY = 3.0
MAX_RETRIES = 2
CONCURRENCY = 3  # Max parallel API calls

# Image resize: max 800px wide for API efficiency
MAX_IMAGE_WIDTH = 800

# Perceptual hash threshold for duplicates (hamming distance)
PHASH_THRESHOLD = 8


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ClassificationResult:
    filename: str
    tag: str
    confidence: float
    description: str
    reason: str = ""  # empty = normal, otherwise error/needs-review


# ---------------------------------------------------------------------------
# Load API key
# ---------------------------------------------------------------------------

def load_api_key() -> str:
    """Load Moonshot API key from scripts/.env or environment."""
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
    key = os.getenv("MOONSHOT_API_KEY", "").strip()
    if not key:
        logger.error("MOONSHOT_API_KEY not found!")
        logger.error("  1. Copy scripts/.env.example to scripts/.env")
        logger.error("  2. Fill in your API key")
        sys.exit(1)
    return key


# ---------------------------------------------------------------------------
# Step 0: Preprocess (deduplication + validation)
# ---------------------------------------------------------------------------

def _compute_phash(img_path: Path) -> Optional[str]:
    """Compute perceptual hash of an image. Returns None if fails."""
    try:
        from imagehash import phash
        img = Image.open(img_path)
        # For GIF, take first frame
        if getattr(img, "is_animated", False):
            img.seek(0)
        return str(phash(img))
    except Exception as e:
        logger.debug(f"phash failed for {img_path.name}: {e}")
        return None


def step_preprocess() -> list[Path]:
    """
    Preprocess images:
    1. Scan data/images/
    2. Validate file format and integrity
    3. Deduplicate using perceptual hash
    4. Move duplicates/corrupted to _duplicates/ / _corrupted/

    Returns list of valid image paths ready for classification.
    """
    logger.info("=" * 60)
    logger.info("Step 0: Preprocessing")
    logger.info("=" * 60)

    DUPLICATES_DIR.mkdir(exist_ok=True)
    CORRUPTED_DIR.mkdir(exist_ok=True)

    # Collect all image files
    all_files = [
        f for f in DATA_IMAGES.iterdir()
        if f.is_file() and f.suffix.lower() in VALID_EXTS
        and not f.name.startswith(".") and not f.name.startswith("_")
    ]
    logger.info(f"Found {len(all_files)} image files in {DATA_IMAGES}")

    valid_files: list[Path] = []
    corrupted: list[Path] = []
    duplicates: list[Path] = []

    # Track hashes for deduplication
    hashes: dict[str, Path] = {}  # phash -> first file

    for f in all_files:
        # Try open with Pillow
        try:
            img = Image.open(f)
            img.verify()  # Quick integrity check
            # Re-open after verify
            img = Image.open(f)
            w, h = img.size
            if w < 20 or h < 20 or w > 8000 or h > 8000:
                logger.warning(f"  Suspicious size {w}x{h}: {f.name}")
        except Exception as e:
            logger.warning(f"  Corrupted/invalid: {f.name} ({e})")
            corrupted.append(f)
            continue

        # Deduplication
        ph = _compute_phash(f)
        if ph:
            dup_of = None
            for existing_hash, existing_path in hashes.items():
                # Simple hamming distance comparison
                dist = sum(c1 != c2 for c1, c2 in zip(ph, existing_hash))
                if dist <= PHASH_THRESHOLD:
                    dup_of = existing_path
                    break
            if dup_of:
                logger.info(f"  Duplicate of {dup_of.name}: {f.name}")
                duplicates.append(f)
                continue
            hashes[ph] = f

        valid_files.append(f)

    # Move corrupted and duplicates
    for f in corrupted:
        shutil.move(str(f), str(CORRUPTED_DIR / f.name))
    for f in duplicates:
        shutil.move(str(f), str(DUPLICATES_DIR / f.name))

    logger.info(f"  Valid: {len(valid_files)} | Corrupted: {len(corrupted)} | Duplicates: {len(duplicates)}")
    return valid_files


# ---------------------------------------------------------------------------
# Step 1: Classify with Kimi Vision API
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "你是一个表情包分类器。用户会给你一张表情包图片，"
    "你需要判断这张图表达的情绪，从给定的分类中选择最匹配的一个。"
    "只输出 JSON，不要其他文字。"
)

_USER_PROMPT_TEMPLATE = """请判断这张表情包的情绪分类。

可选分类（只能选一个）：
- laugh：大笑、笑死、爆笑
- smile：微笑、开心、温馨
- smirk：坏笑、嘿嘿嘿、有小九九
- star_eyes：星星眼、崇拜、好厉害
- satisfied：满足、吃饱了、爽
- excited：兴奋、太好了、耶
- shy：害羞、脸红、不好意思
- cute：卖萌、求关注、可爱
- clingy：黏人、别走、陪陪我
- begging：求求了、拜托、跪求
- pout：撅嘴、哼、不乐意
- tsundere：傲娇、才不是为你、口是心非
- eye_roll：嫌弃、翻白眼
- speechless：无语、不想说话
- questioning：问号、黑人问号
- sigh：叹气、心累、唉
- caring：关心、体贴、担心
- pat：摸摸头、安慰、乖
- hug：抱抱、想要拥抱
- love：比心、爱你、喜欢你
- cry：大哭、哭死、爆哭
- teary：委屈、含泪、被冤枉
- heartbroken：心碎、受伤了
- corner：蹲角落、自闭、别理我
- shocked：震惊、什么情况
- panic：慌张、完了完了
- peek：暗中观察、让我看看
- proud：得意、哼我厉害吧
- sleepy：困了、晚安、睡觉
- rage：暴怒、掀桌、气炸

输出 JSON 格式：
{"tag": "分类标签", "confidence": 0.0-1.0, "description": "中文简短描述（10字内）"}"""


async def _classify_single(
    client: httpx.AsyncClient,
    api_key: str,
    img_path: Path,
    semaphore: asyncio.Semaphore,
) -> ClassificationResult:
    """Classify a single image using Kimi Vision API."""
    async with semaphore:
        # Resize and encode image
        try:
            img = Image.open(img_path)
            if getattr(img, "is_animated", False):
                img.seek(0)
            # Resize if too large
            if img.width > MAX_IMAGE_WIDTH:
                ratio = MAX_IMAGE_WIDTH / img.width
                new_h = int(img.height * ratio)
                img = img.resize((MAX_IMAGE_WIDTH, new_h), Image.LANCZOS)
            # Convert to RGB if necessary (for JPEG encoding)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            b64 = base64.b64encode(buf.getvalue()).decode()
        except Exception as e:
            return ClassificationResult(
                filename=img_path.name, tag="", confidence=0.0,
                description="", reason=f"encode_error: {e}",
            )

        # Build messages
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    },
                    {"type": "text", "text": _USER_PROMPT_TEMPLATE},
                ],
            },
        ]

        payload = {
            "model": KIMI_MODEL,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 100,
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Call API with retries
        last_error = ""
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = await client.post(
                    f"{KIMI_BASE_URL}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=API_TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                break
            except Exception as e:
                last_error = str(e)
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    return ClassificationResult(
                        filename=img_path.name, tag="", confidence=0.0,
                        description="", reason=f"api_error: {last_error}",
                    )

        # Parse JSON from content
        # Kimi may wrap in markdown code block
        raw = content.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            return ClassificationResult(
                filename=img_path.name, tag="", confidence=0.0,
                description="", reason=f"json_parse: {e} | raw={raw[:200]}",
            )

        tag = parsed.get("tag", "").strip().lower()
        confidence = float(parsed.get("confidence", 0.0))
        description = parsed.get("description", "")[:50]

        # Validate tag
        if tag not in VALID_TAGS:
            return ClassificationResult(
                filename=img_path.name, tag=tag, confidence=confidence,
                description=description,
                reason=f"unknown_tag: {tag}",
            )

        return ClassificationResult(
            filename=img_path.name,
            tag=tag,
            confidence=confidence,
            description=description,
            reason="",
        )


async def step_classify(images: list[Path], dry_run: bool = False) -> list[ClassificationResult]:
    """
    Classify all images using Kimi Vision API.
    Supports resuming from progress file.
    """
    logger.info("=" * 60)
    logger.info("Step 1: Kimi Vision API Classification")
    logger.info("=" * 60)

    api_key = load_api_key()

    # Load progress
    progress: dict = {}
    if PROGRESS_FILE.exists():
        try:
            progress = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
            logger.info(f"Loaded progress: {len(progress.get('completed', []))}/{len(images)} done")
        except Exception:
            progress = {}

    completed = set(progress.get("completed", []))
    failed = dict(progress.get("failed", {}))
    results = dict(progress.get("results", {}))

    # Filter out already done
    todo = [img for img in images if img.name not in completed]
    if not todo:
        logger.info("All images already classified!")
    else:
        logger.info(f"Classifying {len(todo)} images (concurrency={CONCURRENCY})...")

    semaphore = asyncio.Semaphore(CONCURRENCY)
    start_time = time.time()

    async with httpx.AsyncClient() as client:
        for i, img in enumerate(todo, 1):
            result = await _classify_single(client, api_key, img, semaphore)

            if result.reason.startswith("api_error") or result.reason.startswith("encode_error"):
                failed[result.filename] = result.reason
                logger.warning(f"  [{i}/{len(todo)}] FAIL {result.filename}: {result.reason}")
            else:
                completed.add(result.filename)
                results[result.filename] = {
                    "tag": result.tag,
                    "confidence": result.confidence,
                    "description": result.description,
                    "reason": result.reason,
                }
                status = "OK" if not result.reason else f"REVIEW({result.reason})"
                logger.info(f"  [{i}/{len(todo)}] {status} {result.filename} → {result.tag} ({result.confidence:.0%}) {result.description}")

            # Save progress every 5 images
            if i % 5 == 0 or i == len(todo):
                _save_progress(completed, failed, results)
                elapsed = time.time() - start_time
                avg = elapsed / i if i > 0 else 0
                remaining = (len(todo) - i) * avg
                logger.info(f"  Progress saved. Avg {avg:.1f}s/img, ETA {remaining/60:.1f}min")

    # Build result list
    all_results: list[ClassificationResult] = []
    for img in images:
        fn = img.name
        if fn in results:
            r = results[fn]
            all_results.append(ClassificationResult(
                filename=fn,
                tag=r["tag"],
                confidence=r["confidence"],
                description=r["description"],
                reason=r.get("reason", ""),
            ))
        elif fn in failed:
            all_results.append(ClassificationResult(
                filename=fn, tag="", confidence=0.0,
                description="", reason=failed[fn],
            ))

    return all_results


def _save_progress(completed: set, failed: dict, results: dict):
    """Save classification progress to JSON file."""
    data = {
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total": len(completed) + len(failed) + len(set(results) - completed - set(failed)),
        "completed": sorted(list(completed)),
        "failed": failed,
        "results": results,
    }
    PROGRESS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Step 2: Move files
# ---------------------------------------------------------------------------

def step_move(results: list[ClassificationResult], dry_run: bool = False) -> dict:
    """
    Move classified images to stickers/{tag}/ directories.
    Low-confidence results go to stickers/_review/.
    """
    logger.info("=" * 60)
    logger.info("Step 2: Moving files")
    logger.info("=" * 60)

    REVIEW_DIR.mkdir(exist_ok=True)

    moved = 0
    review = 0
    failed = 0
    tag_counts: dict[str, int] = {}

    for r in results:
        src = DATA_IMAGES / r.filename
        if not src.exists():
            logger.warning(f"  Source not found: {r.filename}")
            continue

        # Determine destination
        if r.reason.startswith("api_error") or r.reason.startswith("encode_error"):
            logger.warning(f"  SKIP (API fail): {r.filename}")
            failed += 1
            continue

        if r.confidence < 0.5 or r.reason:
            dst_dir = REVIEW_DIR
            review += 1
            logger.info(f"  REVIEW {r.filename} → _review/ (tag={r.tag}, conf={r.confidence:.0%}, reason={r.reason})")
        else:
            dst_dir = STICKERS_DIR / r.tag
            dst_dir.mkdir(exist_ok=True)
            moved += 1
            tag_counts[r.tag] = tag_counts.get(r.tag, 0) + 1
            logger.info(f"  MOVE {r.filename} → {r.tag}/")

        if not dry_run:
            shutil.move(str(src), str(dst_dir / r.filename))

    logger.info(f"  Moved: {moved} | Review: {review} | Failed: {failed}")
    return tag_counts


# ---------------------------------------------------------------------------
# Step 3: Report
# ---------------------------------------------------------------------------

def step_report(results: list[ClassificationResult], tag_counts: dict, dry_run: bool = False):
    """Generate classification report markdown."""
    logger.info("=" * 60)
    logger.info("Step 3: Generating report")
    logger.info("=" * 60)

    total = len(results)
    ok = sum(1 for r in results if r.confidence >= 0.5 and not r.reason)
    review = sum(1 for r in results if r.confidence < 0.5 or r.reason and not r.reason.startswith("api"))
    failed = sum(1 for r in results if r.reason.startswith("api") or r.reason.startswith("encode"))

    lines = [
        "# 表情包分类报告",
        "",
        f"生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"API 模型：{KIMI_MODEL}",
        f"总数量：{total} 张",
        f"成功分类：{ok} 张",
        f"需人工复审：{review} 张（低置信度或未知标签）",
        f"API 失败：{failed} 张",
        "",
        "## 分类分布",
        "",
        "| 分类 | 中文 | 数量 | 占比 |",
        "|------|------|------|------|",
    ]

    # Tag → label mapping
    tag_labels = {}
    for tag in VALID_TAGS:
        meta_file = STICKERS_DIR / tag / "meta.json"
        if meta_file.exists():
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            tag_labels[tag] = meta.get("label", tag)
        else:
            tag_labels[tag] = tag

    for tag in sorted(tag_counts, key=lambda t: -tag_counts[t]):
        count = tag_counts[tag]
        pct = count / total * 100
        label = tag_labels.get(tag, tag)
        lines.append(f"| {tag} | {label} | {count} | {pct:.1f}% |")

    # Empty categories
    empty = [tag for tag in VALID_TAGS if tag not in tag_counts]
    if empty:
        lines.extend(["", "## 空分类（无图片）", ""])
        for tag in empty:
            label = tag_labels.get(tag, tag)
            lines.append(f"- {tag} ({label})")

    # Review list
    review_items = [r for r in results if r.confidence < 0.5 or (r.reason and not r.reason.startswith("api"))]
    if review_items:
        lines.extend(["", "## 需人工复审", "", "| 文件名 | 建议分类 | 置信度 | 原因 |", "|--------|----------|--------|------|"])
        for r in review_items:
            lines.append(f"| {r.filename} | {r.tag} | {r.confidence:.0%} | {r.reason} |")

    # Failed list
    failed_items = [r for r in results if r.reason.startswith("api") or r.reason.startswith("encode")]
    if failed_items:
        lines.extend(["", "## API 失败", "", "| 文件名 | 错误 |", "|--------|------|"])
        for r in failed_items:
            lines.append(f"| {r.filename} | {r.reason} |")

    report_text = "\n".join(lines)

    if dry_run:
        logger.info("[DRY RUN] Report would be:")
        print(report_text[:2000])
    else:
        REPORT_FILE.write_text(report_text, encoding="utf-8")
        logger.info(f"Report saved: {REPORT_FILE}")

    return report_text


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Sticker image classifier using Kimi Vision API")
    parser.add_argument("--step", choices=["preprocess", "classify", "report", "all"],
                        default="all", help="Which step to run (default: all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't actually move files")
    args = parser.parse_args()

    if args.step in ("preprocess", "all"):
        images = step_preprocess()
    else:
        # For classify/report only, scan existing valid images
        images = [
            f for f in DATA_IMAGES.iterdir()
            if f.is_file() and f.suffix.lower() in VALID_EXTS
            and not f.name.startswith(".") and not f.name.startswith("_")
        ]

    if not images:
        logger.warning("No images to classify!")
        return

    results: list[ClassificationResult] = []

    if args.step in ("classify", "all"):
        results = asyncio.run(step_classify(images, dry_run=args.dry_run))
    elif args.step == "report":
        # Load from progress
        if PROGRESS_FILE.exists():
            progress = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
            results = []
            for fn, r in progress.get("results", {}).items():
                results.append(ClassificationResult(
                    filename=fn,
                    tag=r["tag"],
                    confidence=r["confidence"],
                    description=r["description"],
                    reason=r.get("reason", ""),
                ))
            for fn, reason in progress.get("failed", {}).items():
                results.append(ClassificationResult(
                    filename=fn, tag="", confidence=0.0,
                    description="", reason=reason,
                ))

    if args.step in ("all",) and results:
        tag_counts = step_move(results, dry_run=args.dry_run)
        step_report(results, tag_counts, dry_run=args.dry_run)
    elif args.step == "report" and results:
        # Build tag counts from results
        tag_counts = {}
        for r in results:
            if r.tag and r.confidence >= 0.5 and not r.reason:
                tag_counts[r.tag] = tag_counts.get(r.tag, 0) + 1
        step_report(results, tag_counts, dry_run=args.dry_run)

    logger.info("Done!")


if __name__ == "__main__":
    main()
