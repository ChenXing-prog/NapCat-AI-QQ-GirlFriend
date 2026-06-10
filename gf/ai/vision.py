"""Image understanding via NapCat get_file + moonshot vision model."""

import base64, io, logging, re
import httpx
from openai import AsyncOpenAI
from PIL import Image
from ..config import get_config

logger = logging.getLogger(__name__)

# Cache: file_id → description, to avoid duplicate vision API calls
_desc_cache: dict[str, str] = {}
_MAX_CACHE = 100

# Match file_id from [CQ:image,file=XXXX.jpg,...]
_IMAGE_FILE_RE = re.compile(r"\[CQ:image[^\]]*file=([A-Za-z0-9]+\.[a-z]+)")


def extract_file_ids(message: str) -> list[str]:
    """Extract file IDs from QQ CQ:image codes."""
    return _IMAGE_FILE_RE.findall(message)


def is_image_message(message: str) -> bool:
    """Check if a message contains image CQ codes."""
    return "[CQ:image" in message


async def describe_image(file_id: str) -> str | None:
    """Read image via NapCat get_file, send to vision model. Cached by file_id."""
    global _desc_cache
    if file_id in _desc_cache:
        logger.info(f"Vision cache hit: {file_id}")
        return _desc_cache[file_id]
    cfg = get_config()
    try:
        # Step 1: Get file info from NapCatQQ
        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.post(
                f"{cfg.napcat.base_url}/get_file",
                json={"file_id": file_id},
            )
            data = resp.json()
            if data.get("status") != "ok":
                logger.warning(f"NapCat get_file failed for {file_id}")
                return None
            info = data.get("data", {})
            local_path = info.get("file", "")

        # Step 2: Try local file first, fall back to fresh URL
        import os
        if local_path and os.path.exists(local_path):
            img = Image.open(local_path)
        else:
            fresh_url = info.get("url", "")
            if not fresh_url:
                return None
            async with httpx.AsyncClient(timeout=30) as http:
                img_resp = await http.get(fresh_url)
                img_data = img_resp.content
            img = Image.open(io.BytesIO(img_data))

        # Step 3: Resize and encode
        if img.width > 800:
            ratio = 800 / img.width
            img = img.resize((800, int(img.height * ratio)), Image.LANCZOS)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        b64 = base64.b64encode(buf.getvalue()).decode()

        # Step 4: Vision API
        client = AsyncOpenAI(api_key=cfg.llm.api_key, base_url=cfg.llm.base_url)
        resp = await client.chat.completions.create(
            model=cfg.llm.vision_model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": "简短描述这张图片。有人就描述表情动作，有字就读出来，是场景就说场景。不要超过20个字。"},
                ],
            }],
            max_tokens=50,
            temperature=0.3,
        )
        desc = resp.choices[0].message.content.strip()
        logger.info(f"Vision described [{file_id}]: {desc}")
        _desc_cache[file_id] = desc
        if len(_desc_cache) > _MAX_CACHE:
            # Drop oldest entry
            _desc_cache.pop(next(iter(_desc_cache)))
        return desc
    except Exception as e:
        logger.warning(f"Vision describe failed for {file_id}: {e}")
        return None
