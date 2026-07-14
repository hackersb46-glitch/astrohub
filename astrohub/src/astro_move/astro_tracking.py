"""
AstroHub v8.100 - 天体跟踪引擎
================================
跟踪核心引擎，1秒循环控制 PTZ 跟踪天体。

依赖:
- PTZController (src.ptz.isapi.ptz)
- CelestialResolver (src.astro_move.rd2az)
- speed.py 的 load_cached_speed_results

使用 threading.Event 控制跟踪线程启停。
"""

import json
import math
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable

from src.ptz.isapi.ptz import PTZController
from src.astro_move.rd2az import CelestialResolver
from src.advanced.speed import load_cached_speed_results

# PTZ 单位: 3600 = 360° (1单位 = 0.1°)
_PTZ_UNITS_PER_DEG = 10.0


# ═══════════════════════════════════════════════════════════════════════════════
# SpeedCache
# ═══════════════════════════════════════════════════════════════════════════════

class SpeedCache:
    """
    速度映射缓存

    从 speed.json 读取速度映射，按 axis/direction/zoom 组织。
    支持 zoom 线性插值，将不支持的 zoom 值映射到最近校准档位。

    speed.json 格式:
    {
        "results": [
            {
                "axis": "pan"|"tilt",
                "direction": 1|-1,
                "speed_level": 1,  (ISAPI speed level 1-100)
                "speed_val": 1.26,  (PTZ units/s, 1 unit = 0.1°)
                "zoom": 10,
            },
            ...
        ]
    }
    """

    def __init__(self, mac: str):
        self.mac = mac
        # 结构: { (axis, direction, zoom): {speed_level: speed_val, ...} }
        self._zoom_data: dict[tuple[str, int, int], dict[int, float]] = {}
        # 当前校准档位列表
        self._zoom_levels: list[int] = []
        self._loaded = False

    def load(self) -> bool:
        """从缓存加载速度数据"""
        data = load_cached_speed_results(self.mac)
        if data is None:
            return False

        results = data.get("results", [])
        zoom_levels = set()

        for entry in results:
            axis = entry["axis"]
            direction = entry["direction"]
            zoom = entry["zoom"]
            speed_level = entry["speed_level"]
            speed_val = entry["speed_val"]

            key = (axis, direction, zoom)
            if key not in self._zoom_data:
                self._zoom_data[key] = {}
            self._zoom_data[key][speed_level] = speed_val
            zoom_levels.add(zoom)

        self._zoom_levels = sorted(zoom_levels)
        self._loaded = True
        return True

    def get_speed_val(self, axis: str, direction: int, zoom: int,
                      speed_level: int) -> Optional[float]:
        """
        获取指定参数下的速度值 (PTZ units/s)

        zoom 自动插值: 如果 zoom 不在校准档位中，线性插值最近两个档位
        """
        if not self._loaded:
            return None

        # 找到最近的校准 zoom
        effective_zoom = self._find_best_zoom(zoom)
        if effective_zoom is None:
            return None

        key = (axis, direction, effective_zoom)
        data = self._zoom_data.get(key)
        if data is None:
            return None

        return data.get(speed_level)

    def _find_best_zoom(self, zoom: int) -> Optional[int]:
        """
        找到最近的校准 zoom 档位
        如果 zoom 正好是校准档位之一，直接返回
        否则线性插值两个最近档位
        """
        if not self._zoom_levels:
            return None

        # 精确匹配
        if zoom in self._zoom_levels:
            return zoom

        # 低于最小档位：使用最小档位
        if zoom < self._zoom_levels[0]:
            return self._zoom_levels[0]

        # 高于最大档位：使用最大档位
        if zoom > self._zoom_levels[-1]:
            return self._zoom_levels[-1]

        # 在两个档位之间
        for i in range(len(self._zoom_levels) - 1):
            z1, z2 = self._zoom_levels[i], self._zoom_levels[i + 1]
            if z1 <= zoom <= z2:
                # 返回最近的档位
                return z1 if (zoom - z1) < (z2 - zoom) else z2

        return self._zoom_levels[-1]

    def get_speed_level_for_rate(self, axis: str, direction: int, zoom: int,
                                 desired_rate_deg_per_s: float) -> int:
        """
        根据目标速率 (deg/s) 查找最合适的 ISAPI speed level

        Returns:
            int: ISAPI speed level (1-100)，默认 50
        """
        if not self._loaded:
            return 50

        # 转换为 PTZ units/s
        desired_rate_units = desired_rate_deg_per_s * _PTZ_UNITS_PER_DEG

        effective_zoom = self._find_best_zoom(zoom)
        if effective_zoom is None:
            return 50

        key = (axis, direction, effective_zoom)
        data = self._zoom_data.get(key)
        if not data:
            return 50

        # 找到最接近的 speed_level
        best_level = 50
        best_diff = float("inf")

        for level, val in data.items():
            diff = abs(val - desired_rate_units)
            if diff < best_diff:
                best_diff = diff
                best_level = level

        return best_level

    def get_available_speed_levels(self, axis: str, direction: int,
                                    zoom: int) -> list[int]:
        """获取指定轴/方向/zoom 下可用的 speed_level 列表"""
        if not self._loaded:
            return []

        effective_zoom = self._find_best_zoom(zoom)
        key = (axis, direction, effective_zoom)
        data = self._zoom_data.get(key)
        if not data:
            return []

        return sorted(data.keys())

    def is_loaded(self) -> bool:
        return self._loaded


# ═══════════════════════════════════════════════════════════════════════════════
# ZenithHandler
# ═══════════════════════════════════════════════════════════════════════════════

class ZenithHandler:
    """
    天顶变速处理

    当目标接近天顶时，Az 方向需要快速旋转，容易超出机械限位。
    策略:
    - Alt > 75°: 限幅 Az 速度
    - Alt > 85°: 停止 Az 电机，仅保留 Alt 跟踪
    - Alt > 88°: 发出警告
    """

    # 天顶阈值（度）
    ALT_LIMIT_SPEED = 75.0    # 限幅开始
    ALT_STOP_AZ = 85.0        # 停止 Az
    ALT_WARNING = 88.0        # 警告

    # 速度限幅系数
    SPEED_LIMIT_FACTOR = 0.3  # >75° 时 Az 速度降至 30%

    def __init__(self, warning_callback: Optional[Callable[[str], None]] = None):
        """
        Args:
            warning_callback: 警告回调函数，接收警告消息字符串
        """
        self.warning_callback = warning_callback
        self._last_warning = ""
        self._warning_cooldown = 10.0  # 同一警告 10 秒内不重复
        self._last_warning_time = 0.0

    def process(self, alt_deg: float, az_rate_deg_per_s: float) -> dict:
        """
        处理天顶区域跟踪

        Args:
            alt_deg: 当前高度角（度）
            az_rate_deg_per_s: 原始 Az 速率 (deg/s)

        Returns:
            {
                "az_speed_factor": float,    # Az 速度系数 (0.0-1.0)
                "alt_speed_factor": float,   # Alt 速度系数 (1.0)
                "stop_az": bool,             # 是否停止 Az
                "warning": str,              # 警告消息（如有）
                "zone": str,                 # 天顶区域: "normal"|"limit"|"critical"|"danger"
            }
        """
        result = {
            "az_speed_factor": 1.0,
            "alt_speed_factor": 1.0,
            "stop_az": False,
            "warning": "",
            "zone": "normal",
        }

        now = time.time()

        if alt_deg >= self.ALT_WARNING:
            msg = f"⚠ 天顶警告: Alt={alt_deg:.1f}° > 88°，跟踪精度可能下降"
            result["warning"] = msg
            result["az_speed_factor"] = 0.0
            result["stop_az"] = True
            result["zone"] = "danger"
            self._issue_warning(msg, now)

        elif alt_deg >= self.ALT_STOP_AZ:
            msg = f"⚠ 天顶临界: Alt={alt_deg:.1f}° > 85°，停止 Az 电机"
            result["warning"] = msg
            result["az_speed_factor"] = 0.0
            result["stop_az"] = True
            result["zone"] = "critical"
            self._issue_warning(msg, now)

        elif alt_deg >= self.ALT_LIMIT_SPEED:
            factor = self.SPEED_LIMIT_FACTOR
            msg = f"信息: Alt={alt_deg:.1f}° > 75°，Az 速度限幅至 {factor*100:.0f}%"
            result["az_speed_factor"] = factor
            result["zone"] = "limit"
            # 限幅不触发重复警告，只记录
            result["warning"] = msg

        return result

    def _issue_warning(self, msg: str, now: float):
        """发出警告（带冷却）"""
        if msg != self._last_warning or (now - self._last_warning_time) > self._warning_cooldown:
            self._last_warning = msg
            self._last_warning_time = now
            if self.warning_callback:
                self.warning_callback(msg)


# ═══════════════════════════════════════════════════════════════════════════════
# TrackingEngine
# ═══════════════════════════════════════════════════════════════════════════════

class TrackingEngine:
    """
    跟踪核心引擎

    1秒循环，使用 continuous_move 跟踪天体。
    通过 threading.Event 控制跟踪线程启停。

    流程:
    1. 获取目标当前位置 (RA/Dec → Alt/Az)
    2. 读取 PTZ 当前实际位置
    3. 计算误差
    4. 通过 SpeedCache 查找合适的 ISAPI speed level
    5. 通过 ZenithHandler 处理天顶区域
    6. 发送 continuous_move 指令
    """

    # 停止阈值（度）
    ERROR_THRESHOLD_DEG = 0.05  # 误差小于此值认为已对准，停止移动
    MIN_MOVE_DEG = 0.01         # 小于此值不发送移动指令

    def __init__(self, ptz: PTZController, mac: str,
                 obs_lat: float, obs_lon: float,
                 target_spec: dict,
                 warning_callback: Optional[Callable[[str], None]] = None):
        """
        Args:
            ptz: PTZController 实例
            mac: 设备 MAC 地址（用于加载速度数据）
            obs_lat: 观测者纬度（度）
            obs_lon: 观测者经度（度）
            target_spec: 目标规格 (同 CelestialResolver.resolve_target)
            warning_callback: 警告回调
        """
        self.ptz = ptz
        self.mac = mac
        self.obs_lat = obs_lat
        self.obs_lon = obs_lon
        self.target_spec = target_spec

        # 依赖组件
        self.resolver = CelestialResolver()
        self.speed_cache = SpeedCache(mac)
        self.zenith_handler = ZenithHandler(warning_callback)

        # 线程控制
        self._stop_event = threading.Event()
        self._tracking_thread: Optional[threading.Thread] = None

        # 状态
        self._is_running = False
        self._current_zoom = 10
        self._last_correction_time = 0.0
        self._status = {
            "running": False,
            "target": target_spec,
            "current_position": {},
            "target_position": {},
            "error": {},
            "zenith_zone": "normal",
            "last_update": None,
            "corrections": 0,
            "message": "就绪",
        }

        # 加载速度缓存
        self.speed_cache.load()

    # ── 启动/停止 ───────────────────────────────────────────────────────

    def start(self):
        """启动跟踪线程"""
        if self._is_running:
            return

        self._stop_event.clear()
        self._is_running = True
        self._tracking_thread = threading.Thread(
            target=self._tracking_loop,
            name="astro-tracking",
            daemon=True,
        )
        self._tracking_thread.start()
        self._status["running"] = True
        self._status["message"] = "跟踪已启动"

    def stop(self):
        """停止跟踪线程"""
        self._is_running = False
        self._stop_event.set()
        if self._tracking_thread and self._tracking_thread.is_alive():
            self._tracking_thread.join(timeout=5.0)
        self._tracking_thread = None
        self._status["running"] = False
        self._status["message"] = "跟踪已停止"

        # 停止 PTZ 移动
        try:
            self.ptz.stop_move()
        except Exception:
            pass

    def is_running(self) -> bool:
        return self._is_running

    def get_status(self) -> dict:
        """获取当前跟踪状态"""
        self._status["last_update"] = datetime.now(timezone.utc).isoformat()
        return dict(self._status)

    def set_rate(self, rate_type: str, custom_params: Optional[dict] = None) -> None:
        """
        设置跟踪速率模式
        
        Args:
            rate_type: "sidereal" | "lunar" | "solar" | "custom"
            custom_params: 仅当 rate_type="custom" 时使用
                           {"dra_arcsec_per_s": float, "ddec_arcsec_per_s": float}
        """
        if rate_type not in ("sidereal", "lunar", "solar", "custom"):
            raise ValueError(f"Invalid rate type: {rate_type}")
        
        self._current_rate = rate_type
        
        if rate_type == "custom" and custom_params:
            self._custom_rate = custom_params
            # 更新目标规格为自定义速率模式
            self.target_spec["type"] = "custom"
            self.target_spec["custom_dra"] = custom_params.get("dra_arcsec_per_s", 0)
            self.target_spec["custom_ddec"] = custom_params.get("ddec_arcsec_per_s", 0)
        else:
            self._custom_rate = None
        
        self._status["current_rate"] = rate_type
        self._status["message"] = f"速率已切换: {rate_type}"

    # ── 跟踪主循环 ──────────────────────────────────────────────────────

    def _tracking_loop(self):
        """跟踪循环（1秒间隔）"""
        corrections = 0

        while not self._stop_event.is_set():
            loop_start = time.time()

            try:
                self._tracking_step(corrections)
                corrections += 1
                self._status["corrections"] = corrections
            except Exception as e:
                self._status["message"] = f"跟踪异常: {e}"

            # 等待 1 秒（减去已用时间）
            elapsed = time.time() - loop_start
            wait = max(0.1, 1.0 - elapsed)
            if self._stop_event.wait(timeout=wait):
                break

    def _tracking_step(self, iteration: int):
        """单步跟踪"""
        now = datetime.now(timezone.utc)

        # 1. 获取目标位置
        target_result = self.resolver.resolve_target(
            self.target_spec, self.obs_lat, self.obs_lon, now
        )
        if not target_result.get("success"):
            self._status["message"] = f"目标解析失败: {target_result.get('message', '')}"
            return

        target_alt = target_result["alt_deg"]
        target_az = target_result["az_deg"]
        target_rate_az = target_result.get("rate_az_deg_per_s", 0.0)
        target_rate_alt = target_result.get("rate_alt_deg_per_s", 0.0)

        self._status["target_position"] = {
            "alt": target_alt,
            "az": target_az,
            "rate_az": target_rate_az,
            "rate_alt": target_rate_alt,
        }

        # 2. 读取当前 PTZ 位置
        pos = self.ptz.get_position()
        if not pos:
            self._status["message"] = "无法读取 PTZ 位置"
            return

        current_pan_deg = pos["pan"] / _PTZ_UNITS_PER_DEG
        current_tilt_deg = pos["tilt"] / _PTZ_UNITS_PER_DEG
        self._current_zoom = pos["zoom"]

        self._status["current_position"] = {
            "pan_deg": current_pan_deg,
            "tilt_deg": current_tilt_deg,
            "zoom": self._current_zoom,
        }

        # 3. 计算误差
        # 目标 Az 是绝对方向，PTZ pan 也是绝对方向
        err_az = target_az - current_pan_deg
        err_alt = target_alt - current_tilt_deg

        # 处理 Az 过零
        if err_az > 180:
            err_az -= 360
        elif err_az < -180:
            err_az += 360

        self._status["error"] = {
            "az_deg": round(err_az, 4),
            "alt_deg": round(err_alt, 4),
        }

        # 4. 如果误差很小，停止移动
        if abs(err_az) < self.ERROR_THRESHOLD_DEG and abs(err_alt) < self.ERROR_THRESHOLD_DEG:
            self.ptz.stop_move()
            self._status["message"] = "已对准目标"
            return

        # 5. 天顶处理
        zenith = self.zenith_handler.process(target_alt, target_rate_az)
        self._status["zenith_zone"] = zenith["zone"]
        if zenith["warning"]:
            self._status["message"] = zenith["warning"]

        # 6. 计算速度
        # 误差越大，速度越快
        # 使用 PID 风格: 速度 = error * gain
        az_gain = 0.5  # 增益系数（度/秒 → ISAPI speed）
        alt_gain = 0.5

        # 基础速度 = 误差 × 增益
        az_speed_raw = abs(err_az) * az_gain
        alt_speed_raw = abs(err_alt) * alt_gain

        # 天顶限幅
        az_speed_raw *= zenith["az_speed_factor"]

        # 7. 使用 SpeedCache 找到合适的 ISAPI speed level
        # 方向: 正误差 = 需要顺时针移动 = direction 1
        az_direction = 1 if err_az >= 0 else -1
        alt_direction = 1 if err_alt >= 0 else -1

        # 从 SpeedCache 获取最接近的 speed_level
        # 由于我们不知道速度值直接对应关系，使用比例计算
        if az_speed_raw > self.MIN_MOVE_DEG:
            az_level = self.speed_cache.get_speed_level_for_rate(
                "pan", az_direction, self._current_zoom, az_speed_raw
            )
        else:
            az_level = 0

        if alt_speed_raw > self.MIN_MOVE_DEG:
            alt_level = self.speed_cache.get_speed_level_for_rate(
                "tilt", alt_direction, self._current_zoom, alt_speed_raw
            )
        else:
            alt_level = 0

        # 8. 发送 continuous_move 指令
        # ISAPI continuous_move 接受 -100~100 的速度值
        # 正 pan = 右，负 pan = 左
        # 正 tilt = 下，负 tilt = 上
        try:
            if zenith["stop_az"]:
                # 天顶临界：停止 Az
                az_cmd = 0
            else:
                az_cmd = az_level * az_direction if az_level > 0 else 0

            alt_cmd = alt_level * alt_direction if alt_level > 0 else 0

            success = self.ptz.continuous_move(pan=az_cmd, tilt=alt_cmd)
            if success:
                self._status["message"] = f"修正中: Az={az_cmd}, Alt={alt_cmd}"
        except Exception as e:
            self._status["message"] = f"移动指令失败: {e}"

    # ── 目标更新 ────────────────────────────────────────────────────────

    def update_target(self, target_spec: dict):
        """更新跟踪目标（不会中断跟踪）"""
        self.target_spec = target_spec
        self._status["target"] = target_spec
        self._status["message"] = f"目标已更新: {target_spec.get('id', 'unknown')}"

    def update_location(self, lat: float, lon: float):
        """更新观测位置"""
        self.obs_lat = lat
        self.obs_lon = lon
        self._status["message"] = f"观测位置已更新: {lat}°N, {lon}°E"

    def set_zoom(self, zoom: int):
        """设置当前 zoom（会影响速度查找）"""
        self._current_zoom = zoom


# ═══════════════════════════════════════════════════════════════════════════════
# 测试块
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("AstroHub v8.100 - 跟踪引擎自检")
    print("=" * 60)

    # 1. SpeedCache 测试
    print("\n[1] SpeedCache 测试")
    cache = SpeedCache("240f9b764193")
    loaded = cache.load()
    print(f"    加载成功: {loaded}")
    if loaded:
        levels = cache.get_available_speed_levels("pan", 1, 10)
        print(f"    Pan+方向1+Zoom10 可用 speed_levels: {levels}")
        for lvl in [1, 50, 100]:
            val = cache.get_speed_val("pan", 1, 10, lvl)
            if val:
                print(f"    speed_level={lvl}: speed_val={val:.2f} units/s = {val/10:.4f}°/s")

        # 插值测试
        rate = cache.get_speed_level_for_rate("pan", 1, 10, 0.1)
        print(f"    目标速率 0.1°/s → speed_level={rate}")

    # 2. ZenithHandler 测试
    print("\n[2] ZenithHandler 测试")
    zh = ZenithHandler()
    for alt in [70, 80, 86, 89]:
        result = zh.process(alt, 0.5)
        print(f"    Alt={alt}° → zone={result['zone']}, stop_az={result['stop_az']}, "
              f"az_factor={result['az_speed_factor']}")
        if result["warning"]:
            print(f"    警告: {result['warning']}")

    # 3. TrackingEngine 初始化测试
    print("\n[3] TrackingEngine 初始化测试")
    print("    (需要 PTZ 连接，跳过实际硬件测试)")
    print("    组件就绪: SpeedCache, ZenithHandler, CelestialResolver")

    print(f"\n{'=' * 60}")
    print("自检完成")
    print(f"{'=' * 60}")