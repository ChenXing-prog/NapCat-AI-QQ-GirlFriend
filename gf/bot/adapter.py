import asyncio, json, logging
from typing import Optional
import websockets
from websockets.exceptions import ConnectionClosed
from ..config import NapCatConfig, BotConfig
logger = logging.getLogger(__name__)

class QQAdapter:
    def __init__(self, napcat_config, bot_config):
        self.napcat_cfg = napcat_config
        self.bot_cfg = bot_config
        self._ws = None
        self._running = False
        self.on_private_message = None
        self.on_group_message = None
        self.on_friend_add = None

    async def start(self):
        self._running = True
        retry_delay = 1
        while self._running:
            try:
                logger.info(f"Connecting to NapCatQQ WS: {self.napcat_cfg.ws_url}")
                kw = dict(ping_interval=30, ping_timeout=10, close_timeout=5)
                if self.napcat_cfg.access_token:
                    kw["additional_headers"] = {"Authorization": f"Bearer {self.napcat_cfg.access_token}"}
                ws = await websockets.connect(self.napcat_cfg.ws_url, **kw)
                self._ws = ws
                retry_delay = 1
                logger.info("Connected to NapCatQQ WebSocket")
                async for raw in ws:
                    try:
                        await self._handle_message(raw)
                    except Exception as e:
                        logger.error(f"Error handling WS message: {e}")
            except ConnectionClosed as e:
                logger.warning(f"WebSocket disconnected: {e}")
            except Exception as e:
                logger.warning(f"WebSocket connection failed: {e}")
            if self._running:
                logger.info(f"Reconnecting in {retry_delay}s...")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)

    async def stop(self):
        self._running = False
        if self._ws:
            await self._ws.close()

    async def _handle_message(self, raw):
        data = json.loads(raw)
        pt = data.get("post_type")
        if pt == "message":
            uid = str(data.get("user_id",""))
            msg = data.get("raw_message", data.get("message",""))
            if uid == str(self.bot_cfg.bot_qq):
                return
            if data.get("message_type") == "private" and self.on_private_message:
                await self.on_private_message(uid, msg)
        elif pt == "notice" and data.get("notice_type") == "friend_add" and self.on_friend_add:
            await self.on_friend_add(str(data.get("user_id","")))
