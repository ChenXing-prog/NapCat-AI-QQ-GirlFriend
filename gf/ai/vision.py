"""Image understanding via NapCat get_file + moonshot vision model."""

import base64, io, logging, re
import httpx
from openai import AsyncOpenAI
from PIL import Image
from ..config import get_config

logger = logging.getLogger(__name__)

# Match file_id from [CQ:image,file=XXXX.jpg,...]
_IMAGE_FILE_RE = re.compile(r"\[CQ:image[^\]]*file=([A-Za-z0-9]+\.[a-z]+)")


def extract_file_ids(message: str) -> list[str]:
    """Extract file IDs from QQ CQ:image codes."""
    return _IMAGE_FILE_RE.findall(message)


def is_image_message(message: str) -> bool:
    """Check if a message contains image CQ codes."""
    return "[CQ:image" in message


async def describe_image(file_id: str) -> str | None:
    """Read image via NapCat get_file (gets local path), send to vision model."""
    cfg = get_config()
    try:
        # Step 1: Get local file path from NapCatQQ
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.post(
                f"{cfg.napcat.base_url}/get_file",
                json={"file_id": file_id},
            )
            data = resp.json()
            if data.get("status") != "ok":
                logger.warning(f"NapCat get_file failed for {file_id}: {data}")
                return None
            local_path = data.get("data", {}).get("file", "")
            if not local_path:
                return None

        # Step 2: Read local file, resize, encode
        img = Image.open(local_path)
        if img.width > 800:
            ratio = 800 / img.width
            img = img.resize((800, int(img.height * ratio)), Image.LANCZOS)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        b64 = base64.b64encode(buf.getvalue()).decode()

        # Step 3: Vision API
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
        return desc
    except Exception as e:
        logger.warning(f"Vision describe failed for {file_id}: {e}")
        return None
