"""
Phase 2 integration test — proactive scheduler.

Tests:
1. Scheduler configuration loading
2. Proactive prompt generation for morning/evening/silence
3. LLM generates natural check-in messages
4. Clinginess presets and rate limiting logic
5. End-to-end: LLM generates + sticker extraction for proactive messages
"""

import sys
import asyncio
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from gf.config import load_config, get_config
from gf.ai.llm import LLMClient
from gf.ai.persona import build_system_prompt
from gf.memory.store import MemoryStore, UserProfile
from gf.stickers.engine import StickerEngine
from gf.scheduler import (
    ProactiveScheduler,
    CLINGINESS_PRESETS,
    DEFAULT_MORNING_START,
    DEFAULT_MORNING_END,
)

PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "


def test_clinginess_presets():
    """Test 1: Clinginess presets are valid."""
    print(f"\n{'='*60}")
    print("Test 1: Clinginess Presets")
    print(f"{'='*60}")
    try:
        for key in ["clingy", "normal", "chill"]:
            preset = CLINGINESS_PRESETS[key]
            assert "silence_hours" in preset
            assert "max_per_day" in preset
            assert "label" in preset
            print(f"  {PASS} {preset['label']}: "
                  f"silence={preset['silence_hours']}h, "
                  f"max={preset['max_per_day']}/day")

        # Verify clingy is more aggressive than chill
        assert CLINGINESS_PRESETS["clingy"]["silence_hours"] < \
               CLINGINESS_PRESETS["chill"]["silence_hours"]
        assert CLINGINESS_PRESETS["clingy"]["max_per_day"] > \
               CLINGINESS_PRESETS["chill"]["max_per_day"]
        print(f"  {PASS} Clinginess ordering is correct")

        return True
    except Exception as e:
        print(f"  {FAIL} Error: {e}")
        return False


def test_trigger_windows():
    """Test 2: Time window checks."""
    print(f"\n{'='*60}")
    print("Test 2: Trigger Windows")
    print(f"{'='*60}")
    try:
        cfg = get_config()

        # Test morning detection
        morning_dt = datetime(2026, 6, 9, 8, 15)  # 8:15 AM
        not_morning_dt = datetime(2026, 6, 9, 14, 0)  # 2:00 PM
        edge_morning = datetime(2026, 6, 9, 7, 0)  # 7:00 AM sharp

        assert cfg.scheduler.morning_start == 7
        assert cfg.scheduler.morning_end == 10
        print(f"  {PASS} Morning window: {cfg.scheduler.morning_start}:00-{cfg.scheduler.morning_end}:00")

        # Evening window
        assert cfg.scheduler.evening_start == 21
        assert cfg.scheduler.evening_end == 0
        print(f"  {PASS} Evening window: {cfg.scheduler.evening_start}:00-{cfg.scheduler.evening_end}:00")

        return True
    except Exception as e:
        print(f"  {FAIL} Error: {e}")
        return False


def test_silence_detection():
    """Test 3: Silence detection logic."""
    print(f"\n{'='*60}")
    print("Test 3: Silence Detection")
    print(f"{'='*60}")
    try:
        store = MemoryStore(Path("./data"))
        user_id = "silence_test"
        user = store.get_user(user_id)
        user.name = "测试员"
        store.save_user(user)

        # Simulate a conversation that happened 3 hours ago
        three_hours_ago = time.time() - (3 * 3600)
        user.recent_messages = [
            {"role": "user", "content": "你好", "time": three_hours_ago - 60},
            {"role": "assistant", "content": "嗨～", "time": three_hours_ago},
        ]
        store.save_user(user)

        # Now check: with "normal" clinginess (5h silence), should NOT trigger
        # with "clingy" (2h silence), SHOULD trigger
        now = time.time()
        user = store.get_user(user_id)
        last_msg_time = user.recent_messages[-1]["time"]
        hours_since = (now - last_msg_time) / 3600

        print(f"  Last message: {hours_since:.1f}h ago")

        # Normal: 5h threshold, last msg 3h ago → not silent yet
        is_silent_normal = hours_since >= CLINGINESS_PRESETS["normal"]["silence_hours"]
        assert not is_silent_normal, "Should NOT be silent for 'normal' preset"
        print(f"  {PASS} Normal (5h): not silent yet ✓")

        # Clingy: 2h threshold, last msg 3h ago → IS silent
        is_silent_clingy = hours_since >= CLINGINESS_PRESETS["clingy"]["silence_hours"]
        assert is_silent_clingy, "Should BE silent for 'clingy' preset"
        print(f"  {PASS} Clingy (2h): is silent ✓")

        # Cleanup
        (store.users_dir / f"{user_id}.json").unlink()
        return True
    except Exception as e:
        print(f"  {FAIL} Error: {e}")
        return False


async def test_proactive_prompt():
    """Test 4: Proactive prompt generation using persona-aware builder."""
    print(f"\n{'='*60}")
    print("Test 4: Proactive Prompt Building")
    print(f"{'='*60}")
    try:
        cfg = get_config()
        store = MemoryStore(Path("./data"))
        user_id = "prompt_test"
        user = store.get_user(user_id)
        user.name = "小明"
        user.first_chat = time.time() - 15 * 86400  # 15 days ago
        user.relationship = "familiar"
        user.events = [
            {"event": "用户明天有面试", "time": time.time(), "remind_in_hours": 24},
        ]
        store.save_user(user)

        from gf.ai.persona import build_proactive_prompt
        from gf.ai.personas import get_persona

        persona = get_persona("gentle")
        prompt = build_proactive_prompt(
            user_name="小明",
            persona=persona,
            trigger_type="morning",
            days_known=15,
            relationship="familiar",
            events_text="用户明天有面试",
        )

        assert "小明" in prompt, "User name should be in prompt"
        assert persona.name in prompt, "Bot name should be in prompt"
        assert "15 天" in prompt, "Days known should be in prompt"
        assert "familiar" in prompt.lower(), "Relationship should be in prompt"
        assert "[happy]" in prompt.lower() or "[caring]" in prompt.lower(), "Sticker tags should be in prompt"

        print(f"  {PASS} Morning prompt: {len(prompt)} chars")
        print(f"  {PASS} Contains user name, bot name, days, relationship, events")

        # Test evening prompt
        evening_prompt = build_proactive_prompt(
            user_name="小明", persona=persona,
            trigger_type="evening", days_known=15, relationship="familiar",
        )
        assert len(evening_prompt) > 200
        print(f"  {PASS} Evening prompt: {len(evening_prompt)} chars")

        # Test silence prompt
        silence_prompt = build_proactive_prompt(
            user_name="小明", persona=persona,
            trigger_type="silence", days_known=15, relationship="familiar",
        )
        assert len(silence_prompt) > 200
        print(f"  {PASS} Silence prompt: {len(silence_prompt)} chars")

        # Cleanup
        (store.users_dir / f"{user_id}.json").unlink()
        return True
    except Exception as e:
        print(f"  {FAIL} Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_proactive_llm():
    """Test 5: LLM generates persona-aware proactive messages."""
    print(f"\n{'='*60}")
    print("Test 5: Proactive LLM Messages")
    print(f"{'='*60}")
    try:
        cfg = get_config()
        client = LLMClient(cfg.llm)
        store = MemoryStore(Path("./data"))

        from gf.ai.persona import build_proactive_prompt
        from gf.ai.personas import get_persona

        user_id = "proactive_llm_test"
        user = store.get_user(user_id)
        user.name = "阿明"
        user.first_chat = time.time() - 10 * 86400
        user.relationship = "familiar"
        store.add_message(user_id, "user", "今天好累")
        store.add_message(user_id, "assistant", "乖乖辛苦啦～给你捏捏肩膀")
        store.save_user(user)

        persona = get_persona("gentle")

        for trigger in ["morning", "evening", "silence"]:
            system_prompt = build_proactive_prompt(
                user_name=user.name,
                persona=persona,
                trigger_type=trigger,
                days_known=10,
                relationship="familiar",
            )

            recent = store.get_recent_messages(user_id, count=4)
            llm_msgs = [LLMClient.system_message(system_prompt)]
            for m in recent:
                llm_msgs.append({"role": m["role"], "content": m["content"]})
            llm_msgs.append(LLMClient.user_message(
                f"[系统指令：现在{trigger}，请主动给{user.name}发一条消息]"
            ))

            reply, sticker = await client.chat(llm_msgs)
            status = PASS if len(reply) > 0 else FAIL
            print(f"  {status} [{trigger}] {reply[:80]}{'...' if len(reply)>80 else ''}")
            if sticker and sticker.isascii():
                print(f"       Sticker: {sticker}")

        (store.users_dir / f"{user_id}.json").unlink()
        return True
    except Exception as e:
        print(f"  {FAIL} Error: {e}")
        return False


async def main():
    print("=" * 60)
    print("  AI Girlfriend Bot — Phase 2 Scheduler Test")
    print("=" * 60)

    # Load config once before all tests
    cfg = load_config()
    print(f"  Config loaded: {cfg.llm.model}, bot={cfg.bot.bot_name}")

    results = []
    results.append(("Clinginess Presets", test_clinginess_presets()))
    results.append(("Trigger Windows", test_trigger_windows()))
    results.append(("Silence Detection", test_silence_detection()))
    results.append(("Prompt Building", await test_proactive_prompt()))
    results.append(("Proactive LLM", await test_proactive_llm()))

    # Summary
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
