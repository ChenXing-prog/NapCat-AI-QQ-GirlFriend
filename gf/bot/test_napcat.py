"""
NapCatQQ 连接测试脚本。

测试 gf 后端与 NapCatQQ 之间的连接是否正常。

Usage:
    # 先确保 NapCatQQ 在运行
    python -m gf.bot.test_napcat
"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gf.config import load_config, get_config
from gf.bot.client import QQClient


async def main():
    cfg = load_config()

    print("=" * 60)
    print("  NapCatQQ Connection Test")
    print("=" * 60)

    client = QQClient(cfg.napcat)

    # Test 1: Get login info
    print(f"\n1. Connecting to {cfg.napcat.base_url} ...")
    try:
        info = await client.get_login_info()
        print(f"   ✅ Connected!")
        print(f"   QQ: {info.get('user_id', 'N/A')}")
        print(f"   昵称: {info.get('nickname', 'N/A')}")
    except Exception as e:
        print(f"   ❌ Connection failed: {e}")
        print(f"\n   Make sure NapCatQQ is running:")
        print(f"     docker compose up -d")
        print(f"   Then open http://localhost:6099 to scan QR code")
        await client.close()
        return

    # Test 2: Get friend list
    print(f"\n2. Fetching friend list...")
    try:
        friends = await client.get_friend_list()
        count = len(friends.get("data", friends)) if isinstance(friends, dict) else len(friends)
        print(f"   ✅ {count} friends found")
    except Exception as e:
        print(f"   ⚠️  Could not get friend list: {e}")

    # Test 3: Send a test message to yourself
    bot_qq = cfg.bot.bot_qq
    if bot_qq and bot_qq != "123456789":
        print(f"\n3. Sending test message to yourself ({bot_qq})...")
        try:
            await client.send_private_msg(bot_qq, "✅ AI 女友 Bot 上线了！这是一条测试消息～")
            print(f"   ✅ Test message sent. Check your QQ!")
        except Exception as e:
            print(f"   ⚠️  Could not send test message: {e}")
    else:
        print(f"\n3. ⚠️  BOT_QQ is not set (still default). Skipping self-message test.")
        print(f"   Set BOT_QQ in gf/.env to your bot's QQ number.")

    await client.close()
    print(f"\n{'='*60}")
    print("  Connection test complete!")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
