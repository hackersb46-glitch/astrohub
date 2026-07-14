"""
AstroHub v8.80 - 天文指向控制
==============================
PTZ 指向目标恒星，支持校准模型转换。

依赖: astro_move → advanced.calibration_3stars, ptz.isapi.ptz

Author: 开发工厂
"""

from datetime import datetime, timezone
from typing import Optional

from src.ptz.isapi.ptz import PTZController
from src.astro_move.rd2az import CoordinateConverter, StarCatalog, CalibrationSolver


class AstroGoto:
    """
    天文指向控制器。
    接收 PTZController 和可选的 CalibrationSolver，
    提供 goto_star() 指向恒星、read_position_deg() 读取当前 PTZ 位置（度数）。
    """

    def __init__(self, ptz: PTZController, solver: Optional[CalibrationSolver] = None):
        """
        参数:
            ptz: PTZController 实例
            solver: CalibrationSolver 实例（可选，未传或未求解时使用恒等变换）
        """
        self.ptz = ptz
        self.solver = solver
        self.catalog = StarCatalog()
        self.converter = CoordinateConverter()

    # ── 公有方法 ─────────────────────────────────────────────────────────────

    def goto_star(self, star_hip: int, obs_lat: float, obs_lon: float,
                  zoom: int = 10) -> tuple:
        """
        指向一颗目标恒星。

        流程:
          1. 从星表获取恒星的 RA/Dec
          2. 用当前时刻计算 Alt/Az (CoordinateConverter.radec_to_altaz)
          3. 如果有 CalibrationSolver 且已求解，用 true_to_ptz() 转换
             否则直接使用 Alt/Az 作为 PTZ 目标（恒等变换）
          4. 度数 → ISAPI units（×10）
          5. 调用 ptz.absolute_move()

        参数:
            star_hip: 恒星 HIP 编号
            obs_lat: 观测者纬度（度）
            obs_lon: 观测者经度（度）
            zoom: 变焦倍率，默认 10

        返回:
            (success: bool, message: str)
        """
        # 1. 获取星表信息
        star = self.catalog.get_by_hip(star_hip)
        if star is None:
            return False, f"未找到 HIP {star_hip}"

        name = star.get("display_name") or f"HIP{star_hip}"
        ra_deg = star["ra_deg"]
        dec_deg = star["dec_deg"]

        # 2. 计算当前时刻的 Alt/Az
        now = datetime.now(timezone.utc)
        try:
            alt_deg, az_deg = self.converter.radec_to_altaz(
                ra_deg, dec_deg, obs_lat, obs_lon, now
            )
        except Exception as e:
            return False, f"坐标转换失败: {e}"

        # 3. 校准模型转换（如已求解）
        if self.solver is not None and self.solver._solved:
            try:
                ptz_az, ptz_alt = self.solver.true_to_ptz(az_deg, alt_deg)
            except Exception as e:
                return False, f"校准转换失败: {e}"
        else:
            ptz_az, ptz_alt = az_deg, alt_deg

        # 4. 度数 → ISAPI units（×10）
        pan_units = int(ptz_az * 10)
        tilt_units = int(ptz_alt * 10)

        # 5. 发送绝对移动指令
        try:
            success = self.ptz.absolute_move(pan_units, tilt_units, zoom, speed=50)
        except Exception as e:
            return False, f"PTZ 移动失败: {e}"

        if success:
            return True, f"指向 {name} 成功: pan={pan_units}, tilt={tilt_units}"
        else:
            return False, f"指向 {name} 失败: PTZ 返回错误"

    def read_position_deg(self) -> dict:
        """
        读取当前 PTZ 位置，返回度数。

        返回:
            {"pan": float（度）, "tilt": float（度）, "zoom": float}
            获取失败时返回空字典。
        """
        pos = self.ptz.get_position()
        if not pos:
            return {}
        return {
            "pan": pos["pan"] / 10.0,
            "tilt": pos["tilt"] / 10.0,
            "zoom": pos["zoom"],
        }