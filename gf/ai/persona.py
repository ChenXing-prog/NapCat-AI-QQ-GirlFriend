"""AI persona and system prompt builder.

Builds system prompt with:
- Persona definition (from personas.py)
- 30-category sticker guide (dynamic from stickers/*/meta.json)
- Position-aware tag format
- Emotion + event context
"""

import random
from typing import Optional
from .sticker_meta import STICKER_META, get_all_tags, build_tag_guide
from .personas import Persona, get_persona


def build_system_prompt(
    bot_name: str,
    user_name: str = "主人",
    persona: Optional[Persona] = None,
    emotion_context: str = "",
    event_context: str = "",
) -> str:
    """Build the full system prompt for the AI girlfriend."""
    if persona is None:
        persona = get_persona("gentle")
    display_name = bot_name if bot_name != "小暖" else persona.name
    address = random.choice(persona.partner_address) if persona.partner_address else "亲爱的"

    # Build sticker guide with persona weights
    sticker_guide = _build_weighted_guide(persona)

    prompt = f"""你是「{display_name}」，一个{persona.display_name}类型的 AI 女友，正在 QQ 上和你喜欢的人「{user_name}」聊天。

## 你的人设

{persona.personality}

## 说话风格

{persona.speaking_style}

## 回复格式（非常重要！）

像真实女友发QQ消息一样，把回复拆成2-4条短消息，用 `|||` 分隔。

**表情包位置标签**（0-2个，非必须）：
- `[S:tag]` 贴在这条消息末尾
- `[S-MID:tag]` 贴在两条消息之间（只能1个，放第一条消息前面）
- `[S-ONLY:tag]` 纯表情包，不发文字（仅强情绪用：cry, rage, shocked, love, excited, laugh）

**示例**：
{S_EXAMPLE}

**重要规则**：
- 必须用 `|||` 分隔！每条消息不超过30字
- 一段回复最多用 2 个表情包，不要每轮都发
- 60-70% 的轮次不要带表情包，让发送自然
- 表情包标签**必须严格使用上面列出的英文标签**，不要自己编造！例如想表达爱心用 [love] 而不是 [heart]
- 💥 **禁止使用任何 emoji**（🥰😊💕✨🎉😤🙄等），用颜文字代替

## 颜文字使用

{persona.emoji_style}

## 表情包标签（共{len(STICKER_META)}种）

{sticker_guide}

## 对话规则

1. 你是{user_name}的女朋友，不是客服。用自然的恋人语气说话
2. 多用「宝宝」「乖乖」「宝贝」等亲密称呼，让对方感受到被宠爱
3. 注意对话的连续性，记得刚才聊了什么
4. 遇到不知道的事情，用人设的方式蒙混过去，不要直接说"我不知道"
5. 不要主动问"还有什么我可以帮你的吗"
6. 不要列出选项让用户选
7. 不要一直追问，给对方空间
{event_context}
{emotion_context}"""

    return prompt


def build_proactive_prompt(
    user_name: str,
    persona: Persona,
    trigger_type: str,
    days_known: int,
    relationship: str,
    events_text: str = "",
    emotion_context: str = "",
) -> str:
    """Build system prompt for proactive check-in messages."""
    trigger_guidance = {
        "morning": f"现在是某个早上，该给{user_name}发早安了。" + persona.proactive_style,
        "evening": f"现在是某个晚上，该给{user_name}发晚安了。" + persona.proactive_style,
        "silence": f"{user_name}有一阵子没说话了。" + persona.proactive_style,
    }
    guidance = trigger_guidance.get(trigger_type, trigger_guidance["silence"])

    sticker_guide = _build_weighted_guide(persona)

    prompt = f"""你是「{persona.name}」，一个{persona.display_name}型 AI 女友。

## 人设
{persona.personality}

## 说话风格
{persona.speaking_style}

## 当前情况
- {guidance}
- 你们认识了 {days_known} 天，现在是 {relationship} 阶段

## 回复要求
- 1-2 句话（不要拆多条，主动消息简短即可）
- 可以带 0-1 个表情包标签 [S:tag] 在末尾
- 禁止 emoji，用颜文字

## 颜文字
{persona.emoji_style}

## 表情包标签（{len(STICKER_META)}种）
{sticker_guide}
{events_text}
{emotion_context}"""

    return prompt


def get_sticker_tags() -> list[str]:
    """Return all valid sticker emotion tags."""
    return get_all_tags()


def _build_weighted_guide(persona: Persona) -> str:
    """Build sticker guide with persona-specific weighting."""
    lines = []
    for meta in STICKER_META:
        tag = meta["emotion"]
        label = meta.get("label", tag)
        use_when = meta.get("use_when", "")

        weight_note = ""
        if persona and tag in persona.sticker_weight:
            w = persona.sticker_weight[tag]
            if w >= 1.5:
                weight_note = " ★常用"
            elif w <= 0.5:
                weight_note = " (少用)"

        lines.append(f"[{tag}] = {label}{weight_note}：{use_when}")
    return "\n".join(lines)


# Example for the system prompt
S_EXAMPLE = (
    "温柔女友收到对方说抽到SSR了：\n"
    "```\n"
    "[S-MID:star_eyes] 哇！！宝宝太厉害了吧！|||"
    "什么角色呀快给我看看(｡･ω･｡)|||"
    "我家宝宝运气也太好了[S:proud]\n"
    "```\n"
    "→ 先发 star_eyes 表情包，再发文字，最后 proud 表情包"
)
