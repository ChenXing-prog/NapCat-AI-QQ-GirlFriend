"""NapCatQQ WebSocket adapter.

Connects to the NapCatQQ WebSocket server to receive real-time events
(messages, notices, requests) and dispatches them to the message handler.
"""

import asyncio
import json
import logging
from typing import Optional
import websockets
from websockets.exceptions import ConnectionClosed
from ..config import NapCatConfig, BotConfig

logger = logging.getLogger(__name__)


class QQAdapter:
    """WebSocket listener for NapCatQQ events.

    Connects via reverse WebSocket to NapCatQQ and dispatches incoming
    private messages to a handler callback.

    Usage:
        adapter = QQAdapter(napcat_cfg)
        adapter.on_private_message = my_handler
        await adapter.start()
    """

    def __init__(self, napcat_config: NapCatConfig, bot_config: BotConfig):
        self.napcat_cfg = napcat_config
        self.bot_cfg = bot_config
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False

        # Handler callbacks — set before calling start()
        self.on_private_message = None  # async (user_id: str, message: str) -> None
        self.on_group_message = None
        self.on_friend_add = None

    async def start(self):
        """Connect to NapCatQQ WebSocket and start listening for events."""
        self._running = True
        retry_delay = 1

        while self._running:
            try:
                logger.info(f"Connecting to NapCatQQ WS: {self.napcat_cfg.ws_url}")
                async with websockets.connect(
                    self.napcat_cfg.ws_url,
                    extra_headers=(
                        {"Authorization": f"Bearer {self.napcat_cfg.access_token}"}
                        if self.napcat_cfg.access_token else {}
                    ),
                    ping_interval=30,
                    ping_timeout=10,
                ) as ws:
                    self._ws = ws
                    retry_delay = 1  # Reset on successful connection
                    logger.info("Connected to NapCatQQ WebSocket")

                    async for raw in ws:
                        try:
                            await self._handle_message(raw)
                        except Exception as e:
                            logger.error(f"Error handling WS message: {e}")

            except ConnectionClosed as e:
                logger.warning(f"WebSocket disconnected: {e}")
            except (OSError, websockets.WebSocketException) as e:
                logger.warning(f"WebSocket connection failed: {e}")

            if self._running:
                logger.info(f"Reconnecting in {retry_delay}s...")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)  # Exponential backoff, max 60s

    async def stop(self):
        """Stop listening and close the WebSocket connection."""
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None

    # ------------------------------------------------------------------
    # Event dispatching
    # ------------------------------------------------------------------

    async def _handle_message(self, raw: str):
        """Parse and dispatch a WebSocket event."""
        data = json.loads(raw)
        post_type = data.get("post_type")

        if post_type == "message":
            await self._handle_msg_event(data)
        elif post_type == "notice":
            await self._handle_notice_event(data)
        elif post_type == "request":
            await self._handle_request_event(data)
        else:
            # meta_event like heartbeat, lifecycle
            logger.debug(f"Meta event: {data.get('meta_event_type')}")

    async def _handle_msg_event(self, data: dict):
        """Handle incoming message events."""
        msg_type = data.get("message_type")
        user_id = str(data.get("user_id", ""))
        raw_message = data.get("raw_message", data.get("message", ""))

        # Skip messages from self
        if user_id == str(self.bot_cfg.bot_qq):
            return

        if msg_type == "private":
            if self.on_private_message:
                await self.on_private_message(user_id, raw_message)
        elif msg_type == "group":
            if self.on_group_message:
                group_id = str(data.get("group_id", ""))
                await self.on_group_message(group_id, user_id, raw_message)

    async def _handle_notice_event(self, data: dict):
        """Handle notice events (friend add, poke, etc.)."""
        notice_type = data.get("notice_type")

        if notice_type == "friend_add" and self.on_friend_add:
            user_id = str(data.get("user_id", ""))
            await self.on_friend_add(user_id)

    async def _handle_request_event(self, data: dict):
        """Handle request events (friend request, group invite)."""
        # For Phase 1, auto-accept friend requests is handled here
        # or can be configured in NapCatQQ directly
        pass
