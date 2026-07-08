"""
M8 WebSocket v1.0 - WebSocket 连接认证

实现:
- P0.4: WS 连接认证 (连接时携带 token, 服务端验证)
- 支持从 URL query 参数或消息中提取 token
- Token 验证与过期检查

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import time
from typing import Any

from src.websocket.constants import (
    WS_TOKEN_EXPIRE_MINUTES,
)


# ================================================================== #
#  Token 验证器 (对接 M7 JWT 模块)
# ================================================================== #

class WSAuthenticator:
    """WebSocket 连接认证。"""

    def __init__(self) -> None:
        # 简单 token 存储 (生产环境应复用 M7 JWT 模块)
        # {token: {"user": ..., "exp": ..., "active": ...}}
        self._tokens: dict[str, dict[str, Any]] = {}

    def register_token(self, token: str, user: str = "", expires_minutes: int = WS_TOKEN_EXPIRE_MINUTES) -> None:
        """注册有效 Token。

        Args:
            token: JWT token 字符串
            user: 用户名
            expires_minutes: 过期时间 (分钟)
        """
        self._tokens[token] = {
            "user": user,
            "created_at": time.time(),
            "expires_minutes": expires_minutes,
            "active": True,
        }

    def validate_token(self, token: str) -> dict[str, Any] | None:
        """验证 Token 是否有效 (P0.4)。

        Args:
            token: 要验证的 token

        Returns:
            如果有效返回 token 信息 (用户名等), 否则返回 None
        """
        if not token:
            return None

        token_info = self._tokens.get(token)
        if token_info is None:
            return None

        if not token_info.get("active"):
            return None

        # 检查过期
        created = token_info.get("created_at", 0)
        expires = token_info.get("expires_minutes", WS_TOKEN_EXPIRE_MINUTES)
        if time.time() - created > expires * 60:
            token_info["active"] = False
            return None

        return token_info

    def revoke_token(self, token: str) -> bool:
        """吊销 Token。

        Args:
            token: 要吊销的 token

        Returns:
            是否成功
        """
        if token in self._tokens:
            self._tokens[token]["active"] = False
            return True
        return False

    def cleanup_expired(self) -> int:
        """清理过期 Token。

        Returns:
            清理数量
        """
        now = time.time()
        to_remove = []
        for token, info in self._tokens.items():
            expires = info.get("expires_minutes", WS_TOKEN_EXPIRE_MINUTES)
            if now - info.get("created_at", 0) > expires * 60:
                to_remove.append(token)

        for token in to_remove:
            del self._tokens[token]

        return len(to_remove)


# ================================================================== #
#  全局单例
# ================================================================== #

_ws_auth: WSAuthenticator | None = None


def get_ws_auth() -> WSAuthenticator:
    """获取全局 WSAuthenticator 实例。"""
    return _ws_auth  # type: ignore[return-value]


def init_ws_auth() -> WSAuthenticator:
    """初始化全局 WSAuthenticator 实例。

    Returns:
        WSAuthenticator 实例
    """
    global _ws_auth
    _ws_auth = WSAuthenticator()
    return _ws_auth
