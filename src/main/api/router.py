"""
M12 Integration v1.0 - FastAPI 路由层

包含集成模块的基础路由。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["M12 Integration"])


# ------------------------------------------------------------------ #
#  健康检查路由
# ------------------------------------------------------------------ #


@router.get("/health", summary="健康检查")
async def health_check() -> dict:
    """健康检查端点。"""
    return {
        "status": "ok",
        "module": "main",
        "version": "1.0.0",
    }
