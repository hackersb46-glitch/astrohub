"""
M7 REST API v1.0 - JWT / API Key 认证与权限控制

实现:
- JWT Token 生成与验证 (P5.1)
- API Key 认证
- 基于角色的权限控制 (RBAC) (P5.2)

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status

try:
    import jwt  # PyJWT
    HAS_JWT = True
except ImportError:
    HAS_JWT = False

from rest_api.constants import (
    JWT_ALGORITHM,
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_DEFAULT_SECRET,
    JWT_REFRESH_TOKEN_EXPIRE_DAYS,
    Role,
    ROUTE_ROLE_MAP as _ROUTE_ROLE_MAP,
    ErrorCode,
    ERROR_CODE_DESCRIPTION,
    API_KEY_HEADER,
    API_KEY_LENGTH,
)


# ------------------------------------------------------------------ #
#  JWT Token 管理 (P5.1)
# ------------------------------------------------------------------ #

class JWTManager:
    """JWT Token 生成与验证。"""

    def __init__(self, secret: str = JWT_DEFAULT_SECRET):
        self._secret = secret

    def create_access_token(
        self,
        subject: str,
        role: str = Role.VIEWER.value,
        expires_delta: timedelta | None = None,
    ) -> str:
        """生成 access token。

        Args:
            subject: 用户名/标识
            role: 角色名 (admin/operator/viewer)
            expires_delta: 过期时间, 默认60分钟

        Returns:
            JWT token 字符串
        """
        if not HAS_JWT:
            raise RuntimeError("PyJWT 未安装, 请运行: pip install PyJWT")

        now = datetime.now(timezone.utc)
        expire = expires_delta or timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

        payload = {
            "sub": subject,
            "role": role,
            "iat": now,
            "exp": now + expire,
            "type": "access",
        }
        return jwt.encode(payload, self._secret, algorithm=JWT_ALGORITHM)

    def create_refresh_token(self, subject: str, role: str = Role.VIEWER.value) -> str:
        """生成 refresh token。

        Args:
            subject: 用户名/标识
            role: 角色名

        Returns:
            JWT refresh token 字符串
        """
        return self.create_access_token(
            subject=subject,
            role=role,
            expires_delta=timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        )

    def verify_token(self, token: str) -> dict:
        """验证 JWT token。

        Args:
            token: JWT token 字符串

        Returns:
            解码后的 payload dict

        Raises:
            HTTPException: token 无效或过期
        """
        if not HAS_JWT:
            raise RuntimeError("PyJWT 未安装")

        try:
            payload = jwt.decode(token, self._secret, algorithms=[JWT_ALGORITHM])
            if payload.get("type") != "access":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=_error_response(ErrorCode.INVALID_TOKEN),
                )
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=_error_response(ErrorCode.TOKEN_EXPIRED),
            )
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=_error_response(ErrorCode.INVALID_TOKEN),
            )

    def extract_token_from_request(self, request: Request) -> str | None:
        """从请求中提取 Bearer token。

        从 Authorization: Bearer <token> 头中提取。
        """
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        return None


# ------------------------------------------------------------------ #
#  API Key 管理
# ------------------------------------------------------------------ #

class APIKeyManager:
    """API Key 生成与验证。"""

    def __init__(self):
        # 存储 API Key -> {role, created_at, active}
        self._keys: dict[str, dict] = {}

    def generate_key(self, role: str = Role.VIEWER.value) -> str:
        """生成新的 API Key。

        Args:
            role: 角色名

        Returns:
            API Key 字符串
        """
        key = secrets.token_hex(API_KEY_LENGTH // 2)
        self._keys[key] = {
            "role": role,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "active": True,
            "key_hash": hashlib.sha256(key.encode()).hexdigest(),
        }
        return key

    def validate_key(self, key: str) -> dict | None:
        """验证 API Key。

        Args:
            key: API Key 字符串

        Returns:
            如果有效返回 {role, ...}, 否则返回 None
        """
        key_info = self._keys.get(key)
        if key_info and key_info.get("active"):
            return key_info
        return None

    def revoke_key(self, key: str) -> bool:
        """吊销 API Key。

        Args:
            key: API Key 字符串

        Returns:
            是否成功吊销
        """
        if key in self._keys:
            self._keys[key]["active"] = False
            return True
        return False

    def extract_key_from_request(self, request: Request) -> str | None:
        """从请求头中提取 API Key。"""
        return request.headers.get(API_KEY_HEADER)


# ------------------------------------------------------------------ #
#  权限控制 (P5.2)
# ------------------------------------------------------------------ #

class PermissionChecker:
    """基于角色的权限检查器。"""

    def __init__(self):
        self._route_roles = _ROUTE_ROLE_MAP

    def check_permission(self, method: str, path: str, user_role: str) -> bool:
        """检查用户是否有权访问指定端点。

        Args:
            method: HTTP 方法 (GET/POST/PUT/DELETE)
            path: API 路径 (如 /devices, /devices/{mac})
            user_role: 用户角色 (admin/operator/viewer)

        Returns:
            是否有权限
        """
        # 规范化路径 (去除 /api/v1 前缀)
        normalized_path = path
        if normalized_path.startswith("/api/v1"):
            normalized_path = normalized_path[7:]

        # 构造 key: "METHOD:/path"
        key = f"{method.upper()}:{normalized_path}"

        # 直接匹配
        required_role = self._route_roles.get(key)
        if required_role is None:
            # 尝试模糊匹配 (处理 path parameters)
            required_role = self._match_pattern(method, normalized_path)

        if required_role is None:
            # 无配置默认拒绝
            return False

        user_role_enum = self._to_role_enum(user_role)
        return user_role_enum == required_role or user_role_enum == Role.ADMIN

    def _match_pattern(self, method: str, path: str) -> Role | None:
        """模糊匹配带 path parameters 的路由。"""
        for key, role in self._route_roles.items():
            method_pattern, path_pattern = key.split(":", 1)
            if method_pattern != method.upper():
                continue
            if self._paths_match(path_pattern, path):
                return role
        return None

    @staticmethod
    def _paths_match(pattern: str, actual: str) -> bool:
        """检查两个路径是否匹配 (处理 {param} 占位符)。"""
        pattern_parts = pattern.strip("/").split("/")
        actual_parts = actual.strip("/").split("/")

        if len(pattern_parts) != len(actual_parts):
            return False

        for p, a in zip(pattern_parts, actual_parts):
            if p.startswith("{") and p.endswith("}"):
                continue  # 占位符匹配任何值
            if p != a:
                return False

        return True

    @staticmethod
    def _to_role_enum(role_str: str) -> Role:
        """将字符串转为 Role 枚举。"""
        try:
            return Role(role_str)
        except ValueError:
            return Role.VIEWER  # 默认最低权限


# ------------------------------------------------------------------ #
#  登录服务
# ------------------------------------------------------------------ #

class AuthService:
    """用户认证服务。"""

    def __init__(self, jwt_manager: JWTManager):
        self._jwt = jwt_manager
        # 简易用户存储 (生产环境应使用数据库)
        self._users: dict[str, dict] = {
            "admin": {"password_hash": _hash_password("admin123"), "role": Role.ADMIN.value},
            "operator": {"password_hash": _hash_password("operator123"), "role": Role.OPERATOR.value},
            "viewer": {"password_hash": _hash_password("viewer123"), "role": Role.VIEWER.value},
        }

    def authenticate(self, username: str, password: str) -> dict:
        """验证用户凭证。

        Args:
            username: 用户名
            password: 明文密码

        Returns:
            {access_token, refresh_token, token_type, role}

        Raises:
            HTTPException: 凭证无效
        """
        user = self._users.get(username)
        if user is None or user["password_hash"] != _hash_password(password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=_error_response(ErrorCode.INVALID_CREDENTIALS),
            )

        role = user["role"]
        return {
            "access_token": self._jwt.create_access_token(subject=username, role=role),
            "refresh_token": self._jwt.create_refresh_token(subject=username, role=role),
            "token_type": "bearer",
            "role": role,
        }


# ------------------------------------------------------------------ #
#  工具函数
# ------------------------------------------------------------------ #

def _hash_password(password: str) -> str:
    """简易密码哈希 (生产环境应用 bcrypt)。"""
    return hashlib.sha256(password.encode()).hexdigest()


def _error_response(error_code: ErrorCode) -> dict:
    """构造标准错误响应。"""
    return {
        "code": error_code.value,
        "message": ERROR_CODE_DESCRIPTION.get(error_code, "未知错误"),
    }


# ------------------------------------------------------------------ #
#  全局单例 (延迟初始化)
# ------------------------------------------------------------------ #

_jwt_manager: JWTManager | None = None
_api_key_manager: APIKeyManager | None = None
_permission_checker: PermissionChecker | None = None
_auth_service: AuthService | None = None


def get_jwt_manager() -> JWTManager:
    """获取全局 JWT Manager 实例。"""
    return _jwt_manager  # type: ignore[return-value]


def get_api_key_manager() -> APIKeyManager:
    """获取全局 API Key Manager 实例。"""
    return _api_key_manager  # type: ignore[return-value]


def get_permission_checker() -> PermissionChecker:
    """获取全局权限检查器实例。"""
    return _permission_checker  # type: ignore[return-value]


def get_auth_service() -> AuthService:
    """获取全局认证服务实例。"""
    return _auth_service  # type: ignore[return-value]


def init_auth(secret: str = JWT_DEFAULT_SECRET) -> None:
    """初始化认证模块。"""
    global _jwt_manager, _api_key_manager, _permission_checker, _auth_service
    _jwt_manager = JWTManager(secret=secret)
    _api_key_manager = APIKeyManager()
    _permission_checker = PermissionChecker()
    _auth_service = AuthService(_jwt_manager)
