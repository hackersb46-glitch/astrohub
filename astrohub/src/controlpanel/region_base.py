"""AstroHub v8.72 - 画面分析基础工具 + 搜索器基类

提供：
- _valid_pixels() - 排除死黑(0,0,0)和死白(255,255,255)的像素
- _rgb_stats() - 计算RGB统计信息
- calc_contrast() - 计算反差值（Laplacian方差的float）
- calc_brightness() - 计算亮度值（标准亮度Y均值）
- get_exposure_time() - 获取慢快门倍率系数
- calc_stable_delay() - 计算稳定延时 = 基础延迟1.5s + 快门时间
- SearcherBase - 搜索器基类（中断管理、截图、循环控制）
"""

import cv2
import json
import asyncio
import numpy as np


# ============================================================================
# 工具函数
# ============================================================================

def _valid_pixels(bgr: np.ndarray):
    """排除死黑(0,0,0)和死白(255,255,255)，返回(B, G, R)三通道有效像素数组和计数。"""
    dead_black = np.all(bgr == 0, axis=2)
    dead_white = np.all(bgr == 255, axis=2)
    valid = ~(dead_black | dead_white)
    n = np.count_nonzero(valid)
    if n < 10:
        return None, None, None, None, 0
    return bgr[:, :, 0][valid], bgr[:, :, 1][valid], bgr[:, :, 2][valid], valid, n


def _rgb_stats(bgr: np.ndarray) -> dict:
    """计算框选区域有效像素的RGB统计。"""
    b_ch, g_ch, r_ch, _, n = _valid_pixels(bgr)
    b_sum, g_sum, r_sum = float(b_ch.sum()), float(g_ch.sum()), float(r_ch.sum())
    b_avg, g_avg, r_avg = float(b_ch.mean()), float(g_ch.mean()), float(g_ch.mean())
    return {
        "n": n,
        "b_sum": b_sum,
        "g_sum": g_sum,
        "r_sum": r_sum,
        "b_avg": b_avg,
        "g_avg": g_avg,
        "r_avg": r_avg
    }


def calc_contrast(bgr: np.ndarray) -> float:
    """计算框选区域的反差值（Laplacian方差）。"""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def calc_brightness(bgr: np.ndarray) -> float:
    """计算框选区域的亮度值（标准亮度Y均值）。
    Y = 0.299R + 0.587G + 0.114B，排除死黑死白。
    返回 0-255 的浮点数。
    """
    b_ch, g_ch, r_ch, _, n = _valid_pixels(bgr)
    if n < 10:
        return 0.0
    y_values = 0.299 * r_ch + 0.587 * g_ch + 0.114 * b_ch
    return float(np.mean(y_values))


def _parse_shutter_level(level_str: str) -> float:
    """解析快门值字符串为秒数。"""
    try:
        level_str = level_str.strip()
        if "/" in level_str:
            num, den = level_str.split("/")
            return float(num) / float(den)
        return float(level_str)
    except (ValueError, ZeroDivisionError):
        return 0.04


def get_exposure_time(client) -> float:
    """获取慢快门倍率系数 - v8.64:
    基础快门1/25=0.04s。检查慢快门DSS。
    返回慢快门倍率（无慢快门返回1）。
    """
    try:
        resp = client.get("/Image/channels/1/DSS")
        if resp.status_code == 200:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(resp.xml)
            for elem in root.iter():
                tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
                if tag in ("DSSLevel", "dssLevel"):
                    dss_level = (elem.text or "0").strip()
                    try:
                        level = int(dss_level)
                        if level > 1:
                            return float(level)
                    except ValueError:
                        pass
                    break
    except:
        pass
    return 1.0


def calc_stable_delay(client) -> float:
    """计算操作后的稳定延时 - v8.64:
    等待时间 = 固定1.5s + 快门时间
    快门时间 = 基础1/25 × 慢快门倍率
    """
    shutter_factor = get_exposure_time(client)
    base_shutter = 1.0 / 25.0
    shutter_time = base_shutter * shutter_factor
    return 1.5 + shutter_time


# ============================================================================
# 搜索器基类 (v8.72)
# ============================================================================

class SearcherBase:
    """搜索器基类 - 提取三模块共用的中断管理、截图、清理。"""

    search_type = "base"

    def __init__(self, mgr, device_ip, client, x, y, w, h,
                 capture_func, cleanup_func, mac_clean=""):
        self.mgr = mgr
        self.device_ip = device_ip
        self.client = client
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self._capture_func = capture_func
        self._cleanup_func = cleanup_func
        self._mac_clean = mac_clean
        self._interrupted = False
        self._stable_delay = 1.5

    def _interrupt(self):
        """中断搜索"""
        self._interrupted = True

    def _capture(self):
        """获取选区截图"""
        bgr, crop_path, info = self._capture_func(
            self.client, self.mgr, self.device_ip, self.search_type.upper(),
            self.x, self.y, self.w, self.h,
            skip_delay=True
        )
        return bgr, info

    async def _setup_stable_delay(self):
        """计算稳定延时（只计算一次）"""
        self._stable_delay = await asyncio.to_thread(calc_stable_delay, self.client)


# ============================================================================
# 基线管理 (v8.73)
# ============================================================================

from pathlib import Path
from datetime import datetime

_BASELINE_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "search_baseline.json"

# 阈值定义（百分比）
BASELINE_THRESHOLDS = {
    'focus': 15.0,      # 反差差异 < 15%
    'whitebalance': 10.0,  # delta 差异 < 10%
    'brightness': 5.0,   # 亮度差异 < 5%
}


def read_search_baseline(mac_clean: str, mode: str) -> dict | None:
    """读取设备+模式的基线数据。
    
    Args:
        mac_clean: 设备MAC地址（清洗后，12位小写）
        mode: 'focus' | 'whitebalance' | 'brightness'
    
    Returns:
        dict: 基线数据，无则返回 None
    """
    if not _BASELINE_FILE.exists():
        return None
    try:
        with open(_BASELINE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get(mac_clean, {}).get(mode)
    except Exception:
        return None


def write_search_baseline(mac_clean: str, mode: str, baseline: dict):
    """写入设备+模式的基线数据。
    
    Args:
        mac_clean: 设备MAC地址（清洗后，12位小写）
        mode: 'focus' | 'whitebalance' | 'brightness'
        baseline: 基线数据 dict
    """
    data = {}
    if _BASELINE_FILE.exists():
        try:
            with open(_BASELINE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = {}
    
    if mac_clean not in data:
        data[mac_clean] = {}
    
    baseline['timestamp'] = datetime.now().isoformat()
    data[mac_clean][mode] = baseline
    
    _BASELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_BASELINE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def calc_wb_delta(bgr) -> float:
    """计算白平衡 delta 值。
    
    delta = |R/G - 1| + |B/G - 1|
    """
    stats = _rgb_stats(bgr)
    if stats['n'] < 10:
        return 999.0
    r_sum, g_sum, b_sum = stats['r_sum'], stats['g_sum'], stats['b_sum']
    if g_sum < 1:
        g_sum = 1
    return abs(r_sum / g_sum - 1.0) + abs(b_sum / g_sum - 1.0)


def check_baseline(bgr, mode: str, baseline: dict) -> tuple[bool, float, str]:
    """检查当前值与基线的差异是否在阈值内。
    
    Args:
        bgr: 当前截图
        mode: 'focus' | 'whitebalance' | 'brightness'
        baseline: 基线数据
    
    Returns:
        (should_search, diff_percent, message)
        - should_search: 是否需要执行搜索
        - diff_percent: 差异百分比
        - message: 描述信息
    """
    threshold = BASELINE_THRESHOLDS.get(mode, 10.0)
    
    if mode == 'focus':
        current = calc_contrast(bgr)
        base_value = baseline.get('contrast', 0)
        if base_value <= 0:
            return True, 100.0, "基线反差为0，执行搜索"
        diff = abs(current - base_value) / base_value * 100
        label = f"反差 {current:.1f} vs {base_value:.1f}"
    
    elif mode == 'whitebalance':
        current = calc_wb_delta(bgr)
        base_value = baseline.get('delta', 0)
        if base_value <= 0:
            return True, 100.0, "基线delta为0，执行搜索"
        diff = abs(current - base_value) / base_value * 100
        label = f"delta {current:.4f} vs {base_value:.4f}"
    
    elif mode == 'brightness':
        current = calc_brightness(bgr) * 100.0 / 255.0
        base_value = baseline.get('brightness', 0)
        if base_value <= 0:
            return True, 100.0, "基线亮度为0，执行搜索"
        diff = abs(current - base_value) / base_value * 100
        label = f"亮度 {current:.1f} vs {base_value:.1f}"
    
    else:
        return True, 0.0, f"未知模式: {mode}"
    
    if diff < threshold:
        return False, diff, f"差异{diff:.1f}% < 阈值{threshold}%（{label}），无需调整"
    else:
        return True, diff, f"差异{diff:.1f}% >= 阈值{threshold}%（{label}），执行搜索"
