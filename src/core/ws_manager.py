"""WebSocket 连接管理器 - 线程安全的异步 WebSocket 管理。"""

import asyncio
from typing import Any


class WebSocketManager:
    """管理 WebSocket 连接、频道订阅和消息分发。"""

    def __init__(self) -> None:
        self._clients: dict[str, Any] = {}
        self._channels: dict[str, set[str]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: Any, client_id: str, channels: list[str] | None = None) -> None:
        """建立 WebSocket 连接并可选订阅频道。"""
        async with self._lock:
            self._clients[client_id] = {
                "ws": ws,
                "channels": set(channels) if channels else set(),
                "connected_at": asyncio.get_event_loop().time(),
            }
            for ch in channels or []:
                self._channels.setdefault(ch, set()).add(client_id)

    async def disconnect(self, client_id: str) -> None:
        """断开指定客户端连接并清理订阅。"""
        async with self._lock:
            client = self._clients.pop(client_id, None)
            if client:
                for ch in client["channels"]:
                    self._channels.get(ch, set()).discard(client_id)
                    if not self._channels[ch]:
                        del self._channels[ch]

    async def send_to(self, client_id: str, message: dict[str, Any]) -> bool:
        """发送消息给单个客户端。"""
        async with self._lock:
            client = self._clients.get(client_id)
            if not client:
                return False
        try:
            await client["ws"].send_json(message)
            return True
        except Exception:
            await self.disconnect(client_id)
            return False

    async def broadcast(self, message: dict[str, Any], channel: str | None = None) -> int:
        """广播消息到所有客户端或指定频道。"""
        async with self._lock:
            targets = (
                {cid for cid in self._channels.get(channel, set()) if cid in self._clients}
                if channel
                else dict(self._clients)
            )

        sent = 0
        failed = []
        for cid in targets:
            try:
                await self._clients[cid]["ws"].send_json(message)
                sent += 1
            except Exception:
                failed.append(cid)

        async with self._lock:
            for cid in failed:
                await self.disconnect(cid)
        return sent

    async def subscribe(self, client_id: str, channel: str) -> bool:
        """订阅指定频道。"""
        async with self._lock:
            client = self._clients.get(client_id)
            if not client:
                return False
            client["channels"].add(channel)
            self._channels.setdefault(channel, set()).add(client_id)
            return True

    async def unsubscribe(self, client_id: str, channel: str) -> bool:
        """取消订阅指定频道。"""
        async with self._lock:
            client = self._clients.get(client_id)
            if not client:
                return False
            client["channels"].discard(channel)
            self._channels.get(channel, set()).discard(client_id)
            if not self._channels.get(channel):
                self._channels.pop(channel, None)
            return True

    async def get_client_count(self) -> int:
        """返回在线客户端数量。"""
        async with self._lock:
            return len(self._clients)

    async def get_client_info(self, client_id: str) -> dict[str, Any] | None:
        """返回指定客户端信息。"""
        async with self._lock:
            client = self._clients.get(client_id)
            if not client:
                return None
            return {
                "client_id": client_id,
                "channels": list(client["channels"]),
                "connected_at": client["connected_at"],
            }

    async def get_channel_stats(self) -> dict[str, int]:
        """返回各频道的订阅统计。"""
        async with self._lock:
            return {ch: len(members) for ch, members in self._channels.items()}
