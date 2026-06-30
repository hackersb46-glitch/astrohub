"""
AstroHub v2.0 - 速度测试模块 (Speed Testing)

实现速度测试:
- measure_speed_single: 单点速度测量
- post_process_csv: 数据后处理
- run_all_tests: 完整测试流程

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import csv
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from src.advanced.device_path import get_device_info, get_data_path_read, get_data_path_write, get_devices_dir

def _print(msg: str = "", end: str = "\n"):
    """静默可控的print。"""
    import src.ptz.core.logger as logger_module
    if not getattr(logger_module.LOG, 'silent', False):
        print(msg, end=end)

SPEED_PROFILES = {
    'lite': [1, 50, 100],
    'medium': [round(1 + i * (100 - 1) / 7) for i in range(8)],  # 1-100 7等分
    'full': [round(1 + i * (100 - 1) / 25) for i in range(26)],  # 1-100 25等分
}


def load_limit_data(model_short: str, mac_clean: str) -> dict:
    """从limit.json读取限位数据。

    Args:
        model_short: 短型号
        mac_clean: MAC地址(无冒号,小写)

    Returns:
        dict: 限位数据
    """
    import json
    limit_path = get_data_path_read(model_short, mac_clean, 'limit')
    if limit_path is None or not limit_path.exists():
        raise FileNotFoundError("limit.json不存在")
    with open(limit_path, "r", encoding="utf-8") as f:
        return json.load(f)

# Pan轴是360度循环,3600=0
# 所以测试Pan轴时,不要使用3600作为起点,使用0或接近0的值


def measure_speed_single(ptz: Any, axis: str, speed_level: int, raw_csv_path: str,
                         direction: int = 1, zoom_val: int = 10, repeat_idx: int = 0,
                         start_position: float | None = None,
                         limit_data: dict | None = None) -> list[float]:
    """测量单轴单速度点的位移。

    Args:
        ptz: PTZController实例
        axis: 轴名称
        speed_level: 速度等级
        raw_csv_path: CSV路径
        direction: 方向 (1=正向, -1=负向)
        zoom_val: Zoom档位
        repeat_idx: 重复索引
        start_position: 起始位置(绝对移动目标)
        limit_data: 限位数据(从limit.json读取)
        actual_tilt_speed: Tilt轴实际运动速度(正负值,从run_all_tests传入)

    Returns:
        list[float]: 采样点
    """
    # 从limit_data读取限位值
    if limit_data is None:
        raise ValueError("limit_data不能为空,必须从limit.json读取")

    tilt_min = limit_data.get("tilt_min", -200)
    tilt_max = limit_data.get("tilt_max", 900)
    has_flip = limit_data.get("has_flip", False)
    is_infinite = limit_data.get("is_infinite", True)
    pan_min = limit_data.get("pan_min", 0)
    pan_max = limit_data.get("pan_max", 3600)

    # 所有移动开始前必须判断稳定
    # Pan无限位:从当前位置开始,要求稳定
    # Pan有限位/Tilt:绝对移动到起点,验证稳定
    if start_position is not None:
        # 绝对移动到起点
        ptz.absolute_move(
            pan=int(start_position) if axis == "pan" else 1800,
            tilt=int(start_position) if axis == "tilt" else 450,
            zoom=zoom_val,
            speed=50
        )
        # 验证稳定:连续20点绝对相等
        stable_count = 0
        for _ in range(300):  # 最多等待30秒
            pos = ptz.get_position()
            actual = pos.get(axis, 0.0)
            if actual == start_position:
                stable_count += 1
                if stable_count >= 20:
                    break
            else:
                stable_count = 0
            time.sleep(0.1)
        if stable_count < 20:
            _print(f"  警告: 目标{start_position}, 实际{actual:.0f}")
    else:
        # Pan无限位:从当前位置开始,验证稳定
        stable_count = 0
        last_pos = None
        for _ in range(300):
            pos = ptz.get_position()
            actual = pos.get(axis, 0.0)
            if last_pos is not None and actual == last_pos:
                stable_count += 1
                if stable_count >= 20:
                    break
            else:
                stable_count = 0
            last_pos = actual
            time.sleep(0.1)
        if stable_count < 20:
            _print(f"  警告: {axis}轴未稳定")

    # 连续移动
    # Pan/Tilt轴统一使用 speed_level * direction
    actual_speed = speed_level * direction

    ptz.continuous_move(
        pan=actual_speed if axis == "pan" else 0,
        tilt=actual_speed if axis == "tilt" else 0,
    )

    # 采样(检测限位和翻转)
    samples = []
    hit_limit = False
    flip_detected_sampling = False

    for _ in range(110):
        position = ptz.get_position()
        pos = position.get(axis, 0.0) if position else 0.0
        samples.append(pos)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        with open(raw_csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, axis, direction, speed_level, zoom_val, repeat_idx, pos])

        # 检测限位停止
        hit_limit = False

        if axis == "pan":
            # Pan有限位:检测到达限位
            if not is_infinite:
                if pos == pan_max or pos == pan_min:
                    if len(samples) >= 20:
                        recent = samples[-20:]
                        if all(p == pos for p in recent):
                            hit_limit = True
            # Pan无限位:不检测跳变,继续采样到110点

        elif axis == "tilt":
            # Tilt轴限位检测:连续20点达到tmin或tmax
            if pos == tilt_min or pos == tilt_max:
                if len(samples) >= 20:
                    recent = samples[-20:]
                    if all(p == pos for p in recent):
                        hit_limit = True
            
            # Tilt轴翻转检测:趋势反转
            # 只检测趋势变化，不检测初始运动方向
            # 需要至少10个点确定初始趋势
            if len(samples) >= 10:
                # 计算初始趋势(前10个点)
                initial_trend = sum(samples[i] - samples[i-1] for i in range(1, 10))
                # 计算最近5个点趋势
                recent_trend = sum(samples[i] - samples[i-1] for i in range(-4, 0))
                
                # 趋势反转:初始趋势和最近趋势符号相反
                if initial_trend > 0 and recent_trend < 0:
                    # 递增→递减:翻转
                    flip_detected_sampling = True
                    break
                elif initial_trend < 0 and recent_trend > 0:
                    # 递减→递增:翻转
                    flip_detected_sampling = True
                    break

        # 到达限位后立即停止
        if hit_limit:
            break

        time.sleep(0.1)

    # 停止并验证稳定(连续20点位置不变)
    ptz.stop_move()
    stable_count = 0
    last_pos = None
    for _ in range(300):
        pos = ptz.get_position()
        actual = pos.get(axis, 0.0)
        if last_pos is not None and actual == last_pos:
            stable_count += 1
            if stable_count >= 20:
                break
        else:
            stable_count = 0
        last_pos = actual
        time.sleep(0.1)

    return samples


def post_process_csv(raw_csv_path: str, mac: str, limit_data: dict | None = None) -> list[dict[str, Any]]:
    """数据后处理:计算速度。

    Args:
        raw_csv_path: CSV文件路径
        mac: MAC地址
        limit_data: 限位数据(包含direction_info)

    计算规则:
    - 取第6-105个点(索引5:105)
    - 速度 = |end - start| / 10.0
    """
    results = []

    with open(raw_csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # 按组合分组(包含时间戳)
    groups = {}
    for row in rows:
        axis = row.get("axis", "").strip()
        direction = int(row.get("direction", 1))
        speed_level = int(row.get("speed_level", 0))
        zoom = int(row.get("zoom", 0))
        repeat_idx = int(row.get("repeat_idx", 0))
        pos = float(row.get("position", 0.0))
        timestamp = row.get("timestamp", "")
        key = (axis, direction, speed_level, zoom)
        groups.setdefault(key, []).append({"position": pos, "repeat_idx": repeat_idx, "timestamp": timestamp})

    for (axis, direction, speed_level, zoom), entries in groups.items():
        # 读取Pan是否无限位
        is_infinite = limit_data.get("is_infinite", True) if limit_data else True
        pan_min = limit_data.get("pan_min", 0) if limit_data else 0
        pan_max = limit_data.get("pan_max", 3600) if limit_data else 3600
        tilt_min = limit_data.get("tilt_min", -200) if limit_data else -200
        tilt_max = limit_data.get("tilt_max", 900) if limit_data else 900
        
        # 按repeat_idx分组(包含时间戳)
        repeat_groups = {}
        for e in entries:
            idx = e.get("repeat_idx", 0)
            repeat_groups.setdefault(idx, []).append({"position": e["position"], "timestamp": e["timestamp"]})

        speeds = []
        movement_direction = "unknown"
        hit_limit_flag = False

        for repeat_idx, entries in repeat_groups.items():
            # 跳变测试可能少于110点,最少需要10点
            if len(entries) < 10:
                continue

            # 提取位置和时间戳
            positions = [e["position"] for e in entries]
            timestamps = [e["timestamp"] for e in entries]

            # 判断运动方向(前10个点趋势)
            trend_sum = sum(positions[i] - positions[i-1] for i in range(1, 11))
            movement_dir = "increasing" if trend_sum > 0 else ("decreasing" if trend_sum < 0 else "stable")
            movement_direction = movement_dir

            # 检测限位/翻转
            valid_end = len(positions)
            flip_detected = False
            limit_detected = False

            # Pan有限位:检测到达限位(连续20点位置相同且等于min或max)
            # Pan无限位:不需要限位检测
            # Tilt轴:后处理阶段检测到达限位位置，排除限位点
            if axis == "pan" and not is_infinite:
                # Pan有限位:检测首次到达限位位置
                for i in range(len(positions)):
                    if positions[i] == pan_min or positions[i] == pan_max:
                        valid_end = i  # 限位索引-1
                        limit_detected = True
                        break
            elif axis == "tilt":
                # Tilt轴:检测首次到达限位位置
                # 跳过前20点(启动阶段可能就在限位处)
                for i in range(20, len(positions)):
                    if positions[i] == tilt_min or positions[i] == tilt_max:
                        valid_end = i  # 限位索引
                        limit_detected = True
                        break
                
                # Tilt翻转检测:连续5个点趋势与初始趋势相反
                for i in range(10, valid_end):
                    recent_trend = sum(positions[j] - positions[j-1] for j in range(i-4, i+1))
                    
                    if movement_dir == "increasing" and recent_trend < 0:
                        flip_detected = True
                        valid_end = i
                        break
                    elif movement_dir == "decreasing" and recent_trend > 0:
                        flip_detected = True
                        valid_end = i
                        break

            # 选择有效数据
            valid_start = 5  # 排除启停前5个点
            
            # 翻转/限位时:不排除后5点(已通过valid_end排除)
            # 无翻转/无限位时:排除后5点
            if not flip_detected and not limit_detected:
                valid_end = len(positions) - 5

            # 使用限位检测后的valid_end
            valid_positions = positions[valid_start:valid_end]
            valid_timestamps = timestamps[valid_start:valid_end]

            if len(valid_positions) < 2:
                continue

            # Pan无限位:检测跳变次数,分段计算距离
            # 其他情况:累加位移
            if axis == "pan" and is_infinite:
                # 检测跳变点(相邻两点差值绝对值>1800)
                jump_indices = []
                for i in range(1, len(valid_positions)):
                    diff = valid_positions[i] - valid_positions[i-1]
                    if abs(diff) > 1800:
                        jump_indices.append(i)
                
                # 分段计算距离(绝对值累加)
                total_move = 0.0
                
                if len(jump_indices) == 0:
                    # 无跳变:直接计算起点到终点
                    total_move = abs(valid_positions[-1] - valid_positions[0])
                else:
                    # 有跳变:逐段累加
                    prev_idx = 0
                    for jump_idx in jump_indices:
                        # 跳变前的一段:从prev_idx到jump_idx
                        segment_start = valid_positions[prev_idx]
                        segment_end = valid_positions[jump_idx - 1]
                        total_move += abs(segment_end - segment_start)
                        
                        # 跳变跨越的距离(3600边界)
                        jump_from = valid_positions[jump_idx - 1]
                        jump_to = valid_positions[jump_idx]
                        if jump_to < jump_from:
                            # 正向跳变:从3600跳到0
                            total_move += abs(3600 - jump_from) + abs(jump_to - 0)
                        else:
                            # 反向跳变:从0跳到3600
                            total_move += abs(jump_from - 0) + abs(3600 - jump_to)
                        
                        prev_idx = jump_idx
                    
                    # 最后一段:从最后一个跳变点到终点
                    if prev_idx < len(valid_positions) - 1:
                        total_move += abs(valid_positions[-1] - valid_positions[prev_idx])
            else:
                # 累加位移
                total_move = 0.0
                for i in range(1, len(valid_positions)):
                    diff = valid_positions[i] - valid_positions[i-1]
                    total_move += diff

            # 用时间戳计算实际时间
            from datetime import datetime
            start_ts = datetime.strptime(valid_timestamps[0], '%Y-%m-%d %H:%M:%S.%f')
            end_ts = datetime.strptime(valid_timestamps[-1], '%Y-%m-%d %H:%M:%S.%f')
            valid_time = (end_ts - start_ts).total_seconds()

            speed = abs(total_move) / valid_time if valid_time > 0 else 0.0
            speeds.append(speed)

        avg_speed = sum(speeds) / len(speeds) if speeds else 0.0

        # 判断同/反向
        # 从limit_data读取方向信息
        if limit_data:
            axis_dir_info = limit_data.get("direction_info", {}).get(axis, {})
            positive_increases = axis_dir_info.get("positive_command_increases", True)
        else:
            positive_increases = True

        # direction>0: 正命令
        # direction<0: 负命令
        # movement_dir: 实际移动方向(increasing/decreasing)
        if direction > 0:
            # 正命令,如果positive_increases=True,则expected=increasing(同向)
            expected_dir = "increasing" if positive_increases else "decreasing"
        else:
            # 负命令,如果positive_increases=True,则expected=decreasing(同向)
            expected_dir = "decreasing" if positive_increases else "increasing"

        direction_info = "同向" if movement_direction == expected_dir else "反向"

        results.append({
            "mac": mac,
            "axis": axis,
            "direction": direction,
            "speed_level": speed_level,
            "speed_val": round(avg_speed, 2),
            "hit_limit": hit_limit_flag,
            "zoom": zoom,
            "repeats": len(speeds),
            "movement_direction": movement_direction,
            "direction_info": direction_info,
        })

    return results


def run_all_tests(ptz: Any, config: Any = None, speed_profile: str = 'lite', progress_callback=None) -> list[dict[str, Any]]:
    """运行完整速度测试。

    Args:
        ptz: PTZ控制器
        config: 配置（可选）
        speed_profile: 速度档位模式
        progress_callback: 进度回调函数，参数为 (step_name, completed, total, result)
    """
    # 静默模式：禁用日志输出避免资源超限
    import src.ptz.core.logger as logger_module
    logger_module.LOG.silent = True

    # 获取设备信息
    device_info = get_device_info(ptz)
    model_short = device_info['model_short']
    mac_clean = device_info['mac_clean']

    # 从limit.json读取限位数据
    try:
        limit_data = load_limit_data(model_short, mac_clean)
    except FileNotFoundError:
        _print("警告: limit.json不存在,请先运行Limit测试")
        return []

    # 检查direction_info是否存在
    if "direction_info" not in limit_data:
        _print("警告: limit.json中缺少direction_info,请重新运行Limit测试")
        return []

    # 从limit.json读取Zoom限位,计算三个档位
    zoom_min = limit_data.get("zoom_min", 10)
    zoom_max = limit_data.get("zoom_max", 320)
    zoom_mid = int((zoom_min + zoom_max) / 2)
    zoom_levels = [zoom_min, zoom_mid, zoom_max]
    _print(f"Zoom档位: {zoom_levels}")

    speed_levels = SPEED_PROFILES.get(speed_profile, SPEED_PROFILES['lite'])

    # 创建CSV
    csv_path = get_data_path_write(model_short, mac_clean, 'speed')
    csv_path = csv_path.with_suffix('.csv')
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "axis", "direction", "speed_level", "zoom", "repeat_idx", "position"])

    # 从limit.json读取运动方向信息
    direction_info = limit_data.get("direction_info", {})
    pan_dir = direction_info.get("pan", {})
    tilt_dir = direction_info.get("tilt", {})
    _print(f"  Pan: 正命令{'递增' if pan_dir.get('positive_command_increases') else '递减'}")
    _print(f"  Tilt: 正命令{'递增' if tilt_dir.get('positive_command_increases') else '递减'}")

    # 计算总测试数
    total_tests = len(zoom_levels) * len(speed_levels) * 2 * 2 * 3
    current_test = 0

    # 从limit.json读取Pan是否有限位
    pan_has_limit = not limit_data.get("is_infinite", True)
    pan_min = limit_data.get("pan_min", 0)
    pan_max = limit_data.get("pan_max", 3600)

    # Tilt限位
    tilt_min = limit_data.get("tilt_min", -200)
    tilt_max = limit_data.get("tilt_max", 900)

    # 测试开始:稳定在HOME位
    _print("\n稳定在HOME位...")
    if not ptz.goto_home_and_wait():
        _print("  错误: HOME验证失败, 停止测试")
        ptz.continuous_move(0, 0, 0)
        return []

    for zoom_val in zoom_levels:
        # 设置Zoom档位
        ptz.absolute_move(pan=1800, tilt=450, zoom=zoom_val, speed=50)
        stable_count = 0
        for _ in range(300):
            pos = ptz.get_position()
            if pos and abs(pos.get("zoom", 0) - zoom_val) <= 1:
                stable_count += 1
                if stable_count >= 20:
                    break
            else:
                stable_count = 0
            time.sleep(0.1)
        if stable_count < 20:
            _print(f"  警告: Zoom验证失败,目标{zoom_val}")

        for axis in ["pan", "tilt"]:
            for speed in speed_levels:
                for repeat_idx in range(3):
                    for direction in [1, -1]:
                        current_test += 1
                        dir_str = "+" if direction > 0 else "-"
                        axis_short = axis[0].upper()
                        _print(f"  {axis_short}={dir_str}{speed:>3} {repeat_idx+1}/3, 总 {current_test}/{total_tests}", end="\r")
                        
                        # v7.56: 进度回调
                        if progress_callback:
                            step_name = f"{axis_short}{dir_str}速度{speed} Zoom{zoom_val}"
                            progress_callback(step_name, current_test, total_tests, "running")

                        # 确定起点位置
                        if axis == "pan":
                            # Pan无限位时使用虚拟限位: min=10, max=3590
                            pan_min_val = 10 if not pan_has_limit else pan_min
                            pan_max_val = 3590 if not pan_has_limit else pan_max
                            
                            pan_positive_increases = pan_dir.get("positive_command_increases", True)
                            if pan_positive_increases == (direction > 0):
                                start_pos = pan_min_val  # 往大走
                            else:
                                start_pos = pan_max_val  # 往小走
                        else:  # tilt
                            # Tilt:根据direction_info确定起点
                            tilt_positive_increases = tilt_dir.get("positive_command_increases", True)
                            if tilt_positive_increases == (direction > 0):
                                start_pos = tilt_min  # 往大走
                            else:
                                start_pos = tilt_max  # 往小走

                        # 测速(不再每次回HOME)
                        measure_speed_single(
                            ptz, axis, speed, str(csv_path),
                            direction, zoom_val, repeat_idx, start_pos, limit_data
                        )
                        # v7.56: 测试完成回调
                        if progress_callback:
                            progress_callback(step_name, current_test, total_tests, "pass")

    _print()

    # 后处理
    all_results = post_process_csv(str(csv_path), mac_clean, limit_data)

    # 测试完成后回到HOME
    if not ptz.goto_home_and_wait():
        _print("\n警告: Speed测试后回到HOME失败")
    else:
        _print("\nSpeed测试完成,设备已回到HOME位")

    # 保存到speed.json（与CSV同目录）
    try:
        import json
        output_file = csv_path.with_suffix('.json')
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                "success": len(all_results) > 0,
                "total_tests": len(all_results),
                "speed_profile": speed_profile,
                "results": all_results,
                "csv_path": str(csv_path)
            }, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    return all_results



class SpeedTester:
    def __init__(self, ptz: Any) -> None:
        self.ptz = ptz
        self._cancelled = False

    def run_all_tests(self, config: Any = None, speed_profile: str = 'lite', progress_callback=None) -> list[dict[str, Any]]:
        return run_all_tests(self.ptz, config, speed_profile, progress_callback)

    def cancel(self) -> None:
        """取消测试并刹停设备。"""
        self._cancelled = True
        self.ptz.continuous_move(0, 0, 0)


# ================================================================ #
#  缓存读取函数 (v6.19 新增)
# ================================================================ #

def load_cached_speed_results(mac: str) -> dict | None:
    """从本地缓存读取速度测试结果。
    
    v6.19: 优先读取本地缓存，避免每次调用设备API。
    
    Args:
        mac: MAC地址（无分隔符小写）
    
    Returns:
        缓存结果字典，不存在返回 None
    """
    try:
        cache_path = get_data_path_read(None, mac, 'speed')
        if cache_path is None or not cache_path.exists():
            return None
        import json
        with open(cache_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def run_speed_test(
    ip: str = None, 
    username: str = None, 
    password: str = None, 
    port: int = None, 
    speed_profile: str = 'lite',
    mac: str = None,
    use_cache: bool = True
) -> dict:
    """独立运行Speed测试。
    
    v6.19: 优先读取本地缓存，缓存不存在时调用设备API。
    
    Args:
        ip: 设备IP（可选）
        username: 用户名（可选）
        password: 密码（可选）
        port: 端口（可选，默认80）
        speed_profile: 速度档位模式
        mac: MAC地址（可选，用于读取缓存）
        use_cache: 是否优先使用缓存（默认True）
    
    Returns:
        测试结果
    """
    from src.ptz.isapi.client import ISAPIClient
    from src.ptz.isapi.ptz import PTZController
    
    # 1. 优先读取缓存
    if use_cache and mac:
        cached = load_cached_speed_results(mac)
        if cached:
            return {**cached, "from_cache": True}
    
    # 2. 检查必需参数
    if not ip:
        return {"success": False, "error": "缺少设备IP参数"}
    
    # 3. 连接设备并运行测试
    username = username or "admin"
    password = password or ""
    port = port or 80
    
    client = ISAPIClient(ip=ip, username=username, password=password, port=port)
    if not client.verify_credentials():
        return {"success": False, "error": f"设备认证失败: {ip}"}
    
    ptz = PTZController(client)
    results = run_all_tests(ptz, None, speed_profile)
    
    return {
        "success": len(results) > 0,
        "total_tests": len(results),
        "results": results,
        "from_cache": False
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AstroHub Speed测试")
    parser.add_argument("--ip", type=str, required=True, help="设备IP")
    parser.add_argument("--username", type=str, default="admin", help="用户名")
    parser.add_argument("--password", type=str, default="", help="密码")
    parser.add_argument("--port", type=int, default=80, help="端口")
    parser.add_argument("--profile", type=str, default="lite", choices=['lite', 'medium', 'full'], help="速度档位模式")
    parser.add_argument("--mac", type=str, help="MAC地址（用于缓存）")
    parser.add_argument("--no-cache", action="store_true", help="禁用缓存")
    args = parser.parse_args()
    
    _print("=" * 50)
    _print("AstroHub Speed测试")
    _print("=" * 50)
    
    result = run_speed_test(
        ip=args.ip, 
        username=args.username, 
        password=args.password, 
        port=args.port, 
        speed_profile=args.profile,
        mac=args.mac,
        use_cache=not args.no_cache
    )
    
    if result.get("success"):
        cache_note = " (缓存)" if result.get("from_cache") else ""
        _print(f"[完成] 速度测试: {result.get('total_tests', 0)} 项{cache_note}")
    else:
        _print(f"[失败] {result.get('error', '未知错误')}")