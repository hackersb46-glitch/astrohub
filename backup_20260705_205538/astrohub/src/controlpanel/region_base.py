"""AstroHub v8.44 - 画面分析基础工具

提供：
- _valid_pixels() - 排除死黑(0,0,0)和死白(255,255,255)的像素
- _rgb_stats() - 计算RGB统计信息
- calc_contrast() - 计算反差值（Laplacian方差的float）
- get_exposure_time() - 从设备读取当前曝光时间（秒）
- calc_stable_delay() - 计算稳定延时 = 曝光时间*2 + 基础延迟0.5s
"""

import cv2
import numpy as np

# v8.44: 基础稳定延时（秒）
BASE_STABLE_DELAY = 0.5


def _valid_pixels(bgr: np.ndarray):
    """排除死黑(0,0,0)和死白(255,255,255)，返回(B, G, R)三通道有效像素数组和计数。

    Args:
        bgr: BGR格式的图像数组

    Returns:
        tuple: (b_channel, g_channel, r_channel, valid_mask, n)
            如果n < 10，返回(None, None, None, None, 0)
    """
    dead_black = np.all(bgr == 0, axis=2)
    dead_white = np.all(bgr == 255, axis=2)
    valid = ~(dead_black | dead_white)
    n = np.count_nonzero(valid)
    if n < 10:
        return None, None, None, None, 0
    return bgr[:, :, 0][valid], bgr[:, :, 1][valid], bgr[:, :, 2][valid], valid, n


def _rgb_stats(bgr: np.ndarray) -> dict:
    """计算框选区域有效像素的RGB统计。

    Args:
        bgr: BGR格式的图像数组

    Returns:
        dict: 包含 n, b_sum, g_sum, r_sum, b_avg, g_avg, r_avg
    """
    b_ch, g_ch, r_ch, _, n = _valid_pixels(bgr)
    b_sum, g_sum, r_sum = float(b_ch.sum()), float(g_ch.sum()), float(r_ch.sum())
    b_avg, g_avg, r_avg = float(b_ch.mean()), float(g_ch.mean()), float(r_ch.mean())
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
    """计算框选区域的反差值。

    使用Laplacian方差作为反差度量。

    Args:
        bgr: BGR格式的图像数组

    Returns:
        float: 反差值（Laplacian方差）
    """
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _parse_shutter_level(level_str: str) -> float:
    """解析快门值字符串为秒数。

    支持格式：
        "1/60" → 1/60 ≈ 0.01667s
        "1/25" → 1/25 = 0.04s
        "1/30000" → 1/30000 ≈ 0.0000333s

    Returns:
        float: 曝光时间（秒），解析失败返回 0.04（默认1/25）
    """
    try:
        level_str = level_str.strip()
        if "/" in level_str:
            num, den = level_str.split("/")
            return float(num) / float(den)
        return float(level_str)
    except (ValueError, ZeroDivisionError):
        return 0.04  # 默认 1/25s


def get_exposure_time(client) -> float:
    """从设备读取当前实际曝光时间（秒）。

    读取顺序：
    1. GET /Image/channels/1/Shutter → ShutterLevel（机械快门值）
    2. 如果 minShutterLevelLimit 存在且不等于 maxShutterLevelLimit，
       说明慢快门开启，实际曝光 = 快门值 × 慢快门倍率

    Args:
        client: ISAPIClient 实例

    Returns:
        float: 实际曝光时间（秒），失败返回 0.04（1/25s）
    """
    default = 0.04  # 1/25s
    try:
        resp = client.get("/Image/channels/1/Shutter")
        if resp.status_code != 200:
            return default

        import xml.etree.ElementTree as ET
        root = ET.fromstring(resp.xml)

        shutter_level = None
        min_limit = None
        max_limit = None

        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag in ("ShutterLevel", "shutterLevel"):
                shutter_level = (elem.text or "").strip()
            elif tag in ("minShutterLevelLimit", "MinShutterLevelLimit"):
                min_limit = (elem.text or "").strip()
            elif tag in ("maxShutterLevelLimit", "MaxShutterLevelLimit"):
                max_limit = (elem.text or "").strip()

        if not shutter_level:
            return default

        base_exposure = _parse_shutter_level(shutter_level)

        # 检查慢快门：如果 minLimit 和 maxLimit 不同，说明慢快门生效
        # 慢快门倍率 = maxLimit对应时间 / minLimit对应时间
        if min_limit and max_limit and min_limit != max_limit:
            min_time = _parse_shutter_level(min_limit)
            max_time = _parse_shutter_level(max_limit)
            if min_time > 0 and max_time > min_time:
                # 慢快门开启：实际曝光时间 = base × (max_time / base_time)
                # maxShutterLevelLimit 是慢快门后的最慢快门值
                slow_ratio = max_time / base_exposure if base_exposure > 0 else 1.0
                return base_exposure * slow_ratio

        return base_exposure
    except Exception:
        return default


def calc_stable_delay(client) -> float:
    """计算操作后的稳定延时。

    延时 = 曝光时间 × 2 + 基础延迟(0.5s)

    如果慢快门开启，曝光时间为慢快门后的实际曝光时间。

    Args:
        client: ISAPIClient 实例

    Returns:
        float: 延时秒数
    """
    exposure = get_exposure_time(client)
    return exposure * 2 + BASE_STABLE_DELAY
