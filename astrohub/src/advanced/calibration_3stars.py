"""
AstroHub v8.100 - 三星校准模块（兼容层）
========================================
v8.100: 代码已迁移到 src/astro_move/rd2az.py
此文件保留为兼容层，所有类从 rd2az 重新导出。

请新代码直接导入:
    from src.astro_move.rd2az import CoordinateConverter, StarCatalog, CalibrationSolver
"""

# 从 rd2az 重新导出所有公共 API
from src.astro_move.rd2az import (
    CoordinateConverter,
    StarCatalog,
    CalibrationSolver,
    _transpose,
    _mat_mul,
    _mat_inv_5x5,
    _mat_vec_mul,
    _lsq_solve,
)

__all__ = [
    "CoordinateConverter",
    "StarCatalog",
    "CalibrationSolver",
    "_transpose",
    "_mat_mul",
    "_mat_inv_5x5",
    "_mat_vec_mul",
    "_lsq_solve",
]