"""
M4 Calibration Service v1.0
设备校准、自动对焦、色彩平衡、速度映射。

Author: 雅痞张@南方天文
"""

__version__ = "1.0"
__author__ = "雅痞张@南方天文"


# Export Manager
from src.core.calibration_manager import CalibrationManager
__all__ = ['CalibrationManager']