"""Chat commands — persona selection, sticker ban, admin management."""

import logging
import shutil
from typing import Optional
from ..ai.personas import get_persona, get_persona_selection_text

logger = logging.getLogger(__name__)

# ---- Ban ----

_BAN_PATTERNS = [
    "不喜欢这个表情包", "删掉这个表情包", "不要发这个了",
    "换一个", "这个表情包不好", "拉黑这个表情包",
]


def is_ban_command(msg: str) -> bool:
    return any(p in msg for p in _BAN_PATTERNS)


async def handle_ban(user_id: str, last_sticker: dict, memory, qq_client) -> None:
    last = last_sticker.get(user_id)
    if last:
        memory.ban_sticker(user_id, last)
        await qq_client.send_private_msg(user_id, "好哒，以后不发这个了 (｡･ω･｡)")
        logger.info(f"User {user_id} banned sticker: {last}")
    else:
        await qq_client.send_private_msg(user_id, "嗯？你指的是哪个表情包呀～")


# ---- Admin ----

def is_admin_command(msg: str) -> bool:
    return any(c in msg for c in ["添加表情包", "表情包分类", "表情包统计", "删除表情包"])


async def handle_admin_cmd(user_id: str, message: str, stickers, qq_client, cfg,
                           last_sticker: dict) -> None:
    if "表情包分类" in message:
        cats = stickers.category_counts()
        lines = [f"📁 表情包分类（{len(cats)}个）："]
        for tag, count in sorted(cats.items(), key=lambda x: -x[1]):
            meta = stickers.get_meta(tag)
            label = meta.get("label", tag) if meta else tag
            lines.append(f"  [{tag}] {label}: {count}张")
        await qq_client.send_private_msg(user_id, "\n".join(lines))

    elif "表情包统计" in message:
        counts = stickers.category_counts()
        total = sum(counts.values())
        lines = [f"📊 共{total}张，{len(counts)}个分类有图"]
        top5 = sorted(counts.items(), key=lambda x: -x[1])[:5]
        lines.append("Top5: " + ", ".join(f"{t}({c})" for t, c in top5))
        await qq_client.send_private_msg(user_id, "\n".join(lines))

    elif "删除表情包" in message:
        last = last_sticker.get("admin_last")
        if last:
            for tag in stickers.list_categories():
                target = stickers.stickers_dir / tag / last
                if target.exists():
                    target.unlink()
                    stickers.refresh()
                    await qq_client.send_private_msg(user_id, f"已删除 [{tag}] {last}")
                    return
        await qq_client.send_private_msg(user_id, "没有要删除的表情包")

    elif "添加表情包" in message:
        await qq_client.send_private_msg(
            user_id, "发图片给我，然后说「分类到 {标签}」（如：分类到 cute）")


async def classify_and_add(file_path: str, file_name: str, qq_client, cfg, stickers) -> None:
    """Admin sends an image → Kimi Vision classify → save to stickers/{tag}/."""
    import base64, io, json, httpx
    from PIL import Image
    from ..ai.sticker_meta import get_all_tags

    try:
        img = Image.open(file_path)
        if img.width > 800:
            ratio = 800 / img.width
            img = img.resize((800, int(img.height * ratio)), Image.LANCZOS)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        b64 = base64.b64encode(buf.getvalue()).decode()

        tags_str = ", ".join(get_all_tags())
        resp = await httpx.AsyncClient(timeout=60).post(
            f"{cfg.llm.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {cfg.llm.api_key}", "Content-Type": "application/json"},
            json={
                "model": cfg.llm.vision_model,
                "messages": [{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": f"判断表情包情绪。可选：{tags_str}。只输出JSON：{{\"tag\":\"xxx\",\"description\":\"描述\"}}"},
                ]}],
                "temperature": 0.3, "max_tokens": 80,
            },
        )
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        if "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            if content.startswith("json"):
                content = content[4:].strip()
        result = json.loads(content)
        tag = result.get("tag", "").strip().lower()

        if tag not in get_all_tags():
            await qq_client.send_private_msg(cfg.admin_qq, f"分类失败，未知标签: {tag}")
            return

        folder = stickers.stickers_dir / tag
        folder.mkdir(exist_ok=True)
        existing = [f for f in folder.iterdir() if f.is_file()]
        ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else "jpg"
        new_path = folder / f"{len(existing) + 1}.{ext}"
        shutil.copy(file_path, str(new_path))
        stickers.refresh()
        await qq_client.send_private_msg(cfg.admin_qq, f"✅ 已添加 [{tag}] → {new_path.name}")
        logger.info(f"Admin added sticker: {tag}/{new_path.name}")
    except Exception as e:
        logger.error(f"Admin classify failed: {e}")
        await qq_client.send_private_msg(cfg.admin_qq, f"添加失败: {e}")


# ---- Persona ----

def check_persona_cmd(message: str) -> Optional[str]:
    text = message.strip()
    m = {"1": "gentle", "2": "tsundere", "3": "genki", "4": "oneesan", "5": "otaku", "6": "coder"}
    if text in m:
        return m[text]
    n = {"温柔女友": "gentle", "温柔": "gentle", "傲娇青梅": "tsundere", "傲娇": "tsundere",
         "元气学妹": "genki", "元气": "genki", "御姐前辈": "oneesan", "御姐": "oneesan",
         "二次元同好": "otaku", "同好": "otaku",
         "码农女友": "coder", "码农": "coder", "程序员": "coder",
         "换人设": None}
    if text in n:
        return n[text]
    if "换人设" in text or "选人设" in text:
        return None
    for label, pid in n.items():
        if pid and (f"我要{label}" in text or f"选{label}" in text):
            return pid
    return None


async def handle_persona(user_id: str, persona_id: Optional[str], memory, qq_client) -> None:
    if persona_id is None:
        await qq_client.send_private_msg(user_id, get_persona_selection_text())
        return
    persona = get_persona(persona_id)
    memory.set_persona(user_id, persona_id)
    memory.add_message(user_id, "user", f"选择人设：{persona.display_name}")
    await qq_client.send_private_msg(
        user_id, f"好呀～以后我就是你的**{persona.display_name}**「{persona.name}」啦！\n\n"
        f"{persona.tagline}\n\n随时说「换人设」来重新选择哦～")
    memory.add_message(user_id, "assistant", f"已切换人设到{persona.display_name}")


# ---- Helpers ----

def is_any_command(message: str) -> bool:
    text = message.strip()
    if text == "/":
        return False
    return is_ban_command(text) or is_admin_command(text) or \
           check_persona_cmd(text) is not None or \
           text in ("换人设", "选人设", "切换人设")
