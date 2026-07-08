"""AstroHub v8.10 - 框选区域分析
白平衡修正 (Gray World) + 反差对焦 (Laplacian 爬山搜索)
"""
import cv2
import numpy as np


def analyze_whitebalance(bgr: np.ndarray) -> dict:
    """白平衡修正量计算 (排除死黑/死白，总值均衡)。

    原理:
    1. 排除死黑 (0,0,0) 和死白 (255,255,255) 像素
    2. 目标: R_sum * red_gain = G_sum = B_sum * blue_gain
       → red_gain = G_sum / R_sum * 100
       → blue_gain = G_sum / B_sum * 100

    Args:
        bgr: 框选区域的 BGR 图像 (numpy array)

    Returns:
        {"red_gain": int, "blue_gain": int, "r_mean": float, "g_mean": float, "b_mean": float}
    """
    # 排除死黑 (0,0,0) 和死白 (255,255,255)
    dead_black = np.all(bgr == 0, axis=2)
    dead_white = np.all(bgr == 255, axis=2)
    valid = ~(dead_black | dead_white)

    if np.count_nonzero(valid) < 10:
        # 有效像素太少，回退到全局均值
        b_mean, g_mean, r_mean = cv2.mean(bgr)[:3]
        if g_mean < 1:
            g_mean = 1
        red_gain = max(1, min(255, int(g_mean / max(r_mean, 1) * 100)))
        blue_gain = max(1, min(255, int(g_mean / max(b_mean, 1) * 100)))
        return {
            "red_gain": red_gain, "blue_gain": blue_gain,
            "r_mean": round(r_mean, 1), "g_mean": round(g_mean, 1), "b_mean": round(b_mean, 1),
        }

    # 有效像素的 R/G/B 总和
    b_ch = bgr[:, :, 0][valid]
    g_ch = bgr[:, :, 1][valid]
    r_ch = bgr[:, :, 2][valid]

    b_sum = float(b_ch.sum())
    g_sum = float(g_ch.sum())
    r_sum = float(r_ch.sum())

    # 目标: R*gr = G = B*gb → gr = G/R, gb = G/B
    if r_sum < 1:
        r_sum = 1
    if b_sum < 1:
        b_sum = 1

    red_gain = max(1, min(255, int(g_sum / r_sum * 100)))
    blue_gain = max(1, min(255, int(g_sum / b_sum * 100)))

    r_mean = float(r_ch.mean())
    g_mean = float(g_ch.mean())
    b_mean = float(b_ch.mean())

    return {
        "red_gain": red_gain,
        "blue_gain": blue_gain,
        "r_mean": round(r_mean, 1),
        "g_mean": round(g_mean, 1),
        "b_mean": round(b_mean, 1),
    }


def calc_contrast(bgr: np.ndarray) -> float:
    """计算图像反差值 (Laplacian 方差)。

    Args:
        bgr: BGR 图像

    Returns:
        反差值，越高越清晰
    """
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


class ContrastAF:
    """反差对焦爬山搜索器。

    用法:
        af = ContrastAF(client)
        # 循环:
        #   截图 → af.step(bgr) → 返回下一步指令
    """

    def __init__(self, step_size: int = 5, min_step: int = 1):
        self.step_size = step_size
        self.min_step = min_step
        self._prev_contrast = 0.0
        self._direction = 1      # 1=正向(远焦), -1=反向(近焦)
        self._peak_found = False
        self._reverse_count = 0   # 反向次数, 超过2次认为找到峰值

    def step(self, bgr: np.ndarray) -> dict:
        """输入当前帧，返回对焦移动指令。

        Returns:
            {"action": "focus_near"|"focus_far"|"stop", "contrast": float,
             "step": int, "message": str}
        """
        contrast = calc_contrast(bgr)

        if self._peak_found:
            return {"action": "stop", "contrast": round(contrast, 2),
                    "step": 0, "message": "对焦完成"}

        if self._prev_contrast == 0:
            # 首次: 正向试探
            self._prev_contrast = contrast
            return {"action": "focus_far", "contrast": round(contrast, 2),
                    "step": self.step_size, "message": "开始对焦搜索"}

        if contrast > self._prev_contrast:
            # 反差在上升, 继续同向
            self._prev_contrast = contrast
            return {"action": "focus_far" if self._direction > 0 else "focus_near",
                    "contrast": round(contrast, 2),
                    "step": self.step_size, "message": "反差上升, 继续"}
        else:
            # 反差下降, 反向
            self._reverse_count += 1
            self._direction *= -1
            self.step_size = max(self.min_step, self.step_size // 2)
            self._prev_contrast = contrast

            if self._reverse_count >= 3 or self.step_size <= self.min_step:
                self._peak_found = True
                return {"action": "stop", "contrast": round(contrast, 2),
                        "step": 0, "message": "对焦完成"}

            return {"action": "focus_far" if self._direction > 0 else "focus_near",
                    "contrast": round(contrast, 2),
                    "step": self.step_size, "message": "反差下降, 反向精调"}
