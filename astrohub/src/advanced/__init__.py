"""
AstroHub v2.0 - 高级功能模块

包含 Function/Limit/Speed 测试模块以及 Config 写入和 Onboarding 引导。

Author: 雅痞张@南方天文
"""

from .function import FunctionDetector
from .limit import LimitTester
from .speed import SpeedTester
from .config_writer import write_device_config, DeviceConfig
from .onboarding import OnboardingManager

__all__ = [
    "FunctionDetector",
    "LimitTester", 
    "SpeedTester",
    "write_device_config",
    "DeviceConfig",
    "OnboardingManager",
]
