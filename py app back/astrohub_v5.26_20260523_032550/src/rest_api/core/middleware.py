"""
M7 REST API v1.0 - 中间件

实现:
- 请求日志中间件 (P6.3)
- 全局异常处理 (P6.2)
- 认证中间件
- 限流中间件 (P5.3)
- CORS 配置 (P0.1)

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from rest_api.constants import (
    API_V1_PREFIX,
    CORS_ALLOW_CREDENTIALS,
    CORS_ALLOW_HEADERS,
    CORS_ALLOW_METHODS,
    CORS_ALLOW_ORIGINS,
    ErrorCode,
    ERROR_CODE_DESCRIPTION,
    ERROR_CODE_TO_HTTP,
)
from rest_api.core.auth import get_jwt_manager, get_permission_checker
from rest_api.core.rate_limiter import get_rate_limiter


# ------------------------------------------------------------------ #
#  请求日志中间件 (P6.3)
# ------------------------------------------------------------------ #

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """记录所有 API 请求和响应的中间件。

    记录: 方法、路径、耗时、响应状态码、客户端 IP。
    敏感数据脱敏: Authorization header 仅显示前 15 字符。
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.monotonic()

        # 脱敏 Authorization header
        auth_header = request.headers.get("Authorization", "")
        auth_display = _mask_sensitive(auth_header) if auth_header else "N/A"

        client_ip = request.client.host if request.client else "unknown"
        method = request.method
        path = request.url.path

        # 处理请求
        response = await call_next(request)

        # 计算耗时
        elapsed_ms = (time.monotonic() - start_time) * 1000

        # 记录日志
        _log_request(
            method=method,
            path=path,
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
            client_ip=client_ip,
            auth=auth_display,
        )

        # 添加响应头
        response.headers["X-Response-Time"] = f"{elapsed_ms:.1f}ms"

        return response


# ------------------------------------------------------------------ #
#  认证中间件 (P5.1/P5.2)
# ------------------------------------------------------------------ #

class AuthMiddleware(BaseHTTPMiddleware):
    """JWT / API Key 认证中间件。

    对 /api/v1/* 路径实施认证检查。
    支持 Bearer Token 和 X-API-Key 两种认证方式。
    白名单端点无需认证 (如 /docs, /health, /api/v1/auth/login)。
    """

    # 无需认证的端点
    WHITELIST = {
        "/docs",
        "/redoc",
        "/openapi.json",
        "/health",
        f"{API_V1_PREFIX}/auth/login",
        f"{API_V1_PREFIX}/auth/refresh",
    }

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # 白名单端点跳过认证
        if path in self.WHITELIST:
            return await call_next(request)

        # 仅对 /api/ 路径下的路由实施认证
        if not path.startswith("/api/"):
            return await call_next(request)

        # 尝试认证
        jwt_manager = get_jwt_manager()
        token = request.headers.get("Authorization", "")

        if token.startswith("Bearer "):
            # JWT Bearer Token 认证
            try:
                payload = jwt_manager.verify_token(token[7:])
                request.state.user = payload.get("sub", "unknown")
                request.state.role = payload.get("role", "viewer")
            except Exception:
                return _json_response(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    body=_auth_error(ErrorCode.UNAUTHORIZED, "无效的认证凭证"),
                )
        else:
            return _json_response(
                status_code=status.HTTP_401_UNAUTHORIZED,
                body=_auth_error(ErrorCode.UNAUTHORIZED, "缺少 Bearer Token"),
            )

        return await call_next(request)


# ------------------------------------------------------------------ #
#  限流中间件 (P5.3)
# ------------------------------------------------------------------ #

class RateLimitMiddleware(BaseHTTPMiddleware):
    """限流中间件。

    按客户端 IP 进行限流, 超过限制返回 429。
    响应头中添加:
        X-RateLimit-Limit: 限流阈值
        X-RateLimit-Remaining: 剩余请求数
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # 仅对 /api/ 路径限流
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        rate_limiter = get_rate_limiter()
        client_ip = request.client.host if request.client else "unknown"

        if not rate_limiter.is_allowed(client_ip):
            return _json_response(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                body=_rate_limit_error(),
                headers={
                    "X-RateLimit-Limit": str(rate_limiter._default_limit),
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": str(rate_limiter._window),
                },
            )

        response = await call_next(request)
        remaining = rate_limiter.get_remaining(client_ip)
        response.headers["X-RateLimit-Limit"] = str(rate_limiter._default_limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)

        return response


# ------------------------------------------------------------------ #
#  全局异常处理 (P6.2)
# ------------------------------------------------------------------ #

def setup_exception_handlers(app: FastAPI) -> None:
    """配置全局异常处理器。

    捕获未处理的异常, 返回统一的 500 错误响应,
    不泄露堆栈信息给客户端。
    Wave 4: 增强异常分类 - 区分设备离线(409)、认证失败(401)等。
    """

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> Response:
        # 记录错误日志 (不暴露详情给客户端)
        print(f"[M7 ERROR] {request.method} {request.url.path}: {exc}")

        # Wave 4: 智能错误分类
        error_msg = str(exc).lower()
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        error_code = ErrorCode.INTERNAL_ERROR
        message = ERROR_CODE_DESCRIPTION.get(ErrorCode.INTERNAL_ERROR, "服务器内部错误")

        if "offline" in error_msg or "离线" in error_msg or "not reachable" in error_msg:
            status_code = status.HTTP_409_CONFLICT
            error_code = ErrorCode.DEVICE_OFFLINE
            message = "设备离线"
        elif "auth" in error_msg or "unauthorized" in error_msg or "401" in error_msg:
            status_code = status.HTTP_401_UNAUTHORIZED
            error_code = ErrorCode.UNAUTHORIZED
            message = "认证失败，请提供有效的凭证"
        elif "not found" in error_msg or "不存在" in error_msg:
            status_code = status.HTTP_404_NOT_FOUND
            error_code = ErrorCode.NOT_FOUND
            message = str(exc)

        return _json_response(
            status_code=status_code,
            body={
                "success": False,
                "error": {
                    "code": error_code.value,
                    "message": message,
                },
            },
        )


# ------------------------------------------------------------------ #
#  中间件注册
# ------------------------------------------------------------------ #

def setup_middleware(app: FastAPI) -> None:
    """注册所有中间件到 FastAPI 应用。

    注册顺序很重要 - 外层中间件先执行:
    1. CORS (最外层)
    2. RequestLogging
    3. RateLimit
    4. Auth (最内层, 最先执行)
    5. 设备离线检查 (Wave 4 新增)
    """
    # 1. CORS (P0.1)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ALLOW_ORIGINS,
        allow_credentials=CORS_ALLOW_CREDENTIALS,
        allow_methods=CORS_ALLOW_METHODS,
        allow_headers=CORS_ALLOW_HEADERS,
    )

    # 2. 请求日志 (P6.3)
    app.add_middleware(RequestLoggingMiddleware)

    # 3. 限流 (P5.3)
    app.add_middleware(RateLimitMiddleware)

    # 4. 认证 (P5.1/P5.2)
    app.add_middleware(AuthMiddleware)

    # 5. 全局异常处理 (P6.2)
    setup_exception_handlers(app)

    # 6. Wave 4: 422验证错误处理
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """处理Pydantic验证错误，返回422详细信息。"""
        errors = []
        for error in exc.errors():
            errors.append({
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error.get("msg", ""),
                "code": error.get("type", "validation_error"),
            })
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "success": False,
                "error": "请求参数验证失败",
                "code": ErrorCode.VALIDATION_ERROR.value,
                "details": errors,
            },
        )


# ------------------------------------------------------------------ #
#  工具函数
# ------------------------------------------------------------------ #

def _mask_sensitive(value: str, visible: int = 15) -> str:
    """脱敏敏感数据。"""
    if len(value) <= visible:
        return value
    return value[:visible] + "***"


def _log_request(
    method: str,
    path: str,
    status_code: int,
    elapsed_ms: float,
    client_ip: str,
    auth: str = "N/A",
) -> None:
    """输出请求日志。"""
    print(
        f"[M7 API] {method} {path} | "
        f"{status_code} | {elapsed_ms:.1f}ms | "
        f"{client_ip} | auth={auth}"
    )


def _json_response(
    status_code: int,
    body: dict,
    headers: dict | None = None,
) -> Response:
    """构造 JSON 响应。"""
    return Response(
        content=json.dumps(body, ensure_ascii=False),
        status_code=status_code,
        media_type="application/json",
        headers=headers or {},
    )


def _auth_error(code: ErrorCode, message: str) -> dict:
    """构造认证错误响应。"""
    return {
        "error": {
            "code": code.value,
            "message": message,
        }
    }


def _rate_limit_error() -> dict:
    """构造限流错误响应。"""
    return {
        "error": {
            "code": ErrorCode.RATE_LIMITED.value,
            "message": ERROR_CODE_DESCRIPTION[ErrorCode.RATE_LIMITED],
        }
    }
