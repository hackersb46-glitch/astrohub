"""
AstroHub v2.0 - 限位测试模块 (Limit Testing)

实现 P6.0-P6.6 完整限位测试:
- P6.0: 检查设备是否支持 P/T/Z
- P6.1: gotohome 回到预置点10，验证稳定性
- P6.2: MAC识别，更新config
- P6.3: P轴限位 - PAN=50 移动，检测3600→0穿越，记录上下限
- P6.4: T轴限位/翻转 - Tilt=+50 上移，判断翻转(900阈值)，Tilt=-50 下移，下限-200
- P6.5: Z轴限位 - Zoom+/-50 移动，检测2s数值不变停止，获上下限(上限320/下限10)
- P6.6: 设备还原 - 恢复默认参数，回到10号home位
- 每次移动后读取位置，写入 CSV (record/limit_时间戳.csv)

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import csv
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.ptz.isapi.client import ISAPIClient
from src.ptz.isapi.ptz import PTZController
from src.ptz.constants import (
    ISAPI_CHANNEL,
    DEFAULT_PTZ_PRESET,
    HOME_COORDS,
    STABILIZATION_SECONDS,
    SAMPLE_INTERVAL,
    STABLE_POINTS_REQUIRED,
)
from src.config_paths import RECORD_DIR
from src.ptz.core.logger import LOG


class LimitTester:
    """PTZ 限位测试器 - P6.0 至 P6.6 完整限位测试。"""

    # 限位常量
    PAN_MAX = 3600
    PAN_MIN = 0
    TILT_MAX = 900
    TILT_MIN = -200
    TILT_FLIP_THRESHOLD = 900  # 翻转阈值
    ZOOM_MAX = 320  # P6.5 测试阶段上限
    ZOOM_MIN = 10   # P6.5 测试阶段下限
    ZOOM_STABLE_SECONDS = 2.0  # ZOOM持续无变化时间阈值

    def __init__(self, client: ISAPIClient) -> None:
        self.client = client
        self.ptz = PTZController(client)
        self.channel = ISAPI_CHANNEL
        self._csv_path: str = ""
        self._positions: list[dict] = []
        self._pan_limits: dict = {"min": None, "max": None}
        self._tilt_limits: dict = {"min": None, "max": None}
        self._zoom_limits: dict = {"min": None, "max": None}
        self._has_flip: bool = False

    def _get_csv_path(self) -> str:
        """生成 CSV 文件路径：record/limit_时间戳.csv"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = RECORD_DIR / f"limit_{timestamp}.csv"
        RECORD_DIR.mkdir(parents=True, exist_ok=True)
        self._csv_path = str(csv_path)
        return self._csv_path

    def _write_csv_row(self, pan: float, tilt: float, zoom: float) -> None:
        """写入单行 CSV 数据。"""
        if not self._csv_path:
            self._get_csv_path()

        file_exists = os.path.exists(self._csv_path)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S.%f")[:23]

        with open(self._csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["timestamp", "pan", "tilt", "zoom"])
            writer.writerow([timestamp, pan, tilt, zoom])

    def _get_position(self) -> dict[str, float]:
        """获取当前 PTZ 位置。"""
        pos = self.ptz.get_position()
        if pos:
            return pos
        return {"pan": 0.0, "tilt": 0.0, "zoom": 0.0}

    def _move_and_record(
        self,
        pan_speed: float = 0,
        tilt_speed: float = 0,
        duration: float = 2.0,
        sample_interval: float = 0.1,
    ) -> list[dict]:
        """持续移动并记录位置。"""
        positions = []

        # 启动移动
        if not self.ptz.continuous_move(pan=pan_speed, tilt=tilt_speed):
            return positions

        # 采样
        start = time.time()
        while time.time() - start < duration:
            pos = self._get_position()
            positions.append(pos)
            self._write_csv_row(pos.get("pan", 0), pos.get("tilt", 0), pos.get("zoom", 0))
            time.sleep(sample_interval)

        # 停止移动
        self.ptz.continuous_move(0, 0, 0)
        time.sleep(0.5)

        self._positions.extend(positions)
        return positions

    # --- P6.0: 检查设备是否支持 P/T/Z ---

    def check_ptz_support(self) -> dict[str, bool]:
        """P6.0: 检查设备是否支持 Pan/Tilt/Zoom。

        严格按照CSV: 通过获取PTZ位置判断轴支持情况。
        每个轴独立判断，屏幕显示是否支持。
        """
        support = {"pan": False, "tilt": False, "zoom": False}

        pos = self._get_position()
        if pos:
            support["pan"] = "pan" in pos
            support["tilt"] = "tilt" in pos
            support["zoom"] = "zoom" in pos

        # 屏幕显示是否支持 (CSV评审标准)
        pan_text = "支持" if support["pan"] else "不支持"
        tilt_text = "支持" if support["tilt"] else "不支持"
        zoom_text = "支持" if support["zoom"] else "不支持"
        LOG.log('info',
                f'P/T/Z 轴支持情况: Pan={pan_text}, Tilt={tilt_text}, Zoom={zoom_text}'
        )

        return support

    # --- P6.1: GotoHome 稳定性验证 ---

    def goto_home_verify_stability(self) -> dict[str, Any]:
        """P6.1: 回到预置点10 (HOME位)，验证稳定性。连续 20 点采样，每点严格匹配 HOME 坐标。"""
        result = {
            "success": False,
            "home_preset": DEFAULT_PTZ_PRESET,
            "stability_check": False,
            "readings": [],
            "deviation": 0.0,
        }

        # Step 1: Go to preset 10 (HOME)
        home_success = self.ptz.goto_preset(DEFAULT_PTZ_PRESET)
        if not home_success:
            result["success"] = False
            result["error"] = "goto_preset(10) 失败"
            return result

        time.sleep(STABILIZATION_SECONDS)

        # Step 2: 持续采样 20 点 @ 0.1s
        readings = []
        for i in range(20):
            pos = self._get_position()
            readings.append(pos)
            self._write_csv_row(pos.get("pan", 0), pos.get("tilt", 0), pos.get("zoom", 0))
            time.sleep(0.1)

        result["readings"] = readings

        # Step 3: 每点严格匹配 HOME_COORDS (pan=1800, tilt=450, zoom=10)
        expected = HOME_COORDS  # {"pan": 1800, "tilt": 450, "zoom": 10}
        all_match = True
        max_deviation = 0.0

        for r in readings:
            pan_dev = abs(r.get("pan", 0) - expected["pan"])
            tilt_dev = abs(r.get("tilt", 0) - expected["tilt"])
            zoom_dev = abs(r.get("zoom", 0) - expected["zoom"])
            point_dev = max(pan_dev, tilt_dev, zoom_dev)
            max_deviation = max(max_deviation, point_dev)

            # Strict matching: pan within ±10, tilt within ±5, zoom within ±1
            if pan_dev > 10 or tilt_dev > 5 or zoom_dev > 1:
                all_match = False

        result["deviation"] = round(max_deviation, 2)
        result["stability_check"] = all_match
        result["success"] = True
        return result

    # --- P6.2: MAC 识别 ---

    def identify_mac(self) -> dict[str, Any]:
        """P6.2: MAC识别，用于更新config。"""
        result = {
            "mac": "",
            "model": "",
            "serial_number": "",
            "firmware_version": "",
            "identified": False,
        }

        try:
            import xml.etree.ElementTree as ET

            response = self.client.get("/System/deviceInfo")
            if response.status_code == 200:
                root = ET.fromstring(response.xml)

                def find_text(tag: str, default: str = "") -> str:
                    for elem in root.iter():
                        local_name = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                        if local_name.lower() == tag.lower():
                            return (elem.text or default).strip()
                    return default

                result["mac"] = find_text("macAddress", "")
                result["model"] = find_text("model", "")
                result["serial_number"] = find_text("serialNumber", "")
                result["firmware_version"] = find_text("firmwareVersion", "")
                result["identified"] = bool(result["mac"])
        except Exception:
            pass

        return result

    # --- P6.3: P轴限位测试 ---

    def test_pan_limits(self) -> dict[str, Any]:
        """P6.3: P轴限位测试 - 严格按照CSV列D方法。

        步骤:
        1. gotohome 回到零位，稳定STABILIZATION_SECONDS
        2. 正向 PAN=+50 连续移动，实时监测跳变/稳定，立刻停止
        3. 稳定1秒
        4. 反向 PAN=-50 连续移动，实时监测跳变/稳定，立刻停止
        5. 回到HOME位，稳定1秒
        6. 构建结果返回
        """
        result = {
            "success": False,
            "pan_min": self.PAN_MIN,
            "pan_max": self.PAN_MAX,
            "crossing_detected": False,
            "is_infinite": False,
            "readings": [],
            "error": None,
        }

        # 步骤1: 回到 HOME 位作为起点，稳定
        if not self.ptz.goto_home():
            result["error"] = "回到HOME失败"
            return result

        time.sleep(STABILIZATION_SECONDS)

        pan_positive_infinite = False
        pan_negative_infinite = False
        pan_max_val = self.PAN_MAX  # default if infinite
        pan_min_val = self.PAN_MIN  # default if infinite

        # 步骤2: 正向 PAN=+50 连续移动监测
        self.ptz.continuous_move(pan=50, tilt=0, zoom=0)
        last_pan = None
        same_pan_count = 0
        start_time = time.time()
        positive_exited = False

        while not positive_exited and (time.time() - start_time) < 30.0:
            pos = self._get_position()
            current_pan = pos.get("pan", 0)
            self._write_csv_row(current_pan, pos.get("tilt", 0), pos.get("zoom", 0))
            result["readings"].append({
                "pan": current_pan,
                "direction": "positive",
                "same_count": same_pan_count,
            })

            if last_pan is not None:
                # JUMP CHECK: delta > 1800
                if abs(current_pan - last_pan) > 1800:
                    self.ptz.continuous_move(0, 0, 0)
                    pan_positive_infinite = True
                    result["readings"].append({
                        "jump_detected": True, "from": last_pan, "to": current_pan,
                        "direction": "positive", "reason": "delta > 1800"
                    })
                    positive_exited = True
                    break

                # STABLE CHECK: 连续20次相同值
                if current_pan == last_pan:
                    same_pan_count += 1
                    if same_pan_count >= 20:
                        self.ptz.continuous_move(0, 0, 0)
                        pan_max_val = int(current_pan)
                        result["readings"].append({
                            "stable_detected": True, "pan": current_pan,
                            "direction": "positive", "same_count": same_pan_count
                        })
                        positive_exited = True
                        break
                else:
                    same_pan_count = 0

            last_pan = current_pan
            time.sleep(0.1)

        if not positive_exited:
            # 超时未检出
            self.ptz.continuous_move(0, 0, 0)
            result["readings"].append({
                "timeout": True, "pan": current_pan, "direction": "positive"
            })

        # 正向已判定无限位，直接返回结果，不测反向
        if pan_positive_infinite:
            self.ptz.goto_home()
            time.sleep(1)
            result["pan_min"] = self.PAN_MIN
            result["pan_max"] = self.PAN_MAX
            result["is_infinite"] = True
            result["crossing_detected"] = True
            result["readings"].append({"conclusion": "无限位（正向检测到跳变）"})
            result["success"] = True
            return result

        # 步骤3: 稳定
        time.sleep(1)

        # 步骤4: 反向 PAN=-50 连续移动监测（仅当正向未判定无限位时执行）
        same_pan_count = 0
        last_pan = None
        start_time = time.time()
        negative_exited = False

        self.ptz.continuous_move(pan=-50, tilt=0, zoom=0)

        while not negative_exited and (time.time() - start_time) < 30.0:
            pos = self._get_position()
            current_pan = pos.get("pan", 0)
            self._write_csv_row(current_pan, pos.get("tilt", 0), pos.get("zoom", 0))
            result["readings"].append({
                "pan": current_pan,
                "direction": "negative",
                "same_count": same_pan_count,
            })

            if last_pan is not None:
                # JUMP CHECK: delta > 1800
                if abs(current_pan - last_pan) > 1800:
                    self.ptz.continuous_move(0, 0, 0)
                    pan_negative_infinite = True
                    result["readings"].append({
                        "jump_detected": True, "from": last_pan, "to": current_pan,
                        "direction": "negative", "reason": "delta > 1800"
                    })
                    negative_exited = True
                    break

                # STABLE CHECK: 连续20次相同值
                if current_pan == last_pan:
                    same_pan_count += 1
                    if same_pan_count >= 20:
                        self.ptz.continuous_move(0, 0, 0)
                        pan_min_val = int(current_pan)
                        result["readings"].append({
                            "stable_detected": True, "pan": current_pan,
                            "direction": "negative", "same_count": same_pan_count
                        })
                        negative_exited = True
                        break
                else:
                    same_pan_count = 0

            last_pan = current_pan
            time.sleep(0.1)

        if not negative_exited:
            # 超时未检出
            self.ptz.continuous_move(0, 0, 0)
            result["readings"].append({
                "timeout": True, "pan": current_pan, "direction": "negative"
            })

        # 步骤5: 回到HOME位
        self.ptz.goto_home()
        time.sleep(1)

        # 步骤6: 构建结果
        is_infinite = pan_positive_infinite or pan_negative_infinite
        result["pan_min"] = pan_min_val
        result["pan_max"] = pan_max_val
        result["is_infinite"] = is_infinite
        result["crossing_detected"] = is_infinite

        if is_infinite:
            result["readings"].append({"conclusion": "无限位（检测到跳变）"})
        elif pan_max_val != self.PAN_MAX or pan_min_val != self.PAN_MIN:
            result["readings"].append({
                "conclusion": "有限位",
                "pan_min": pan_min_val,
                "pan_max": pan_max_val,
            })
        else:
            result["readings"].append({"conclusion": "未知（超时未检出）"})

        result["success"] = True
        return result

    # --- P6.4: T轴限位 + 翻转测试 ---

    def test_tilt_limits_and_flip(self) -> dict[str, Any]:
        """P6.4: T轴限位/翻转测试 - 严格按照CSV列D方法。

        步骤:
        1. gotohome 回到home位，稳定 STABILIZATION_SECONDS
        2. Tilt=+50 方向移动，到达900后20点内出现数值下降 → 翻转
           翻转后继续运动直到T达到最小值（20点不变）
           若Tilt+50在某点位出现超过20点数值无变化 → 无翻转，记录上限
        3. 稳定1秒
        4. Tilt=-50 测量下限，20点不变即停止
        5. 回到HOME
        """
        result = {
            "success": False,
            "tilt_min": self.TILT_MIN,
            "tilt_max": self.TILT_MAX,
            "has_flip": False,
            "flip_detected_at": None,
            "readings": [],
            "error": None,
        }

        # 步骤1: 回到 HOME 位，稳定
        if not self.ptz.goto_home():
            result["error"] = "回到HOME失败"
            return result

        time.sleep(STABILIZATION_SECONDS)

        # 步骤2: 正向 Tilt=+50 上移
        self.ptz.continuous_move(pan=0, tilt=50, zoom=0)
        flipped = False
        peak_tilt = 0.0
        readings_up = []
        same_tilt_count = 0
        last_tilt = None
        tilt_stopped = False
        start = time.time()

        while not tilt_stopped and (time.time() - start) < 60.0:
            time.sleep(SAMPLE_INTERVAL)
            pos = self._get_position()
            t = pos.get("tilt", 0)
            self._write_csv_row(pos.get("pan", 0), t, pos.get("zoom", 0))
            readings_up.append(t)
            peak_tilt = max(peak_tilt, t)

            # 翻转判断: 到达 900 后 20 点内出现数值下降
            if t >= self.TILT_FLIP_THRESHOLD - 50 and peak_tilt >= self.TILT_FLIP_THRESHOLD:
                # 达到900附近后，检查后续窗口内是否有下降
                idx = len(readings_up) - 1
                recent_window = readings_up[max(0, idx - 20):idx]
                if len(recent_window) >= 10:
                    recent_peak = max(recent_window)
                    latest_vals = readings_up[idx - 3:idx + 1] if idx >= 3 else readings_up
                    if any(v < recent_peak - 0.5 for v in latest_vals) and not flipped:
                        flipped = True
                        result["readings"].append({
                            "flip_detected": True,
                            "peak_tilt": peak_tilt,
                            "at_index": idx,
                        })

            # 稳定检测: 连续20点数值不变 → 到达极限
            if last_tilt is not None and abs(t - last_tilt) < 0.5:
                same_tilt_count += 1
                if same_tilt_count >= STABLE_POINTS_REQUIRED:
                    tilt_stopped = True
                    result["readings"].append({
                        "stable_detected": True, "tilt": t,
                        "direction": "up", "same_count": same_tilt_count,
                    })
            else:
                same_tilt_count = 0

            last_tilt = t

        # 停止正向运动
        self.ptz.continuous_move(0, 0, 0)
        tilt_up_end = last_tilt if last_tilt is not None else peak_tilt
        result["readings"].append({"direction": "up_end", "tilt": tilt_up_end})
        time.sleep(1)

        # 记录翻转状态
        if flipped:
            result["has_flip"] = True
            self._has_flip = True
            result["tilt_max"] = self.TILT_MAX  # 翻转上限=900
            result["flip_detected_at"] = peak_tilt
        else:
            # 无翻转，上限为稳定值
            if tilt_stopped:
                result["tilt_max"] = int(tilt_up_end)
            else:
                result["tilt_max"] = self.TILT_MAX
            result["has_flip"] = False

        result["readings"].append({
            "flip": result["has_flip"],
            "tilt_max": result["tilt_max"],
        })

        # 步骤4: 反向 Tilt=-50 下移测下限
        self.ptz.continuous_move(pan=0, tilt=-50, zoom=0)
        same_tilt_count = 0
        last_tilt = None
        tilt_stopped = False
        tilt_down_end = None
        start = time.time()

        while not tilt_stopped and (time.time() - start) < 60.0:
            time.sleep(SAMPLE_INTERVAL)
            pos = self._get_position()
            t = pos.get("tilt", 0)
            self._write_csv_row(pos.get("pan", 0), t, pos.get("zoom", 0))

            if last_tilt is not None and abs(t - last_tilt) < 0.5:
                same_tilt_count += 1
                if same_tilt_count >= STABLE_POINTS_REQUIRED:
                    tilt_stopped = True
                    tilt_down_end = t
                    result["readings"].append({
                        "stable_detected": True, "tilt": t,
                        "direction": "down", "same_count": same_tilt_count,
                    })
            else:
                same_tilt_count = 0

            last_tilt = t

        self.ptz.continuous_move(0, 0, 0)
        time.sleep(1)

        # 步骤5: 回到 HOME
        observed_tilt_min = int(tilt_down_end) if tilt_down_end is not None else self.TILT_MIN
        result["tilt_min"] = observed_tilt_min
        self._tilt_limits["min"] = observed_tilt_min
        self._tilt_limits["max"] = result["tilt_max"]

        result["readings"].append({
            "tilt_min": result["tilt_min"],
            "tilt_max": result["tilt_max"],
            "has_flip": result["has_flip"],
        })

        if not self.ptz.goto_home():
            LOG.log('warning', 'goto_home 失败，尝试 continuous_move(0,0,0) 后重试')
            self.ptz.continuous_move(0, 0, 0)
            time.sleep(2)
            self.ptz.goto_home()
        time.sleep(1)

        result["success"] = True
        return result

    # --- P6.5: Z限位测试 ---

    def test_zoom_limits(self) -> dict[str, Any]:
        """P6.5: Z轴限位 - ZOOM+/-50 移动，持续无变化2s停止，获上下限。"""
        result = {
            "success": False,
            "zoom_min": self.ZOOM_MIN,
            "zoom_max": self.ZOOM_MAX,
            "zoom_min_observed": None,
            "zoom_max_observed": None,
            "readings": [],
            "error": None,
        }

        # 回到 HOME 位
        if not self.ptz.goto_home():
            result["error"] = "回到HOME失败"
            return result
        time.sleep(STABILIZATION_SECONDS)

        # Zoom+ 方向: Z=+50（使用 PTZController 的 zoom_in 接口）
        home_pos = self._get_position()
        home_zoom = home_pos.get("zoom", 0)
        result["readings"].append({"direction": "home", "zoom": home_zoom})

        # Zoom In 方向
        self.ptz.continuous_move(pan=0, tilt=0, zoom=50)
        zoom_in_start = time.time()
        last_zoom_val = home_zoom
        last_change_time = zoom_in_start
        max_zoom_observed = home_zoom

        start = time.time()
        while time.time() - start < 30:  # 最多30s超时保护
            time.sleep(0.1)
            pos = self._get_position()
            z = pos.get("zoom", 0)
            self._write_csv_row(pos.get("pan", 0), pos.get("tilt", 0), z)
            result["readings"].append({"direction": "zoom_in", "zoom": z})
            if z != last_zoom_val:
                last_zoom_val = z
                last_change_time = time.time()
                max_zoom_observed = max(max_zoom_observed, z)
            if time.time() - last_change_time >= self.ZOOM_STABLE_SECONDS:
                LOG.log('done', 'Zoom入限位已稳定2s')
                break
        self.ptz.continuous_move(0, 0, 0)
        time.sleep(1)

        result["zoom_max_observed"] = max_zoom_observed

        # 回到 HOME 位
        self.ptz.goto_home()
        time.sleep(STABILIZATION_SECONDS)

        # Zoom Out 方向: Z=-50 (从 HOME 位开始)
        home_pos = self._get_position()
        home_zoom = home_pos.get("zoom", 0)
        self.ptz.continuous_move(pan=0, tilt=0, zoom=-50)
        last_zoom_val = home_zoom
        last_change_time = time.time()
        min_zoom_observed = home_zoom

        start = time.time()
        while time.time() - start < 30:
            time.sleep(0.1)
            pos = self._get_position()
            z = pos.get("zoom", 0)
            self._write_csv_row(pos.get("pan", 0), pos.get("tilt", 0), z)
            result["readings"].append({"direction": "zoom_out", "zoom": z})
            if z != last_zoom_val:
                last_zoom_val = z
                last_change_time = time.time()
                min_zoom_observed = min(min_zoom_observed, z)
            if time.time() - last_change_time >= self.ZOOM_STABLE_SECONDS:
                LOG.log('done', 'Zoom出限位已稳定2s')
                break
        self.ptz.continuous_move(0, 0, 0)
        time.sleep(1)

        # 回到 HOME
        self.ptz.goto_home()
        time.sleep(STABILIZATION_SECONDS)

        result["zoom_min_observed"] = min_zoom_observed
        # P6.5: ZOOM_MAX=320, ZOOM_MIN=10 per M1_method.csv 测试阶段标准
        result["zoom_min"] = int(min_zoom_observed) if min_zoom_observed is not None else self.ZOOM_MIN
        result["zoom_max"] = int(max_zoom_observed) if max_zoom_observed is not None else self.ZOOM_MAX

        self._zoom_limits["min"] = self.ZOOM_MIN if min_zoom_observed is None else int(min_zoom_observed)
        self._zoom_limits["max"] = self.ZOOM_MAX if max_zoom_observed is None else int(max_zoom_observed)

        result["success"] = True

        return result

    # --- P6.6: 设备还原 ---

    def restore_device(self) -> bool:
        """P6.6: 设备还原 - 停止数据读写，恢复默认参数，回到10号home位。"""
        try:
            # 调用设备恢复默认 API
            import xml.etree.ElementTree as ET
            result = self.client.get("/System/deviceInfo")
            if result.status_code == 200:
                # 设备在线，尝试恢复默认
                restore_xml = '<?xml version="1.0" encoding="UTF-8"?>'
                restore_xml += '<restore xmlns="http://www.hikvision.com/ver20/XMLSchema"/>'
                restore_result = self.client.put("/System/restoreDefaults", restore_xml)
                if restore_result.status_code == 200:
                    LOG.log('done', '设备参数已恢复默认')
                    time.sleep(5)  # 等待设备应用恢复
                else:
                    LOG.log('warning', '设备还原API未成功，继续回到HOME位')
        except Exception as e:
            LOG.log('warning', '设备还原异常: %s，继续回到HOME位' % e)

        # 回到 10 号 home 位
        return self.ptz.goto_preset(DEFAULT_PTZ_PRESET)

    # --- 完整测试流程 ---

    def run_all_tests(self) -> dict[str, Any]:
        """运行所有限位测试 (P6.0-P6.6)，返回完整结果。
        
        注: 预置点10 的设置已在 function.py 中作为第一步执行，此处不再重复设置。
        """

        # 初始化 CSV
        self._get_csv_path()

        # P6.0: 检查支持
        support_check = self.check_ptz_support()

        if not all(support_check.values()):
            return {
                "success": False,
                "message": "设备不完全支持 P/T/Z",
                "support": support_check,
            }

        # P6.1: Home 稳定性
        stability = self.goto_home_verify_stability()

        # P6.2: MAC 识别
        mac_info = self.identify_mac()

        # P6.3: P轴限位
        pan_limits = self.test_pan_limits()

        # P6.4: T轴限位 + 翻转
        tilt_limits = self.test_tilt_limits_and_flip()

        # P6.5: Z轴限位
        zoom_limits = self.test_zoom_limits()

        # P6.6: 设备还原
        restore_ok = self.restore_device()

        # 回到 HOME（重试确保成功）
        home_ok = self.ptz.goto_home()
        if not home_ok:
            LOG.log('warning', 'limit 测试结束 goto_home 失败，重试')
            self.ptz.continuous_move(0, 0, 0)
            time.sleep(2)
            home_ok = self.ptz.goto_home()
        time.sleep(1)
        if home_ok:
            LOG.log('done', 'limit 测试完成，设备已回到 HOME 位')
        else:
            LOG.log('error', 'limit 测试完成，回到 HOME 位失败')

        return {
            "success": True,
            "pan_min": pan_limits.get("pan_min", self.PAN_MIN),
            "pan_max": pan_limits.get("pan_max", self.PAN_MAX),
            "tilt_min": tilt_limits.get("tilt_min", self.TILT_MIN),
            "tilt_max": tilt_limits.get("tilt_max", self.TILT_MAX),
            "zoom_min": zoom_limits.get("zoom_min", self.ZOOM_MIN),
            "zoom_max": zoom_limits.get("zoom_max", self.ZOOM_MAX),
            "has_flip": tilt_limits.get("has_flip", False),
            "stability_check": stability.get("stability_check", False),
            "mac_info": mac_info,
            "csv_path": self._csv_path,
            "restore_ok": restore_ok,
        }

    def get_status(self) -> dict[str, Any]:
        """获取当前测试状态。"""
        return {
            "csv_path": self._csv_path,
            "positions_recorded": len(self._positions),
            "pan_limits": self._pan_limits,
            "tilt_limits": self._tilt_limits,
            "zoom_limits": self._zoom_limits,
            "has_flip": self._has_flip,
        }
