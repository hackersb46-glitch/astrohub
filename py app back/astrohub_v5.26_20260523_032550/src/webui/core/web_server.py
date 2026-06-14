"""
M6 Web UI Service v1.0 - 静态文件服务与 SPA 支持

提供 React 前端构建产物的静态文件服务，支持 SPA 路由回退（所有非 API 请求返回 index.html）。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.routing import Match

from webui.constants import STATIC_DIR, BUILD_DIR, SPA_INDEX


class SPAServer:
    """SPA 静态文件服务器。

    挂载 /static 路由服务构建产物，并提供 SPA 路由回退支持。
    """

    def __init__(self, static_dir: Optional[Path] = None, build_dir: Optional[Path] = None):
        """初始化 SPA 服务器。

        Args:
            static_dir: 静态文件目录，默认为 constants.STATIC_DIR
            build_dir: 构建产物目录，默认为 constants.BUILD_DIR
        """
        self._static_dir = static_dir or STATIC_DIR
        self._build_dir = build_dir or BUILD_DIR
        self._initialized = False

    def setup(self, app: FastAPI) -> None:
        """在 FastAPI 应用中注册静态文件路由和 SPA 回退。

        优先级：
        1. /static/* -> 直接映射静态文件
        2. API 路由 -> 由 FastAPI router 处理
        3. SPA 路由 -> 返回 index.html（前端路由接管）

        Args:
            app: FastAPI 应用实例
        """
        # 挂载 /static 目录
        if self._static_dir.exists():
            app.mount("/static", StaticFiles(directory=str(self._static_dir)), name="static")

        # 挂载 /build 目录（React 构建产物）
        if self._build_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(self._build_dir / "assets")), name="assets")

        # SPA 回退路由 - 必须挂载到最后（低优先级）
        app.add_api_route(
            "/{full_path:path}",
            self._serve_spa_index,
            methods=["GET"],
            include_in_schema=False,
        )

        self._initialized = True

    async def _serve_spa_index(self, full_path: str) -> FileResponse | HTMLResponse:
        """SPA 路由回退：返回 index.html 让前端路由接管。

        跳过以下路径（避免与 API 路由和静态文件冲突）：
        - /api/*
        - /static/*
        - /assets/*
        - /docs, /openapi.json, /redoc

        Args:
            full_path: 请求路径

        Returns:
            index.html 的 FileResponse 或 404 HTMLResponse
        """
        # 跳过 API 和静态资源路径
        skip_prefixes = ("api/", "static/", "assets/", "docs", "openapi.json", "redoc")
        if any(full_path.startswith(prefix) for prefix in skip_prefixes):
            return HTMLResponse("<h1>404 Not Found</h1>", status_code=404)

        index_file = self._build_dir / SPA_INDEX
        if index_file.exists():
            return FileResponse(str(index_file))

        # 如果 build 目录不存在，返回一个简单的 SPA 提示
        return HTMLResponse(
            "<h1>M6 Web UI 服务已就绪</h1><p>请构建 React 前端并将产物放置到 build/ 目录。</p>",
            status_code=200,
        )

    @property
    def is_initialized(self) -> bool:
        """SPA 服务器是否已初始化。"""
        return self._initialized


def create_spa_server() -> SPAServer:
    """工厂函数：创建 SPA 服务器实例。

    Returns:
        配置完成的 SPAServer 实例
    """
    return SPAServer()
