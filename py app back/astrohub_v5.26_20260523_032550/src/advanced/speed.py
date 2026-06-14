"""
AstroHub v2.0 - 速度测试模块 (Speed Testing)

实现速度测试:
- measure_speed_single: 单点速度测量，11秒采样110个样本，写入原始CSV
- post_process_csv: 从原始CSV读取，按(axis, direction, speed_level, zoom)分组计算速度
- run_all_tests: Pan/Tilt 全轴测试，所有测量写入原始CSV，完成后调用post_process_csv

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import csv
import time
from datetime import datetime
from pathlib import Path
from typing import Any

SPEED_PROFILES = {
    'lite': [1, 50, 100],
    'medium': [1, 20, 40, 60, 80, 100],
    'full': [1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100],
}


def _set_zoom_absolute(ptz, zoom_val: int, az=1800, el=450) -> bool:
    """Set absolute zoom position using absolute_move with zoom parameter."""
    return ptz.absolute_move(pan=az, tilt=el, zoom=zoom_val, speed=50)


def _goto_pan_start(ptz, positive: bool, pan_limit_max, pan_limit_min: int, zoom: int) -> None:
    """Pan 起始位置 per CSV spec.

    - 有限位: absolute_move(P_max/P_min, el=450, zoom) → wait_stable
    - 无限位: preset_goto(10) → sleep(3) → wait_stable
    """
    p_max = pan_limit_max if pan_limit_max != "INFINITE" else None

    if p_max is not None:  # 有限位
        if positive:
            ptz.absolute_move(pan=p_max, tilt=450, zoom=zoom)
        else:
            ptz.absolute_move(pan=pan_limit_min, tilt=450, zoom=zoom)
        ptz.wait_stable()
    else:  # 无限位
        ptz.goto_preset(10)
        time.sleep(3)
        ptz.wait_stable()


def _goto_tilt_start(ptz, positive: bool, tilt_limits: dict, zoom: int) -> None:
    """Tilt 起始位置 per CSV spec.

    - 正向(+): absolute_move(az=1800, el=T_max, zoom)
    - 负向(-): absolute_move(az=1800, el=T_min, zoom)
    """
    t_min = tilt_limits.get("min", -200)
    t_max = tilt_limits.get("max", 900)

    if positive:
        ptz.absolute_move(pan=1800, tilt=t_max, zoom=zoom)
    else:
        ptz.absolute_move(pan=1800, tilt=t_min, zoom=zoom)
    ptz.wait_stable()


def measure_speed_single(ptz: Any, axis: str, speed_level: int, raw_csv_path: str, direction: str = "forward", zoom_val: int = 10) -> list[float]:
    """测量单轴单速度点的位移，将所有样本写入原始CSV。

    Per M1_speed_method.csv P5:
    - 11秒 continuous_move → 每0.1秒采样 → 共110个样本
    - 每个样本立即写入原始CSV (timestamp, axis, direction, speed_level, zoom, position)

    Args:
        ptz: PTZController 实例
        axis: 轴名称 ('pan' 或 'tilt')
        speed_level: 速度等级 (正值, 用于continuous_move的方向由caller保证)
        raw_csv_path: 原始CSV文件路径
        direction: 测试方向 ('forward' 或 'reverse')
        zoom_val: 当前zoom档位 (默认10)

    Returns:
        list[float]: 全部110个采样点位置值
    """
    duration = 11.0
    interval = 0.1
    target_samples = int(duration / interval)  # 110

    ptz.continuous_move(
        pan=speed_level if axis == "pan" else 0,
        tilt=speed_level if axis == "tilt" else 0,
    )

    samples: list[float] = []
    for _ in range(target_samples):
        position = ptz.get_position()
        pos = position.get(axis, 0.0) if position else 0.0
        samples.append(pos)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        with open(raw_csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, axis, direction, speed_level, zoom_val, pos])
        time.sleep(interval)

    ptz.stop_move()

    return samples


def post_process_csv(raw_csv_path: str, mac: str) -> list[dict[str, Any]]:
    """对原始 CSV 数据进行后处理：flip 检测 + 速度计算。

    Per M1_speed_method.csv P5:
    - 按 (axis, direction, speed_level, zoom) 分组
    - valid = positions[5:-5] (丢弃前后各5)
    - 速度 = |end_pos - start| * 0.1 / 10.0 deg/s (除以10.0, 4位小数)
    - 限位flip检测: valid[i] < valid[i-1] (正向撞限位), valid[i] > valid[i-1] (反向)
    - end_pos = valid[i-2] (排除触发点i、i-1、限位点i-2); i<2时取valid[0]
    """
    results: list[dict[str, Any]] = []

    with open(raw_csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        axis = row.get("axis", "").strip()
        direction = row.get("direction", "").strip()
        speed_level = int(row.get("speed_level", 0))
        zoom = int(row.get("zoom", 0))
        pos = float(row.get("position", 0.0))
        key = (axis, direction, speed_level, zoom)
        groups.setdefault(key, []).append({"position": pos})

    for (axis, direction, speed_level, zoom), entries in groups.items():
        positions = [e["position"] for e in entries]
        valid = positions[5:-5]  # 丢弃首尾5样本
        if len(valid) < 2:
            continue

        start = positions[0]  # start = 原始第一个位置 (before discard)
        sign = 1 if direction == "forward" else -1

        # 默认 end_pos 为有效窗口最后一个
        end_pos = valid[-1]
        hit_limit = False

        # 限位flip检测
        if sign > 0:
            for i in range(1, len(valid)):
                if valid[i] < valid[i - 1]:  # 正方向撞限位 (位置变小)
                    end_pos = valid[i - 2] if i >= 2 else valid[0]
                    hit_limit = True
                    break
        else:
            for i in range(1, len(valid)):
                if valid[i] > valid[i - 1]:  # 反向撞限位 (位置变大)
                    end_pos = valid[i - 2] if i >= 2 else valid[0]
                    hit_limit = True
                    break

        # 速度 = |end_pos - start| * 0.1 / 10.0, 4位小数
        speed_val = round(abs(end_pos - start) * 0.1 / 10.0, 4)

        results.append({
            "mac": mac,
            "axis": axis,
            "direction": direction,
            "speed_level": speed_level,
            "speed_val": speed_val,
            "start_pos": round(start, 4),
            "end_pos": round(end_pos, 4),
            "hit_limit": hit_limit,
            "zoom": zoom,
        })

    return results


def run_all_tests(ptz: Any, config: Any, mac: str, limit_map: dict | None = None, speed_profile: str = 'lite') -> dict[str, Any]:
    """运行完整速度测试 (3档Zoom x Pan/Tilt x 4档速度), 结果写入 config。

    Per M1_speed_method.csv P6-P8:
    - Zoom 档位: Z_min=10, Z_mid=165, Z_max=320
    - 每档Zoom: 测试Pan(1/25/50/100) + Tilt(1/25/50/100)
    - Pan起始: 有限位→absolute_move(P_max/P_min), 无限位→preset_goto(10)
    - Tilt起始: absolute_move(1800, T_max/T_min)
    - 每档测完回HOME (P8.1): preset_goto(10) → sleep(3) → 验证位置(tolerance=0)

    流程:
    步骤1: 执行所有测量，每测一次写入原始CSV (每个采样点一行)
    步骤2: 所有测试完成后，调用 post_process_csv 从原始CSV读取并计算速度
    步骤3: 结果写入 config
    """
    # --- 限位值动态读取 ---
    pan_limit_max = "INFINITE"  # 默认无限位
    pan_limit_min = 0
    tilt_limits = {"min": -200, "max": 900}

    if limit_map:
        pan_data = limit_map.get("pan", {})
        pan_limit_max = pan_data.get("max", "INFINITE")
        pan_limit_min = pan_data.get("min", 0)
        tilt_data = limit_map.get("tilt", {})
        tilt_limits = {"min": tilt_data.get("min", -200), "max": tilt_data.get("max", 900)}

    speed_levels = SPEED_PROFILES.get(speed_profile, SPEED_PROFILES['lite'])
    zoom_levels = [10, 165, 320]  # Z_min, Z_mid, Z_max

    # --- 创建原始CSV文件 ---
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_csv_path = str(Path("data/records") / f"speed_raw_{mac}_{timestamp_str}.csv")
    Path(raw_csv_path).parent.mkdir(parents=True, exist_ok=True)
    with open(raw_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "axis", "direction", "speed_level", "zoom", "position"])

    for zi, zoom_val in enumerate(zoom_levels):
        # 切换到目标Zoom档
        _set_zoom_absolute(ptz, zoom_val)
        time.sleep(2)

        # --- Pan 轴测试 ---
        for speed in speed_levels:
            # 正向(+)
            _goto_pan_start(ptz, positive=True, pan_limit_max=pan_limit_max, pan_limit_min=pan_limit_min, zoom=zoom_val)
            measure_speed_single(ptz, "pan", speed, raw_csv_path=raw_csv_path, direction="forward", zoom_val=zoom_val)
            time.sleep(2)

            # 反向(-)
            _goto_pan_start(ptz, positive=False, pan_limit_max=pan_limit_max, pan_limit_min=pan_limit_min, zoom=zoom_val)
            measure_speed_single(ptz, "pan", speed, raw_csv_path=raw_csv_path, direction="reverse", zoom_val=zoom_val)
            time.sleep(2)

        # --- Tilt 轴测试 ---
        for speed in speed_levels:
            # 正向(+): 从T_max=900出发, 向T_min方向移动
            _goto_tilt_start(ptz, positive=True, tilt_limits=tilt_limits, zoom=zoom_val)
            measure_speed_single(ptz, "tilt", speed, raw_csv_path=raw_csv_path, direction="forward", zoom_val=zoom_val)
            time.sleep(2)

            # 反向(-): 从T_min=-200出发, 向T_max方向移动
            _goto_tilt_start(ptz, positive=False, tilt_limits=tilt_limits, zoom=zoom_val)
            measure_speed_single(ptz, "tilt", speed, raw_csv_path=raw_csv_path, direction="reverse", zoom_val=zoom_val)
            time.sleep(2)

        # P8.1: 每档测完回HOME，再切换下一Zoom
        if zi < len(zoom_levels) - 1:
            ptz.goto_preset(10)
            time.sleep(3)
            s = ptz.get_position()
            if s:
                az, el = s.get("pan", 0), s.get("tilt", 0)
                if az != 1800 or el != 450:
                    pass  # HOME位置偏差 (tolerance=0, 精确匹配)

    # --- 所有测试完成后，从原始CSV计算速度 ---
    all_results = post_process_csv(raw_csv_path, mac)

    # --- 结果写入 config ---
    if hasattr(config, "set"):
        config.set("speed_test.results", all_results)
        config.set("speed_test.mac", mac)
        config.set("speed_test.raw_csv", raw_csv_path)
    elif isinstance(config, dict):
        config.setdefault("speed_test", {})["results"] = all_results
        config.setdefault("speed_test", {})["mac"] = mac
        config.setdefault("speed_test", {})["raw_csv"] = raw_csv_path

    return all_results


class SpeedTester:
    def __init__(self, ptz: Any) -> None:
        self.ptz = ptz

    def run_all_tests(self, config: Any = None, mac: str = '', limit_map: dict | None = None, speed_profile: str = 'lite') -> dict[str, Any]:
        return run_all_tests(self.ptz, config, mac, limit_map, speed_profile)

