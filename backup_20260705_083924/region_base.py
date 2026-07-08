"""AstroHub v8.36 - 画面分析基础工具

提供图像处理的基础函数：
- _valid_pixels() - 排除死黑(0,0,0)和死白(255,255,255)的像素
- _rgb_stats() - 计算RGB统计信息
- calc_contrast() - 计算反差值（Laplacian方差的float）
"""

import cv2
import numpy as np


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
