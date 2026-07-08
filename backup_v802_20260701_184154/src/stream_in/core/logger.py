"""
StreamIn 日志模块 - wasm_log

独立的 WASM SDK 日志器，与其他 AstroHub 日志统一路径。
日志文件：log/wasm_YYYYMMDD.log
"""

from __future__ import annotations

import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path


def _get_log_dir() -> Path:
    """获取日志目录。"""
    # 与 astrohub 主程序使用相同的 log 目录
    app_dir = Path(__file__).resolve().parent.parent.parent.parent
    return app_dir / "log"


def _setup_wasm_logger() -> logging.Logger:
    """创建并配置 WASM 日志器。"""
    logger = logging.getLogger("wasm")
    logger.setLevel(logging.DEBUG)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    log_dir = _get_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    # 日志格式
    fmt = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)-7s] [wasm] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 文件处理器 - 按天轮转
    today = datetime.now().strftime("%Y%m%d")
    log_file = log_dir / f"wasm_{today}.log"

    file_handler = RotatingFileHandler(
        filename=str(log_file),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)

    return logger


# 单例日志器
wasm_log = _setup_wasm_logger()
