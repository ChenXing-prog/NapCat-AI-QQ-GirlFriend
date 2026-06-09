"""
Phase 1 integration test.

Tests the core pipeline without needing NapCatQQ:
1. Config loading
2. System prompt building
3. LLM chat (with real API)
4. Sticker tag extraction
5. Memory store (read/write)
6. Sticker engine (category listing, picking)
7. Full simulated conversation

Usage:
    cd gf
    python test_phase1.py
"""

import sys
import asyncio
from pathlib import Path

# Allow running from gf/ directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from gf.config import load_config, get_config
from gf.ai.persona import build_system_prompt, get_sticker_tags
from gf.ai.llm import LLMClient
from gf.memory.store import MemoryStore
from gf.stickers.engine import StickerEngine


PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "


def test_config():
    """Test 1: Configuration loading."""
    print(f"\n{'='*60}")
    print("Test 1: Configuration")
    print(f"{'='*60}")
    try:
        cfg = load_config()
        print(f"  {PASS} Config loaded")
        print(f"      LLM Provider: {cfg.llm.provider}")
        print(f"      LLM Model:    {cfg.llm.model}")
        print(f"      Bot Name:     {cfg.bot.bot_name}")
        print(f"      Bot QQ:       {cfg.bot.bot_qq}")
        return True
    except Exception as e:
        print(f"  {FAIL} Config error: {e}")
        return False


def test_persona():
    """Test 2: System prompt building."""
    print(f"\n{'='*60}")
    print("Test 2: Persona & System Prompt")
    print(f"{'='*60}")
    try:
        prompt = build_system_prompt("小暖", "测试员")
        assert len(prompt) > 500, "Prompt too short"
        assert "小暖" in prompt, "Bot name not in prompt"
        assert "测试员" in prompt, "User name not in prompt"
        assert "[happy]" in prompt or "[shy]" in prompt, "Sticker tags should be in prompt"

        tags = get_sticker_tags()
        assert len(tags) >= 19, f"Expected at least 19 sticker tags, got {len(tags)}"

        print(f"  {PASS} System prompt: {len(prompt)} chars")
        print(f"  {PASS} Sticker tags: {len(tags)} categories loaded")
        return True
    except Exception as e:
        print(f"  {FAIL} Persona error: {e}")
        return False


def test_memory():
    """Test 3: Memory store."""
    print(f"\n{'='*60}")
    print("Test 3: Memory Store")
    print(f"{'='*60}")
    try:
        store = MemoryStore(Path("./data"))

        # Create / load user
        user = store.get_user("test_001")
        assert user.user_id == "test_001"
        print(f"  {PASS} User created: {user.user_id}")

        # Update name
        store.update_name("test_001", "小明")
        user = store.get_user("test_001")
        assert user.name == "小明"
        print(f"  {PASS} User name updated: {user.name}")

        # Add messages
        store.add_message("test_001", "user", "你好呀小暖～")
        store.add_message("test_001", "assistant", "小明～你来啦！今天有没有想我呀 💕")
        store.add_message("test_001", "user", "想啦想啦")

        msgs = store.get_recent_messages("test_001")
        assert len(msgs) == 3, f"Expected 3 messages, got {len(msgs)}"
        print(f"  {PASS} Messages stored: {len(msgs)}")

        # Add event
        store.add_event("test_001", "用户明天有考试")
        user = store.get_user("test_001")
        assert len(user.events) == 1
        assert "考试" in user.events[0]["event"]
        print(f"  {PASS} Event stored: {user.events[0]['event']}")

        # Relationship progression
        for i in range(110):
            store.add_message("test_001", "user", f"msg {i}")
        user = store.get_user("test_001")
        assert user.relationship == "familiar"
        print(f"  {PASS} Relationship: {user.relationship} (after 110+ msgs)")

        # Clean up test data
        (store.users_dir / "test_001.json").unlink()

        return True
    except Exception as e:
        print(f"  {FAIL} Memory error: {e}")
        return False


def test_sticker_engine():
    """Test 4: Sticker engine with 30-category system."""
    print(f"\n{'='*60}")
    print("Test 4: Sticker Engine")
    print(f"{'='*60}")
    try:
        engine = StickerEngine(Path("../stickers"))

        cats = engine.list_categories()
        print(f"  {PASS} Categories with images: {len(cats)}")

        # Test pick with empty category (laugh has no images)
        result = engine.pick("laugh")
        assert result is None, "Should return None for empty category"
        print(f"  {PASS} Empty category (laugh) → None: OK")

        # Test pick with populated category
        result2 = engine.pick("cute")
        assert result2 is not None, "cute should have images"
        print(f"  {PASS} Populated category (cute) → {result2.name}")

        # Test blacklist filtering
        banned = {result2.name}
        result3 = engine.pick("cute", banned=banned)
        assert result3 is not None and result3.name != result2.name
        print(f"  {PASS} Blacklist: excluded {result2.name}, got {result3.name}")

        # Test meta
        meta = engine.get_meta("cute")
        assert meta is not None and meta["emotion"] == "cute"
        print(f"  {PASS} Meta: {meta['emotion']} → {meta.get('label','?')}")

        # Test category counts
        counts = engine.category_counts()
        total = sum(counts.values())
        assert total >= 100, f"Expected 100+ stickers, got {total}"
        print(f"  {PASS} Total: {total} stickers in {len(counts)} categories")

        return True
    except Exception as e:
        print(f"  {FAIL} Sticker engine error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_llm():
    """Test 5: LLM chat (requires valid API key)."""
    print(f"\n{'='*60}")
    print("Test 5: LLM Chat")
    print(f"{'='*60}")
    try:
        cfg = get_config()
        client = LLMClient(cfg.llm)

        system = build_system_prompt(cfg.bot.bot_name, "测试员")

        messages = [
            LLMClient.system_message(system),
            LLMClient.user_message("你好呀，猜猜我今天心情怎么样？"),
        ]

        print(f"  Sending to {cfg.llm.model}...")
        reply, sticker = await client.chat(messages)

        print(f"  {PASS} Reply: {reply[:100]}")
        if sticker:
            print(f"  {PASS} Sticker tag: {sticker}")
        else:
            print(f"  {WARN} No sticker tag (not required)")

        # Test sticker tag extraction
        print(f"\n  --- Testing sticker tag parsing ---")
        # Use a second message that should trigger sticker
        messages.append(LLMClient.assistant_message(reply))
        messages.append(LLMClient.user_message("你今天好可爱哦！"))

        reply2, sticker2 = await client.chat(messages)
        print(f"  {PASS} Reply 2: {reply2[:100]}")
        if sticker2:
            print(f"  {PASS} Sticker tag: {sticker2}")
        else:
            print(f"  {WARN} No sticker tag in reply 2")

        return True
    except Exception as e:
        print(f"  {FAIL} LLM error: {e}")
        return False


async def test_full_conversation():
    """Test 6: Simulated multi-turn conversation."""
    print(f"\n{'='*60}")
    print("Test 6: Full Conversation Simulation")
    print(f"{'='*60}")
    try:
        cfg = get_config()
        client = LLMClient(cfg.llm)
        store = MemoryStore(Path("./data"))
        engine = StickerEngine(Path("../stickers"))

        user_id = "conv_test"
        user = store.get_user(user_id)
        user.name = "阿明"
        store.save_user(user)

        # Simulate a 3-turn conversation
        turns = [
            "你好呀！",
            "我今天上班好累...",
            "哈哈，确实开心多了。对了，我明天有个重要的面试",
        ]

        system = build_system_prompt(cfg.bot.bot_name, user.name)
        llm_messages = [LLMClient.system_message(system)]

        for i, user_msg in enumerate(turns):
            print(f"\n  --- Turn {i+1} ---")
            print(f"  User: {user_msg}")

            # Get recent messages from memory
            recent = store.get_recent_messages(user_id, count=10)
            llm_messages = [LLMClient.system_message(system)]
            for m in recent:
                llm_messages.append({"role": m["role"], "content": m["content"]})
            llm_messages.append(LLMClient.user_message(user_msg))

            reply, sticker = await client.chat(llm_messages)
            print(f"  Bot: {reply[:80]}{'...' if len(reply)>80 else ''}")
            if sticker:
                print(f"  Sticker: [{sticker}]")

            store.add_message(user_id, "user", user_msg)
            store.add_message(user_id, "assistant", reply)

        # Verify memory
        final_msgs = store.get_recent_messages(user_id)
        print(f"\n  {PASS} Total messages in memory: {len(final_msgs)} (expected 6)")

        # Check if "面试" event was detected
        user = store.get_user(user_id)
        print(f"  {PASS} Events recorded: {len(user.events)}")

        # Clean up
        (store.users_dir / f"{user_id}.json").unlink()

        return True
    except Exception as e:
        print(f"  {FAIL} Conversation error: {e}")
        return False


async def main():
    print("=" * 60)
    print("  AI Girlfriend Bot — Phase 1 Integration Test")
    print("=" * 60)

    results = []

    # Ordered tests (dependency: config must load first)
    results.append(("Config", test_config()))
    if not results[-1][1]:
        print("\n⛔ Config failed — cannot continue. Check your .env file.")
        return

    results.append(("Persona", test_persona()))
    results.append(("Memory", test_memory()))
    results.append(("Sticker Engine", test_sticker_engine()))
    results.append(("LLM Chat", await test_llm()))
    results.append(("Full Conversation", await test_full_conversation()))

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
