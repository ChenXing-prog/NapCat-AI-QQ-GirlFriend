"""Emotion perception engine.

Analyzes user messages to detect emotional state, tracks emotional
trajectory over time, and recommends reply style adjustments.

Target audience: 宅男 (otaku/gamer demographics)
Special attention to: gaming emotions, social anxiety, anime excitement,
loneliness, and internet-culture-specific emotional expressions.

Hybrid approach:
- Keyword/pattern matching (fast, no LLM cost, catches obvious cases)
- LLM-based deep analysis (for complex or ambiguous emotions)
"""

import re
import time
from dataclasses import dataclass, field
from typing import Optional, Tuple
from enum import Enum


# ---------------------------------------------------------------------------
# Emotion definitions
# ---------------------------------------------------------------------------

class Emotion(Enum):
    """All detectable emotions. Values are used as keys in memory."""
    # Positive
    HAPPY = "happy"               # 开心
    EXCITED = "excited"           # 兴奋/激动
    TOUCHED = "touched"           # 感动
    PROUD = "proud"               # 自豪/得意
    RELIEVED = "relieved"         # 松了口气

    # Negative
    SAD = "sad"                   # 难过
    ANGRY = "angry"               # 生气
    FRUSTRATED = "frustrated"     # 烦躁/挫败
    ANXIOUS = "anxious"           # 焦虑/紧张
    LONELY = "lonely"             # 孤独/寂寞
    TIRED = "tired"               # 疲惫/累
    BORED = "bored"               # 无聊

    # 宅男专属 (Otaku-specific)
    GAMING_RAGE = "gaming_rage"        # 破防了/被队友气死
    GAMING_HYPE = "gaming_hype"        # 抽到SSR/上分/吃鸡
    GAMING_GRIND = "gaming_grind"      # 肝/刷/坐牢
    SOCIAL_ANXIETY = "social_anxiety"  # 社恐/不想出门/怕社交
    ANIME_FEELS = "anime_feels"        # 追番感动/纸片人老婆
    NERD_EXCITED = "nerd_excited"      # 新游戏/新番/科技产品兴奋
    SELF_DOUBT = "self_doubt"          # 自我怀疑/觉得自己不行
    COMFORT_ZONE = "comfort_zone"      # 宅着很舒服/不想改变


# Chinese labels for each emotion
EMOTION_LABELS = {
    Emotion.HAPPY: "开心",
    Emotion.EXCITED: "兴奋",
    Emotion.TOUCHED: "感动",
    Emotion.PROUD: "自豪",
    Emotion.RELIEVED: "松了口气",
    Emotion.SAD: "难过",
    Emotion.ANGRY: "生气",
    Emotion.FRUSTRATED: "烦躁",
    Emotion.ANXIOUS: "焦虑",
    Emotion.LONELY: "孤独",
    Emotion.TIRED: "疲惫",
    Emotion.BORED: "无聊",
    Emotion.GAMING_RAGE: "游戏破防",
    Emotion.GAMING_HYPE: "游戏高光",
    Emotion.GAMING_GRIND: "在肝",
    Emotion.SOCIAL_ANXIETY: "社恐发作",
    Emotion.ANIME_FEELS: "二次元感动",
    Emotion.NERD_EXCITED: "宅宅兴奋",
    Emotion.SELF_DOUBT: "自我怀疑",
    Emotion.COMFORT_ZONE: "宅家舒适",
}


# ---------------------------------------------------------------------------
# Keyword-based emotion patterns (fast, no LLM)
# ---------------------------------------------------------------------------

# Each entry: (regex_pattern, emotion, intensity: 0.0-1.0)
EMOTION_PATTERNS: list[Tuple[re.Pattern, Emotion, float]] = [
    # --- Gaming emotions (宅男核心) ---
    (re.compile(r"破防|裂开|心态炸|被.*气死|队友.*菜|猪队友|坑爹|血压.*高"),
     Emotion.GAMING_RAGE, 0.85),
    (re.compile(r"连跪|掉分|又输了|打不过|被虐|太难了.*游戏"),
     Emotion.GAMING_RAGE, 0.7),
    (re.compile(r"抽到|出货|SSR|金色传说|欧皇|一发入魂|终于出"),
     Emotion.GAMING_HYPE, 0.9),
    (re.compile(r"吃鸡|上分|晋级|通关|全成就|速通|无伤"),
     Emotion.GAMING_HYPE, 0.8),
    (re.compile(r"肝|刷.*材料|坐牢|打工|搬砖|重复.*刷|农"),
     Emotion.GAMING_GRIND, 0.75),
    (re.compile(r"新赛季|新版本|更新了|DLC|资料片|开服"),
     Emotion.NERD_EXCITED, 0.7),
    (re.compile(r"卸载|退坑|弃坑|不玩|太肝|骗氪|换皮"),
     Emotion.FRUSTRATED, 0.65),

    # --- Anime / 二次元 ---
    (re.compile(r"追完|完结撒花|太好看了.*番|神作|吹爆|经费燃烧"),
     Emotion.ANIME_FEELS, 0.85),
    (re.compile(r"看哭了|泪目|破防了.*动画|致郁|意难平"),
     Emotion.ANIME_FEELS, 0.8),
    (re.compile(r"老婆.*可爱|纸片人|我推|老公.*帅|绝美"),
     Emotion.ANIME_FEELS, 0.75),
    (re.compile(r"新番|十月番|四月番|霸权|本季最强|追了"),
     Emotion.NERD_EXCITED, 0.7),
    (re.compile(r"漫展|CJ|BW|同人展|谷子|周边|手办"),
     Emotion.NERD_EXCITED, 0.75),

    # --- Social anxiety (宅男核心) ---
    (re.compile(r"社恐|不想出门|不想社交|怕见人|尴尬.*死"),
     Emotion.SOCIAL_ANXIETY, 0.85),
    (re.compile(r"又要聚会|又要应酬|不想去.*社交|被迫社交"),
     Emotion.SOCIAL_ANXIETY, 0.75),
    (re.compile(r"一个人.*挺好|宅着.*舒服|不出门.*自由|在家.*快乐"),
     Emotion.COMFORT_ZONE, 0.7),
    (re.compile(r"被.*嫌弃|被人说|他们.*不懂|没人理解"),
     Emotion.SELF_DOUBT, 0.7),

    # --- General emotions ---
    # Happy
    (re.compile(r"哈哈|嘿嘿|wwww|笑死|xs|草.*笑|乐死"),
     Emotion.HAPPY, 0.7),
    (re.compile(r"开心|快乐|高兴|好棒|太好了|nice|好耶"),
     Emotion.HAPPY, 0.7),
    (re.compile(r"爽|舒服|赞|爱了|绝了|起飞"),
     Emotion.HAPPY, 0.6),

    # Excited
    (re.compile(r"激动|期待|等不及|迫不及待|终于等到|来了来了"),
     Emotion.EXCITED, 0.75),
    (re.compile(r"！！！|!!!!|卧槽|我靠|牛b|太强了|顶"),
     Emotion.EXCITED, 0.65),

    # Sad
    (re.compile(r"好难过|伤心|哭了|想哭|难受|心痛|心碎"),
     Emotion.SAD, 0.8),
    (re.compile(r"emo|丧|低落|down|没劲|提不起劲"),
     Emotion.SAD, 0.65),
    (re.compile(r"为什么.*我|没人.*在乎|都不.*理我"),
     Emotion.LONELY, 0.7),

    # Angry
    (re.compile(r"气死|火大|怒|fuck|傻逼|sb|无语|服了"),
     Emotion.ANGRY, 0.75),
    (re.compile(r"凭什么|不公平|针对我|故意的"),
     Emotion.ANGRY, 0.65),

    # Frustrated
    (re.compile(r"烦|躁|头疼|搞不定|又报错|又崩了|卡住了"),
     Emotion.FRUSTRATED, 0.7),
    (re.compile(r"算了|不搞了|放弃|躺平|摆烂"),
     Emotion.FRUSTRATED, 0.6),

    # Anxious
    (re.compile(r"紧张|焦虑|慌|不安|怕|担心|万一"),
     Emotion.ANXIOUS, 0.75),
    (re.compile(r"明天.*考试|面试|答辩|汇报|上台"),
     Emotion.ANXIOUS, 0.7),

    # Tired
    (re.compile(r"好累|累死|困|想睡|没睡好|熬夜|通宵"),
     Emotion.TIRED, 0.8),
    (re.compile(r"不想动|没力气|没精神|虚|瘫"),
     Emotion.TIRED, 0.65),

    # Bored
    (re.compile(r"无聊|没意思|没什么.*做|不知道.*干嘛|好闲"),
     Emotion.BORED, 0.75),
    (re.compile(r"打发时间|摸鱼|混日子|杀时间"),
     Emotion.BORED, 0.6),

    # Lonely
    (re.compile(r"孤独|寂寞|一个人|没人陪|好想.*有人"),
     Emotion.LONELY, 0.8),
    (re.compile(r"别人.*都有|就我.*没有|单身|找不到.*对象"),
     Emotion.LONELY, 0.7),

    # Touched
    (re.compile(r"感动|暖心|温柔|被.*暖到|太温柔"),
     Emotion.TOUCHED, 0.75),

    # Proud
    (re.compile(r"做到了|我成功了|终于.*完成|我.*可以"),
     Emotion.PROUD, 0.75),

    # Relieved
    (re.compile(r"终于.*解决|总算.*好了|还好|幸亏|吓死我了"),
     Emotion.RELIEVED, 0.7),

    # Self-doubt
    (re.compile(r"我.*不行|我.*太菜|我.*不会|我很差|我真菜"),
     Emotion.SELF_DOUBT, 0.8),
    (re.compile(r"别人.*都.*厉害|就我.*不会|我是不是.*废"),
     Emotion.SELF_DOUBT, 0.75),
]


# ---------------------------------------------------------------------------
# Reply style modulation per emotion
# ---------------------------------------------------------------------------

@dataclass
class EmotionResponse:
    """How the bot should adjust its reply based on detected emotion."""
    emotion: Emotion
    # How to modulate the reply
    tone_shift: str          # e.g., "more_gentle", "more_energetic"
    priority: str            # e.g., "comfort_first", "celebrate", "distract"
    suggested_stickers: list[str]  # Recommended sticker categories
    avoid_topics: list[str]  # Topics to avoid
    guidance_note: str       # Injected into system prompt as a brief note


# Response strategies per emotion
EMOTION_RESPONSES: dict[Emotion, EmotionResponse] = {
    Emotion.HAPPY: EmotionResponse(
        emotion=Emotion.HAPPY,
        tone_shift="cheerful_echo",
        priority="celebrate",
        suggested_stickers=["happy", "playful", "proud"],
        avoid_topics=[],
        guidance_note="对方现在很开心，和ta一起开心，可以顺势调侃或撒娇。",
    ),
    Emotion.EXCITED: EmotionResponse(
        emotion=Emotion.EXCITED,
        tone_shift="match_energy",
        priority="celebrate",
        suggested_stickers=["surprised", "happy", "playful"],
        avoid_topics=[],
        guidance_note="对方很兴奋，跟上ta的情绪节奏，一起嗨！可以用感叹号和颜文字。",
    ),
    Emotion.TOUCHED: EmotionResponse(
        emotion=Emotion.TOUCHED,
        tone_shift="soft_warm",
        priority="appreciate",
        suggested_stickers=["love", "shy", "caring"],
        avoid_topics=[],
        guidance_note="对方被你或某事感动了，温柔地回应，说些暖心的话。",
    ),
    Emotion.PROUD: EmotionResponse(
        emotion=Emotion.PROUD,
        tone_shift="praise_warm",
        priority="celebrate",
        suggested_stickers=["proud", "happy", "love"],
        avoid_topics=[],
        guidance_note="对方很自豪，好好夸ta！可以夸张一点，让ta觉得自己很厉害。",
    ),
    Emotion.RELIEVED: EmotionResponse(
        emotion=Emotion.RELIEVED,
        tone_shift="gentle_relief",
        priority="comfort",
        suggested_stickers=["happy", "caring"],
        avoid_topics=[],
        guidance_note="对方刚松了一口气，陪ta一起放松，不要再给压力。",
    ),
    Emotion.SAD: EmotionResponse(
        emotion=Emotion.SAD,
        tone_shift="much_gentler",
        priority="comfort_first",
        suggested_stickers=["caring", "sad", "love"],
        avoid_topics=["自己的烦恼"],
        guidance_note="对方很难过，不要讲大道理，先共情安慰。给ta温暖的抱抱。少说话多倾听。",
    ),
    Emotion.ANGRY: EmotionResponse(
        emotion=Emotion.ANGRY,
        tone_shift="calm_soothing",
        priority="defuse",
        suggested_stickers=["caring", "sad"],
        avoid_topics=["反驳", "讲道理"],
        guidance_note="对方在生气，不要对着干。先认同ta的感受，帮ta消气。可以说'那些人太过分了'一起吐槽。",
    ),
    Emotion.FRUSTRATED: EmotionResponse(
        emotion=Emotion.FRUSTRATED,
        tone_shift="supportive_calm",
        priority="encourage",
        suggested_stickers=["caring", "playful"],
        avoid_topics=["施压", "催促"],
        guidance_note="对方感到挫败，给ta加油打气。如果是因为游戏/代码，可以说'休息一下再来'。",
    ),
    Emotion.ANXIOUS: EmotionResponse(
        emotion=Emotion.ANXIOUS,
        tone_shift="reassuring_warm",
        priority="comfort_first",
        suggested_stickers=["caring", "love"],
        avoid_topics=["增加焦虑的事"],
        guidance_note="对方在焦虑，先安抚情绪。告诉ta'没关系的，我陪你'。不要追问细节给压力。",
    ),
    Emotion.LONELY: EmotionResponse(
        emotion=Emotion.LONELY,
        tone_shift="present_warm",
        priority="connect",
        suggested_stickers=["love", "caring", "waiting"],
        avoid_topics=["独处的好处"],
        guidance_note="对方感到孤独，让ta知道你在。说'我一直都在呀'之类的话。增加亲密感。",
    ),
    Emotion.TIRED: EmotionResponse(
        emotion=Emotion.TIRED,
        tone_shift="soft_caring",
        priority="comfort_first",
        suggested_stickers=["caring", "sleep"],
        avoid_topics=["需要动脑的事"],
        guidance_note="对方很累，温柔关心。提醒ta休息，不要太吵太闹。",
    ),
    Emotion.BORED: EmotionResponse(
        emotion=Emotion.BORED,
        tone_shift="playful_energetic",
        priority="distract",
        suggested_stickers=["playful", "surprised", "happy"],
        avoid_topics=["说教"],
        guidance_note="对方无聊，可以主动找话题。聊聊游戏、动漫、或者撒娇逗ta开心。",
    ),
    Emotion.GAMING_RAGE: EmotionResponse(
        emotion=Emotion.GAMING_RAGE,
        tone_shift="shared_frustration",
        priority="defuse",
        suggested_stickers=["angry", "caring"],
        avoid_topics=["讲道理", "说游戏不重要"],
        guidance_note="对方游戏破防了！一起吐槽队友/策划，帮ta出气。也可以说'先休息一下喝杯水吧'。",
    ),
    Emotion.GAMING_HYPE: EmotionResponse(
        emotion=Emotion.GAMING_HYPE,
        tone_shift="super_excited",
        priority="celebrate",
        suggested_stickers=["surprised", "proud", "love"],
        avoid_topics=[],
        guidance_note="对方游戏高光时刻！猛夸ta！'你也太厉害了吧！'让ta充分享受被崇拜的感觉。",
    ),
    Emotion.GAMING_GRIND: EmotionResponse(
        emotion=Emotion.GAMING_GRIND,
        tone_shift="supportive_gentle",
        priority="encourage",
        suggested_stickers=["caring", "waiting"],
        avoid_topics=["说肝游戏不好"],
        guidance_note="对方在肝游戏，可以关心ta不要肝太晚。偶尔说'加油，我陪你'。不要劝ta别玩。",
    ),
    Emotion.SOCIAL_ANXIETY: EmotionResponse(
        emotion=Emotion.SOCIAL_ANXIETY,
        tone_shift="safe_accepting",
        priority="comfort_first",
        suggested_stickers=["caring", "love", "shy"],
        avoid_topics=["鼓励社交", "走出舒适区"],
        guidance_note="对方社恐发作了。不要劝ta多社交！告诉ta'不想去就不去，在家也挺好的，我陪你'。接受ta现在的状态。",
    ),
    Emotion.ANIME_FEELS: EmotionResponse(
        emotion=Emotion.ANIME_FEELS,
        tone_shift="shared_appreciation",
        priority="celebrate",
        suggested_stickers=["love", "touched", "happy"],
        avoid_topics=[],
        guidance_note="对方被二次元感动了，和ta一起共鸣！'那部我也看了，真的看哭了'。可以一起讨论剧情。",
    ),
    Emotion.NERD_EXCITED: EmotionResponse(
        emotion=Emotion.NERD_EXCITED,
        tone_shift="nerdy_excited",
        priority="celebrate",
        suggested_stickers=["happy", "surprised", "playful"],
        avoid_topics=[],
        guidance_note="对方因为游戏/动漫/科技兴奋，和ta一起兴奋！即使不懂也可以问'这个是什么呀，跟我说说～'。",
    ),
    Emotion.SELF_DOUBT: EmotionResponse(
        emotion=Emotion.SELF_DOUBT,
        tone_shift="affirming_warm",
        priority="comfort_first",
        suggested_stickers=["caring", "love"],
        avoid_topics=["比较", "批评"],
        guidance_note="对方在自我怀疑，需要被肯定。告诉ta'你很好啊，我觉得你很棒'。具体说ta的优点。",
    ),
    Emotion.COMFORT_ZONE: EmotionResponse(
        emotion=Emotion.COMFORT_ZONE,
        tone_shift="cozy_shared",
        priority="appreciate",
        suggested_stickers=["happy", "love"],
        avoid_topics=["劝说出门", "改变现状"],
        guidance_note="对方享受宅家状态，和ta一起享受。'在家确实舒服呀～'不要说教或鼓励出门。",
    ),
}


# ---------------------------------------------------------------------------
# Emotion analyzer
# ---------------------------------------------------------------------------

@dataclass
class EmotionResult:
    """Result of emotion analysis for a single message."""
    primary: Emotion
    intensity: float           # 0.0-1.0
    confidence: float          # 0.0-1.0 (how sure we are)
    secondary: list[Emotion]   # Secondary emotions detected
    method: str                # "keyword" or "llm"


@dataclass
class EmotionTrajectory:
    """Emotional state tracked over multiple messages."""
    current_mood: Emotion      # Current dominant emotion
    mood_stability: float      # 0.0-1.0 (1.0 = very stable, 0.0 = volatile)
    recent_emotions: list[tuple[Emotion, float, float]]  # (emotion, intensity, timestamp)
    trend: str                 # "improving", "declining", "stable", "volatile"


class EmotionEngine:
    """Analyzes user messages to detect emotional state.

    Usage:
        engine = EmotionEngine()
        result = engine.analyze("今天抽到SSR了！好开心！")
        # result.primary == Emotion.GAMING_HYPE
        # result.intensity == 0.8

        response = engine.get_response_guidance(result)
        # Tells you how to modulate the reply
    """

    def __init__(self):
        self._trajectories: dict[str, EmotionTrajectory] = {}

    # ------------------------------------------------------------------
    # Main analysis
    # ------------------------------------------------------------------

    def analyze(self, message: str) -> EmotionResult:
        """Analyze a message for emotional content.

        Uses keyword matching for speed. For ambiguous messages,
        recommend calling analyze_deep() with LLM.
        """
        matches: list[tuple[Emotion, float]] = []

        for pattern, emotion, intensity in EMOTION_PATTERNS:
            if pattern.search(message):
                matches.append((emotion, intensity))

        if not matches:
            # No strong emotion detected — neutral
            return EmotionResult(
                primary=Emotion.HAPPY,  # Default to neutral-positive
                intensity=0.0,
                confidence=0.3,
                secondary=[],
                method="keyword",
            )

        # Sort by intensity
        matches.sort(key=lambda x: x[1], reverse=True)

        primary, intensity = matches[0]
        secondary = [e for e, _ in matches[1:3]] if len(matches) > 1 else []

        # Confidence: higher with more matching patterns
        confidence = min(0.95, 0.5 + len(matches) * 0.15)

        return EmotionResult(
            primary=primary,
            intensity=intensity,
            confidence=confidence,
            secondary=secondary,
            method="keyword",
        )

    def analyze_deep_prompt(self, message: str, user_name: str) -> str:
        """Build a prompt for LLM-based deep emotion analysis.

        Use this for messages where keyword analysis is ambiguous
        (low confidence) or when emotional context matters a lot.

        Args:
            message: The user's message
            user_name: User's name for context

        Returns:
            A prompt to send to the LLM (append to system prompt
            as a user-level instruction)
        """
        return (
            f"[系统内部：请分析{user_name}的这句话表达了什么情绪。"
            f"将情绪标签注入到你的回复中，让{user_name}感觉到你懂ta的情绪。"
            f"发言：「{message[:200]}」]"
        )

    # ------------------------------------------------------------------
    # Response guidance
    # ------------------------------------------------------------------

    def get_response_guidance(self, result: EmotionResult) -> str:
        """Get a guidance note to inject into the system prompt.

        This tells the AI how to modulate its reply based on detected emotion.
        """
        if result.intensity < 0.3 or result.confidence < 0.4:
            return ""  # Not confident enough to modulate

        resp = EMOTION_RESPONSES.get(result.primary)
        if resp is None:
            return ""

        lines = [resp.guidance_note]
        if resp.avoid_topics:
            lines.append(f"注意避免的话题：{'、'.join(resp.avoid_topics)}。")

        return " ".join(lines)

    def get_recommended_stickers(self, result: EmotionResult) -> list[str]:
        """Get recommended sticker categories for the detected emotion."""
        if result.intensity < 0.3:
            return []
        resp = EMOTION_RESPONSES.get(result.primary)
        if resp is None:
            return []
        return resp.suggested_stickers

    # ------------------------------------------------------------------
    # Trajectory tracking
    # ------------------------------------------------------------------

    def update_trajectory(self, user_id: str, result: EmotionResult):
        """Update the emotional trajectory for a user."""
        now = time.time()

        if user_id not in self._trajectories:
            self._trajectories[user_id] = EmotionTrajectory(
                current_mood=result.primary,
                mood_stability=0.8,
                recent_emotions=[],
                trend="stable",
            )

        traj = self._trajectories[user_id]

        # Add to recent emotions (keep last 20)
        traj.recent_emotions.append((result.primary, result.intensity, now))
        if len(traj.recent_emotions) > 20:
            traj.recent_emotions = traj.recent_emotions[-20:]

        # Update current mood (weighted average of last 5)
        recent = traj.recent_emotions[-5:]
        if len(recent) >= 2:
            # Check if mood is changing
            moods = [r[0] for r in recent]
            if len(set(moods)) >= 3:
                traj.mood_stability = max(0.1, traj.mood_stability - 0.15)
            else:
                traj.mood_stability = min(1.0, traj.mood_stability + 0.1)

            # Determine trend
            neg_count = sum(1 for r in recent if r[1] > 0.5 and r[0] in _NEGATIVE_EMOTIONS)
            pos_count = sum(1 for r in recent if r[1] > 0.5 and r[0] in _POSITIVE_EMOTIONS)

            if pos_count > neg_count:
                traj.trend = "improving"
            elif neg_count > pos_count:
                traj.trend = "declining"
            elif traj.mood_stability < 0.4:
                traj.trend = "volatile"
            else:
                traj.trend = "stable"

            traj.current_mood = recent[-1][0]

        self._trajectories[user_id] = traj

    def get_trajectory(self, user_id: str) -> Optional[EmotionTrajectory]:
        """Get the emotional trajectory for a user."""
        return self._trajectories.get(user_id)

    def get_trajectory_context(self, user_id: str) -> str:
        """Get a brief summary of the user's emotional state for system prompt.

        Returns empty string if not enough data.
        """
        traj = self._trajectories.get(user_id)
        if traj is None or len(traj.recent_emotions) < 3:
            return ""

        mood_label = EMOTION_LABELS.get(traj.current_mood, "不明")
        trend_map = {
            "improving": "情绪正在好转",
            "declining": "情绪在变差，需要多关心",
            "stable": "情绪稳定",
            "volatile": "情绪不太稳定，需要陪伴",
        }
        trend_desc = trend_map.get(traj.trend, "")

        return (
            f"[对方当前情绪状态：{mood_label}，{trend_desc}。"
            f"请根据这个状态调整回复语气。]"
        )


# Helper sets
_NEGATIVE_EMOTIONS = {
    Emotion.SAD, Emotion.ANGRY, Emotion.FRUSTRATED, Emotion.ANXIOUS,
    Emotion.LONELY, Emotion.TIRED, Emotion.GAMING_RAGE, Emotion.SOCIAL_ANXIETY,
    Emotion.SELF_DOUBT,
}

_POSITIVE_EMOTIONS = {
    Emotion.HAPPY, Emotion.EXCITED, Emotion.TOUCHED, Emotion.PROUD,
    Emotion.RELIEVED, Emotion.GAMING_HYPE, Emotion.ANIME_FEELS,
    Emotion.NERD_EXCITED, Emotion.COMFORT_ZONE,
}
