"""
AstroHub v2.0 - 统一操作日志模块

v6.40: 记录所有用户操作、API调用、脚本执行。

功能:
- 用户点击、连接、断开等操作
- API调用日志
- 脚本执行日志 (speed.py, limit.py, function.py等)
- ISAPI 操作日志

日志格式:
[时间戳毫秒] [级别] [模块] 操作类型: 操作详情

日志文件:
astrohub/logs/operation_YYYYMMDD.log

Author: 开发工厂
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
import json

# ================================================================ #
#  日志目录配置
# ================================================================ #

def _get_log_dir() -> Path:
    """获取日志目录 (portable)."""
    import sys
    if getattr(sys, 'frozen', False):
        # PyInstaller打包
        return Path(sys.executable).parent / 'logs'
    # 开发模式
    return Path(__file__).resolve().parent.parent.parent / 'logs'

LOG_DIR = _get_log_dir()
LOG_DIR.mkdir(parents=True, exist_ok=True)


# ================================================================ #
#  操作日志类
# ================================================================ #

class OperationLogger:
    """统一操作日志记录器.
    
    级别:
        INFO    - 正常操作
        WARN    - 警告
        ERROR   - 错误
        DEBUG   - 调试信息
        FAILED  - 操作失败
    """
    
    _instance = None
    _logger = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._setup_logger()
        return cls._instance
    
    @classmethod
    def _setup_logger(cls):
        """配置日志处理器."""
        today = datetime.now().strftime("%Y%m%d")
        log_file = LOG_DIR / f"operation_{today}.log"
        
        logger = logging.getLogger("astrohub.operation")
        logger.setLevel(logging.DEBUG)
        
        # 文件处理器
        file_handler = RotatingFileHandler(
            filename=str(log_file),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=30,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        
        # 格式: [时间戳毫秒] [级别] [模块] 操作
        fmt = logging.Formatter(
            fmt="[%(asctime)s.%(msecs)03d] [%(levelname)-7s] [%(module)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
        
        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(fmt)
        logger.addHandler(console_handler)
        
        cls._logger = logger
    
    @classmethod
    def _format_timestamp(cls) -> str:
        """格式化时间戳（毫秒）."""
        now = datetime.now()
        ms = int((now.timestamp() % 1) * 1000)
        return now.strftime("%Y-%m-%d %H:%M:%S") + f".{ms:03d}"
    
    @classmethod
    def log(cls, level: str, module: str, action: str, detail: str | dict = "") -> None:
        """记录操作日志.
        
        Args:
            level: INFO/WARN/ERROR/DEBUG/FAILED
            module: web/api/script/isapi
            action: click/connect/disconnect/execute/login/play
            detail: 操作详情
        """
        if cls._logger is None:
            cls._setup_logger()
        
        timestamp = cls._format_timestamp()
        
        if isinstance(detail, dict):
            detail_str = json.dumps(detail, ensure_ascii=False)
        else:
            detail_str = str(detail)
        
        msg = f"[{module}] {action}: {detail_str}"
        
        level_map = {
            "INFO": logging.INFO,
            "WARN": logging.WARNING,
            "ERROR": logging.ERROR,
            "DEBUG": logging.DEBUG,
            "FAILED": logging.ERROR,
        }
        
        log_level = level_map.get(level.upper(), logging.INFO)
        cls._logger.log(log_level, msg)


# ================================================================ #
#  便捷函数
# ================================================================ #

def log_operation(level: str, module: str, action: str, detail: str | dict = "") -> None:
    """记录操作日志."""
    OperationLogger.log(level, module, action, detail)

def log_info(module: str, action: str, detail: str | dict = "") -> None:
    """记录 INFO 操作."""
    log_operation("INFO", module, action, detail)

def log_warn(module: str, action: str, detail: str | dict = "") -> None:
    """记录 WARN 操作."""
    log_operation("WARN", module, action, detail)

def log_error(module: str, action: str, detail: str | dict = "") -> None:
    """记录 ERROR 操作."""
    log_operation("ERROR", module, action, detail)

def log_failed(module: str, action: str, detail: str | dict = "") -> None:
    """记录 FAILED 操作."""
    log_operation("FAILED", module, action, detail)

def log_debug(module: str, action: str, detail: str | dict = "") -> None:
    """记录 DEBUG 操作."""
    log_operation("DEBUG", module, action, detail)


# ================================================================ #
#  模块专用日志函数
# ================================================================ #

def log_web(action: str, detail: str | dict = "") -> None:
    """Web界面操作日志."""
    log_info("web", action, detail)

def log_api(action: str, detail: str | dict = "") -> None:
    """API调用日志."""
    log_info("api", action, detail)

def log_script(script_name: str, action: str, detail: str | dict = "") -> None:
    """脚本执行日志."""
    log_info("script", f"{script_name}:{action}", detail)

def log_isapi(action: str, detail: str | dict = "") -> None:
    """ISAPI操作日志."""
    log_info("isapi", action, detail)


# ================================================================ #
#  导出
# ================================================================ #

__all__ = [
    "OperationLogger",
    "log_operation",
    "log_info",
    "log_warn",
    "log_error",
    "log_failed",
    "log_debug",
    "log_web",
    "log_api",
    "log_script",
    "log_isapi",
    "LOG_DIR",
]