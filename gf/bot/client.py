"""NapCatQQ HTTP client (v4 API)."""

import httpx
from typing import Optional
from ..config import NapCatConfig


class QQClient:
    """HTTP client for NapCatQQ v4 API."""

    def __init__(self, config: NapCatConfig):
        self.config = config
        headers = {}
        if config.access_token:
            headers["Authorization"] = f"Bearer {config.access_token}"
        self._client = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=30.0,
            headers=headers,
        )

    async def send_private_msg(self, user_id: str, message: str) -> dict:
        """Send a private text message."""
        resp = await self._client.post("/send_private_msg", json={
            "user_id": int(user_id),
            "message": message,
        })
        return resp.json()

    async def send_image(self, user_id: str, file_path: str) -> dict:
        """Send an image."""
        resp = await self._client.post("/send_private_msg", json={
            "user_id": int(user_id),
            "message": f"[CQ:image,file=file://{file_path}]",
        })
        return resp.json()

    async def send_like(self, user_id: str, times: int = 1) -> dict:
        """Send a like."""
        resp = await self._client.post("/send_like", json={
            "user_id": int(user_id),
            "times": min(times, 10),
        })
        return resp.json()

    async def get_login_info(self) -> dict:
        resp = await self._client.post("/get_login_info", json={})
        return resp.json()

    async def get_stranger_info(self, user_id: str) -> dict:
        resp = await self._client.post("/get_stranger_info", json={
            "user_id": int(user_id),
        })
        return resp.json()

    async def get_friend_list(self) -> dict:
        resp = await self._client.post("/get_friend_list", json={})
        return resp.json()

    async def close(self):
        await self._client.aclose()
