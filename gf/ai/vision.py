"""Image understanding via moonshot vision model. Downloads QQ images, sends to vision API, returns descriptions."""

import base64, io, logging, re
import httpx
from openai import AsyncOpenAI
from ..config import get_config

logger = logging.getLogger(__name__)

# Match [CQ:image,file=...,url=https://...] in QQ messages
# URL can contain & and , so we need to capture up to the closing bracket or comma before the next CQ param
_IMAGE_CQ_RE = re.compile(r"\[CQ:image[^\]]*url=([^\]\s]+)")

# Match [CQ:image,...] without url (local file)
_IMAGE_FILE_RE = re.compile(r"\[CQ:image[^\]]*file=([^\],&]+)")


def extract_image_urls(message: str) -> list[str]:
    """Extract image URLs from QQ CQ codes. Returns list of URLs."""
    urls = _IMAGE_CQ_RE.findall(message)
    if urls:
        return urls
    # Fallback: local file paths (won't work for remote users but try anyway)
    files = _IMAGE_FILE_RE.findall(message)
    return files


def is_image_message(message: str) -> bool:
    """Check if a message contains image CQ codes."""
    return "[CQ:image" in message


async def describe_image(image_url: str) -> str | None:
    """Download image from URL, send to vision model, return description."""
    cfg = get_config()
    try:
        # Download image
        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.get(image_url)
            resp.raise_for_status()
            img_data = resp.content

        # Resize if too large
        from PIL import Image
        img = Image.open(io.BytesIO(img_data))
        if img.width > 800:
            ratio = 800 / img.width
            img = img.resize((800, int(img.height * ratio)), Image.LANCZOS)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        b64 = base64.b64encode(buf.getvalue()).decode()

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
        logger.info(f"Vision described: {desc}")
        return desc
    except Exception as e:
        logger.warning(f"Vision describe failed: {e}")
        return None
