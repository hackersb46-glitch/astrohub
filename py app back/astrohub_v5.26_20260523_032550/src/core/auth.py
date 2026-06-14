"""
AstroHub v2.0 - 认证与授权管理

JWT Token + API Key 双轨认证。
支持角色权限：admin / operator / viewer
"""

from __future__ import annotations

import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from src.config import ACCESS_TOKEN_EXPIRE_MINUTES, SECRET_KEY
from src.logger import get_logger

log = get_logger("auth")

ROLES = {"admin", "operator", "viewer"}


class AuthError(Exception):
    """认证相关异常基类。"""


class UserNotFoundError(AuthError):
    pass


class InvalidCredentialsError(AuthError):
    pass


class TokenExpiredError(AuthError):
    pass


class InvalidTokenError(AuthError):
    pass


class PermissionDeniedError(AuthError):
    pass


class AuthManager:
    """认证管理器。

    管理用户、JWT Token、API Key 及权限。
    注：当前实现使用内存存储，生产环境应迁移至数据库。
    """

    # 角色权限矩阵
    PERMISSIONS: dict[str, list[str]] = {
        "admin": [
            "user.create",
            "user.read",
            "user.update",
            "user.delete",
            "user.change_password",
            "token.revoke",
            "apikey.create",
            "apikey.read",
            "apikey.delete",
            "system.read",
            "system.write",
            "system.admin",
        ],
        "operator": [
            "user.read",
            "user.update",
            "apikey.create",
            "apikey.read",
            "system.read",
            "system.write",
        ],
        "viewer": [
            "user.read",
            "apikey.read",
            "system.read",
        ],
    }

    def __init__(self) -> None:
        """初始化认证管理器。"""
        self._users: dict[str, dict[str, Any]] = {}
        self._user_ids: dict[str, str] = {}  # user_id -> username
        self._tokens: set[str] = set()
        self._api_keys: dict[str, dict[str, Any]] = {}
        self._next_id = 1

        log.info("AuthManager 初始化完成")

    # ------------------------------------------------------------------
    # 用户管理
    # ------------------------------------------------------------------

    def create_user(self, username: str, password: str, role: str) -> str:
        """创建用户。

        Args:
            username: 用户名。
            password: 明文密码（内部自动哈希）。
            role: 角色，必须为 admin / operator / viewer 之一。

        Returns:
            新创建用户的 user_id。

        Raises:
            AuthError: 角色非法或用户名已存在。
        """
        if role not in ROLES:
            raise AuthError(f"非法角色 '{role}'，可选: {ROLES}")
        if username in self._users:
            raise AuthError(f"用户 '{username}' 已存在")

        user_id = str(self._next_id)
        self._next_id += 1

        self._users[username] = {
            "user_id": user_id,
            "password_hash": self._hash_password(password),
            "role": role,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._user_ids[user_id] = username

        log.info(f"用户 '{username}' 创建成功 (role={role})")
        return user_id

    def authenticate(self, username: str, password: str) -> str:
        """认证用户，颁发 JWT Token。

        Args:
            username: 用户名。
            password: 密码。

        Returns:
            JWT token 字符串。

        Raises:
            InvalidCredentialsError: 用户名或密码错误。
        """
        user = self._users.get(username)
        if not user or user["password_hash"] != self._hash_password(password):
            log.warning(f"认证失败: 用户 '{username}'")
            raise InvalidCredentialsError("用户名或密码错误")

        now = datetime.now(timezone.utc)
        payload = {
            "user_id": user["user_id"],
            "username": username,
            "role": user["role"],
            "iat": now,
            "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        }

        token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
        self._tokens.add(token)

        log.info(f"用户 '{username}' 认证成功")
        return token

    def verify_token(self, token: str) -> dict[str, Any]:
        """验证 JWT Token 并返回用户信息。

        Args:
            token: JWT token 字符串。

        Returns:
            包含 user_id, username, role 的字典。

        Raises:
            InvalidTokenError: Token 无效或格式错误。
            TokenExpiredError: Token 已过期。
        """
        if token not in self._tokens:
            raise InvalidTokenError("Token 已被撤销")

        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            self._tokens.discard(token)
            raise TokenExpiredError("Token 已过期")
        except jwt.InvalidTokenError as exc:
            raise InvalidTokenError(f"Token 无效: {exc}")

        return {
            "user_id": payload["user_id"],
            "username": payload["username"],
            "role": payload["role"],
        }

    def revoke_token(self, token: str) -> None:
        """撤销指定 Token。

        Args:
            token: 要撤销的 JWT token。
        """
        self._tokens.discard(token)
        log.info("Token 已撤销")

    # ------------------------------------------------------------------
    # API Key 管理
    # ------------------------------------------------------------------

    def generate_api_key(self, user_id: str) -> str:
        """为指定用户生成 API Key。

        Args:
            user_id: 用户 ID。

        Returns:
            新生成的 API Key 字符串。

        Raises:
            UserNotFoundError: 用户不存在。
        """
        username = self._user_ids.get(user_id)
        if not username:
            raise UserNotFoundError(f"用户 ID '{user_id}' 不存在")

        api_key = f"ak_{secrets.token_hex(32)}"
        self._api_keys[api_key] = {
            "user_id": user_id,
            "username": username,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        log.info(f"为用户 '{username}' 生成 API Key")
        return api_key

    def verify_api_key(self, api_key: str) -> dict[str, Any]:
        """验证 API Key 并返回用户信息。

        Args:
            api_key: API Key 字符串。

        Returns:
            包含 user_id, username, role 的字典。

        Raises:
            InvalidTokenError: API Key 无效。
        """
        key_info = self._api_keys.get(api_key)
        if not key_info:
            raise InvalidTokenError("API Key 无效")

        username = key_info["username"]
        user = self._users[username]

        return {
            "user_id": key_info["user_id"],
            "username": username,
            "role": user["role"],
        }

    # ------------------------------------------------------------------
    # 权限管理
    # ------------------------------------------------------------------

    def get_user_permissions(self, user_id: str) -> list[str]:
        """获取指定用户的所有权限。

        Args:
            user_id: 用户 ID。

        Returns:
            权限字符串列表。

        Raises:
            UserNotFoundError: 用户不存在。
        """
        username = self._user_ids.get(user_id)
        if not username:
            raise UserNotFoundError(f"用户 ID '{user_id}' 不存在")

        role = self._users[username]["role"]
        return list(self.PERMISSIONS.get(role, []))

    @staticmethod
    def check_permission(user_permissions: list[str], required: str) -> bool:
        """检查用户是否拥有指定权限。

        Args:
            user_permissions: 用户权限列表。
            required: 需要的权限字符串（如 'system.write'）。

        Returns:
            是否拥有权限。
        """
        return required in user_permissions

    # ------------------------------------------------------------------
    # 密码管理
    # ------------------------------------------------------------------

    def change_password(self, user_id: str, old_password: str, new_password: str) -> None:
        """修改用户密码。

        Args:
            user_id: 用户 ID。
            old_password: 旧密码。
            new_password: 新密码。

        Raises:
            UserNotFoundError: 用户不存在。
            InvalidCredentialsError: 旧密码错误。
            AuthError: 新旧密码相同。
        """
        username = self._user_ids.get(user_id)
        if not username:
            raise UserNotFoundError(f"用户 ID '{user_id}' 不存在")

        user = self._users[username]
        if user["password_hash"] != self._hash_password(old_password):
            raise InvalidCredentialsError("旧密码错误")

        if self._hash_password(old_password) == self._hash_password(new_password):
            raise AuthError("新密码不能与旧密码相同")

        user["password_hash"] = self._hash_password(new_password)
        log.info(f"用户 '{username}' 修改密码成功")

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_password(password: str) -> str:
        """对密码进行 SHA-256 哈希（加盐）。

        生产环境应替换为 bcrypt / argon2。
        """
        salt = SECRET_KEY[:16]
        return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
