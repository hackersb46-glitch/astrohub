"""
StreamIn - WASM 播放器控制模块

管理 WASM SDK 播放器进入 AstroHub 的所有功能：
- COOP/COEP 中间件（WASM 需要 SharedArrayBuffer）
- WebSocket 代理（复用官方 webSocketVideoCtrlProxy 方式）
- 独立日志 wasm_log

官方 SDK 架构：
- 前端：webVideoCtrl.js (JS SDK) + wasm-player.js (AstroHub 封装)
- 后端：WebSocket 代理 /webSocketVideoCtrlProxy（转发前端 SDK ↔ 设备 WebSocket）
- Nginx：官方 demo 使用 Nginx 做代理，AstroHub 用 Python aiohttp 实现

Author: 雅痞张@南方天文
"""

from src.stream_in.core.logger import wasm_log
from src.stream_in.api.router import stream_in_router, COOP_COEP_PATHS

__all__ = ["wasm_log", "stream_in_router", "COOP_COEP_PATHS"]
