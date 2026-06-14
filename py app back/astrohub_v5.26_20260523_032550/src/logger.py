"""
AstroHub v2.0 - 统一日志管理

单例 Logger，按模块分区，文件轮转。
日志文件按天: data/logs/astrohub_YYYYMMDD.log
"""

from __future__ import annotations

import warnings
warnings.warn(
    "src/logger.py is deprecated. Use module-specific logger (e.g., m1_ptz_astro.core.logger). "
    "Will be removed in a future version.",
    DeprecationWarning,
    stacklevel=2,
)

import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from src.config import LOG_BACKUP_COUNT, LOG_LEVEL, LOG_MAX_BYTES
from src.config_paths import LOG_DIR


class Logger:
    """统一日志单例。

    用法:
        log = get_logger("ptz")
        log.info("PTZ 初始化完成")

    分区说明:
        name 参数标识模块名，日志输出中会自动带上模块标签。
    """

    _instances: dict[str, logging.Logger] = {}
    _initialized = False

    @classmethod
    def get_logger(cls, name: str = "astrohub") -> logging.Logger:
        """获取按模块分区的 Logger 实例。

        Args:
            name: 模块名称，用作日志分区标识。

        Returns:
            配置完整的 logging.Logger 实例。
        """
        if name not in cls._instances:
            logger = logging.getLogger(f"astrohub.{name}")
            logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

            if not cls._initialized:
                cls._setup_handlers(logger)
                cls._initialized = True
            else:
                # 子 logger 继承 root handlers
                logger.propagate = True

            cls._instances[name] = logger

        return cls._instances[name]

    @classmethod
    def _setup_handlers(cls, root_logger: logging.Logger) -> None:
        """配置根日志处理器（仅初始化一次）。"""
        LOG_DIR.mkdir(parents=True, exist_ok=True)

        # 日志格式
        fmt = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)-7s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # 文件处理器 - 按天轮转
        today = datetime.now().strftime("%Y%m%d")
        log_file = LOG_DIR / f"astrohub_{today}.log"

        file_handler = RotatingFileHandler(
            filename=str(log_file),
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        file_handler.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
        root_logger.addHandler(file_handler)

        # 控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(fmt)
        console_handler.setLevel(logging.INFO)
        root_logger.addHandler(console_handler)


# 便捷函数
def get_logger(name: str = "astrohub") -> logging.Logger:
    """获取模块日志器。

    Args:
        name: 模块名称。

    Returns:
        logging.Logger 实例。
    """
    return Logger.get_logger(name)
