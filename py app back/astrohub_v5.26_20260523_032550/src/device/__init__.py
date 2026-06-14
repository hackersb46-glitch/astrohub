"""
M2 Device Manager v1.0
多设备管理、设备状态监控、设备生命周期管理。

Author: 雅痞张@南方天文
"""

__version__ = "1.0"
__author__ = "雅痞张@南方天文"


# Export Manager
from src.core.device_manager import DeviceManager
__all__ = ['DeviceManager']