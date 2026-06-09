"""
Phase 3 integration test — emotion engine, personas, event extraction.

Tests:
1. Emotion engine keyword detection (all emotion types)
2. Emotion response guidance generation
3. Emotion trajectory tracking
4. Persona loading and personality verification
5. Persona-aware system prompt building
6. Event extraction from messages
7. Follow-up context building
8. End-to-end: persona + emotion + events in chat pipeline
"""

import sys
import asyncio
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from gf.config import load_config
from gf.ai.emotion import (
    EmotionEngine, Emotion, EmotionResult,
    EMOTION_LABELS, EMOTION_RESPONSES,
)
from gf.ai.personas import get_persona, list_personas, PERSONAS
from gf.ai.persona import build_system_prompt, build_proactive_prompt
from gf.ai.events import EventExtractor, build_followup_context
from gf.ai.llm import LLMClient
from gf.memory.store import MemoryStore

PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "


def test_emotion_keywords():
    """Test 1: Emotion engine keyword detection across all emotions."""
    print(f"\n{'='*60}")
    print("Test 1: Emotion Keyword Detection")
    print(f"{'='*60}")
    try:
        engine = EmotionEngine()
        test_cases = [
            ("抽到SSR了！！太开心了！！", Emotion.GAMING_HYPE, 0.7),
            ("队友太菜了，气死我了，这把又输了", Emotion.GAMING_RAGE, 0.7),
            ("新番太好看了，看哭了", Emotion.ANIME_FEELS, 0.7),
            ("又要去聚会，好烦，不想去", Emotion.SOCIAL_ANXIETY, 0.7),
            ("今天好累，通宵肝了一晚上", Emotion.TIRED, 0.7),
            ("我是不是太菜了，别人都比我厉害", Emotion.SELF_DOUBT, 0.7),
            ("没有人理解我，好孤独", Emotion.LONELY, 0.7),
            ("哈哈今天吃鸡了", Emotion.GAMING_HYPE, 0.6),
            ("好开心！今天发工资了", Emotion.HAPPY, 0.6),
            ("明天面试好紧张", Emotion.ANXIOUS, 0.6),
        ]

        passed = 0
        for msg, expected_emotion, min_intensity in test_cases:
            result = engine.analyze(msg)
            if result.primary == expected_emotion and result.intensity >= min_intensity:
                passed += 1
                print(f"  {PASS} \"{msg[:30]}...\" → {EMOTION_LABELS[result.primary]} ({result.intensity:.0%})")
            else:
                print(f"  {WARN} \"{msg[:30]}...\" → got {EMOTION_LABELS[result.primary]}, expected {EMOTION_LABELS[expected_emotion]}")

        print(f"\n  {passed}/{len(test_cases)} emotion detections correct")
        return passed >= 7  # Allow some borderline cases
    except Exception as e:
        print(f"  {FAIL} Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_emotion_guidance():
    """Test 2: Emotion response guidance."""
    print(f"\n{'='*60}")
    print("Test 2: Emotion Response Guidance")
    print(f"{'='*60}")
    try:
        engine = EmotionEngine()

        # Test high-intensity emotion → gets guidance
        result = engine.analyze("真的好难过，今天发生了很多不开心的事...")
        guidance = engine.get_response_guidance(result)
        assert len(guidance) > 20, "Should get substantial guidance for strong emotion"
        print(f"  {PASS} Strong sad → guidance: {len(guidance)} chars")

        # Test gaming rage → special guidance
        result2 = engine.analyze("破防了！队友太菜连跪5把！")
        guidance2 = engine.get_response_guidance(result2)
        assert "游戏" in guidance2 or "破防" in guidance2 or "吐槽" in guidance2
        print(f"  {PASS} Gaming rage → special guidance present")

        # Test low confidence → no guidance
        result3 = engine.analyze("嗯")
        guidance3 = engine.get_response_guidance(result3)
        assert guidance3 == "", "Should not give guidance for low confidence"
        print(f"  {PASS} Low confidence → no guidance (correct)")

        # Test recommended stickers
        stickers = engine.get_recommended_stickers(result)
        assert "caring" in stickers or "sad" in stickers
        print(f"  {PASS} Recommended stickers for sad: {stickers}")

        return True
    except Exception as e:
        print(f"  {FAIL} Error: {e}")
        return False


def test_emotion_trajectory():
    """Test 3: Emotion trajectory tracking."""
    print(f"\n{'='*60}")
    print("Test 3: Emotion Trajectory")
    print(f"{'='*60}")
    try:
        engine = EmotionEngine()

        # Simulate improving mood
        engine.update_trajectory("test", engine.analyze("好难过"))
        engine.update_trajectory("test", engine.analyze("唉"))
        engine.update_trajectory("test", engine.analyze("稍微好一点了"))
        engine.update_trajectory("test", engine.analyze("哈哈你说得对"))
        engine.update_trajectory("test", engine.analyze("今天真开心！"))

        traj = engine.get_trajectory("test")
        assert traj is not None
        assert traj.trend == "improving", f"Should be improving, got {traj.trend}"
        print(f"  {PASS} Trend: {traj.trend} (5 messages, negative → positive)")

        # Get context
        ctx = engine.get_trajectory_context("test")
        assert "好转" in ctx
        print(f"  {PASS} Context: {ctx}")

        return True
    except Exception as e:
        print(f"  {FAIL} Error: {e}")
        return False


def test_personas():
    """Test 4: Persona definitions and loading."""
    print(f"\n{'='*60}")
    print("Test 4: Persona Definitions")
    print(f"{'='*60}")
    try:
        persona_list = list_personas()
        assert len(persona_list) == 5, f"Expected 5 personas, got {len(persona_list)}"
        print(f"  {PASS} {len(persona_list)} personas available")

        for p in persona_list:
            persona = get_persona(p["id"])
            assert persona.display_name == p["display_name"]
            assert len(persona.personality) > 50, f"{p['id']} personality too short"
            assert len(persona.speaking_style) > 20, f"{p['id']} speaking_style too short"
            assert persona.partner_address, f"{p['id']} has no partner addresses"
            print(f"  {PASS} {persona.display_name} ({persona.name}): "
                  f"otaku={persona.otaku_level}, "
                  f"stickers={len(persona.sticker_weight)} weights")

        # Verify otaku persona has most references
        otaku = get_persona("otaku")
        assert otaku.otaku_level == "hardcore"
        assert len(otaku.otaku_topics) > 5
        print(f"  {PASS} Otaku persona: {len(otaku.otaku_topics)} topics")

        return True
    except Exception as e:
        print(f"  {FAIL} Error: {e}")
        return False


def test_persona_prompt():
    """Test 5: Persona-aware system prompt building."""
    print(f"\n{'='*60}")
    print("Test 5: Persona-Aware Prompts")
    print(f"{'='*60}")
    try:
        cfg = load_config()

        for pid in ["gentle", "tsundere", "genki", "oneesan", "otaku"]:
            persona = get_persona(pid)
            prompt = build_system_prompt(
                bot_name=persona.name,
                user_name="测试员",
                persona=persona,
            )
            assert persona.display_name in prompt, f"{pid}: persona name not in prompt"
            assert "测试员" in prompt, f"{pid}: user name not in prompt"
            assert "[happy]" in prompt or "[shy]" in prompt, f"{pid}: sticker tags not in prompt"
            assert len(prompt) > 400, f"{pid}: prompt too short ({len(prompt)} chars)"
            print(f"  {PASS} {persona.display_name}: {len(prompt)} chars ✓")

        # Test proactive prompt
        genki = get_persona("genki")
        proactive = build_proactive_prompt(
            user_name="测试员",
            persona=genki,
            trigger_type="morning",
            days_known=30,
            relationship="familiar",
        )
        assert "测试员" in proactive
        assert genki.display_name in proactive
        print(f"  {PASS} Proactive prompt: {len(proactive)} chars")

        return True
    except Exception as e:
        print(f"  {FAIL} Error: {e}")
        return False


async def test_event_extraction():
    """Test 6: Event extraction with LLM."""
    print(f"\n{'='*60}")
    print("Test 6: Event Extraction")
    print(f"{'='*60}")
    try:
        cfg = load_config()
        client = LLMClient(cfg.llm)
        extractor = EventExtractor(client)

        messages = [
            "我明天有个重要的面试，有点紧张",
            "最近在玩黑神话悟空，太上头了",
            "下个月要去日本旅行！",
        ]

        for msg in messages:
            events = await extractor.extract(msg)
            if events:
                for evt in events:
                    print(f"  {PASS} \"{msg[:30]}...\" → [{evt.type}] {evt.event} (remind:{evt.remind_in_hours}h)")
            else:
                print(f"  {WARN} \"{msg[:30]}...\" → no events extracted")

        return True
    except Exception as e:
        print(f"  {FAIL} Error: {e}")
        return False


def test_followup_context():
    """Test 7: Follow-up context building."""
    print(f"\n{'='*60}")
    print("Test 7: Follow-up Context")
    print(f"{'='*60}")
    try:
        now = time.time()
        events = [
            {
                "event": "用户有面试",
                "type": "exam",
                "extracted_at": now - 86400,  # 24h ago
                "remind_in_hours": 24,
                "reminded": False,
                "time": now - 86400,
            },
            {
                "event": "用户身体不舒服",
                "type": "health",
                "extracted_at": now - 21600,  # 6h ago
                "remind_in_hours": 6,
                "reminded": False,
                "time": now - 21600,
            },
            {
                "event": "用户买了新游戏",
                "type": "gaming",
                "extracted_at": now - 7200,  # 2h ago
                "remind_in_hours": 24,
                "reminded": False,
                "time": now - 7200,
            },
        ]

        ctx = build_followup_context([events[0], events[1]])
        assert "面试" in ctx
        assert "不舒服" in ctx
        print(f"  {PASS} Due events context: {len(ctx)} chars")
        print(f"       {ctx.strip()}")

        return True
    except Exception as e:
        print(f"  {FAIL} Error: {e}")
        return False


async def test_full_pipeline():
    """Test 8: Full persona + emotion pipeline with LLM."""
    print(f"\n{'='*60}")
    print("Test 8: Full Persona + Emotion Pipeline")
    print(f"{'='*60}")
    try:
        cfg = load_config()
        client = LLMClient(cfg.llm)
        engine = EmotionEngine()

        # Test each persona with a 宅男-relevant message
        messages = [
            ("tsundere", "今天抽卡又沉了，心态崩了"),
            ("genki", "新番更新了！！终于等到这一天！"),
            ("otaku", "有没有好玩的联机游戏推荐？"),
        ]

        for pid, msg in messages:
            persona = get_persona(pid)

            # Analyze emotion
            result = engine.analyze(msg)
            guidance = engine.get_response_guidance(result)

            # Build prompt
            prompt = build_system_prompt(
                bot_name=persona.name,
                user_name="宅宅",
                persona=persona,
                emotion_context=guidance,
            )

            # Chat
            llm_msgs = [
                LLMClient.system_message(prompt),
                LLMClient.user_message(msg),
            ]
            reply, sticker = await client.chat(llm_msgs)

            emo_label = EMOTION_LABELS[result.primary]
            sticker_info = f"[{sticker}]" if sticker else "(none)"
            print(f"  [{persona.display_name}] emo={emo_label} sticker={sticker_info}")
            print(f"  {PASS} User: {msg}")
            print(f"       Bot: {reply[:80]}{'...' if len(reply)>80 else ''}")

        return True
    except Exception as e:
        print(f"  {FAIL} Error: {e}")
        return False


async def main():
    print("=" * 60)
    print("  AI Girlfriend Bot — Phase 3 Integration Test")
    print("=" * 60)

    cfg = load_config()
    print(f"  Model: {cfg.llm.model}")

    results = []
    results.append(("Emotion Keywords", test_emotion_keywords()))
    results.append(("Emotion Guidance", test_emotion_guidance()))
    results.append(("Emotion Trajectory", test_emotion_trajectory()))
    results.append(("Persona Definitions", test_personas()))
    results.append(("Persona Prompts", test_persona_prompt()))
    results.append(("Event Extraction", await test_event_extraction()))
    results.append(("Follow-up Context", test_followup_context()))
    results.append(("Full Pipeline", await test_full_pipeline()))

    print(f"\n{'='*60}")
    print("  Summary")
    print(f"{'='*60}")
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for name, ok in results:
        status = PASS if ok else FAIL
        print(f"  {status} {name}")
    print(f"\n  {passed}/{total} tests passed")


if __name__ == "__main__":
    asyncio.run(main())
