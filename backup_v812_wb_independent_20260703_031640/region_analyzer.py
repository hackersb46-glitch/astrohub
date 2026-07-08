"""AstroHub v8.11 - 框选区域分析
白平衡迭代搜索 + 反差对焦爬山搜索
"""
import cv2
import numpy as np


# ── 公共工具 ──────────────────────────────────────────────


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
    b_avg, g_avg, r_avg = float(b_ch.mean()), float(g_ch.mean()), float(r_ch.mean())
    return {"n": n, "b_sum": b_sum, "g_sum": g_sum, "r_sum": r_sum,
            "b_avg": b_avg, "g_avg": g_avg, "r_avg": r_avg}


def calc_contrast(bgr: np.ndarray) -> float:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


# ── 白平衡迭代搜索器 ─────────────────────────────────────

class IterativeWB:
    """白平衡迭代搜索器。

    以 ±5 → ±2 → ±1 步长迭代，直到最小步长无显著改善。

    用法:
        wb = IterativeWB()
        for bgr in frames:
            cmd = wb.step(bgr)
            if cmd["action"] == "stop": break
            # 应用 cmd["red_gain"], cmd["blue_gain"] 到设备
    """

    def __init__(self):
        self._stage = 0          # 0=粗(5), 1=中(2), 2=细(1)
        self._stage_steps = [5, 2, 1]
        self._current_red = 100
        self._current_blue = 100
        self._prev_rgb_ratio = None   # (r_ratio, b_ratio)
        self._no_improve = 0

    def step(self, bgr: np.ndarray) -> dict:
        stats = _rgb_stats(bgr)
        n, b_sum, g_sum, r_sum = stats["n"], stats["b_sum"], stats["g_sum"], stats["r_sum"]

        if g_sum < 1: g_sum = 1
        if r_sum < 1: r_sum = 1
        if b_sum < 1: b_sum = 1

        target_red = int(g_sum / r_sum * self._current_red)
        target_blue = int(g_sum / b_sum * self._current_blue)
        target_red = max(1, min(255, target_red))
        target_blue = max(1, min(255, target_blue))

        step_size = self._stage_steps[self._stage]
        new_red = self._current_red + max(-step_size, min(step_size, target_red - self._current_red))
        new_blue = self._current_blue + max(-step_size, min(step_size, target_blue - self._current_blue))

        # 检查是否收敛
        r_ratio = r_sum / g_sum
        b_ratio = b_sum / g_sum
        rgb_ratio = (r_ratio, b_ratio)

        delta = abs(r_ratio - 1.0) + abs(b_ratio - 1.0)

        if self._prev_rgb_ratio:
            prev_delta = abs(self._prev_rgb_ratio[0] - 1.0) + abs(self._prev_rgb_ratio[1] - 1.0)
            if delta >= prev_delta * 0.95:  # 改善<5%
                self._no_improve += 1
            else:
                self._no_improve = 0

        self._prev_rgb_ratio = rgb_ratio

        # 检查是否需要进入下一阶段
        if self._no_improve >= 2 and self._stage < 2:
            self._stage += 1
            self._no_improve = 0
            stage_name = "medium" if self._stage == 1 else "fine"
            return {
                "action": "continue",
                "stage": stage_name,
                "step_size": self._stage_steps[self._stage],
                "red_gain": new_red, "blue_gain": new_blue,
                "r_sum": round(r_sum, 1), "g_sum": round(g_sum, 1), "b_sum": round(b_sum, 1),
                "r_avg": round(stats["r_avg"], 1), "g_avg": round(stats["g_avg"], 1), "b_avg": round(stats["b_avg"], 1),
                "delta": round(delta, 4), "pixels": n,
                "message": f"进入{'中等' if self._stage == 1 else '精细'}调校 (±{self._stage_steps[self._stage]})"
            }

        # 检查最终收敛 (stage=2 即 step=1 且无改善)
        if self._stage == 2 and self._no_improve >= 2:
            old_r = self._current_red
            old_b = self._current_blue
            self._current_red = new_red
            self._current_blue = new_blue
            return {
                "action": "stop",
                "stage": "done",
                "step_size": 0,
                "red_gain": old_r, "blue_gain": old_b,
                "r_sum": round(r_sum, 1), "g_sum": round(g_sum, 1), "b_sum": round(b_sum, 1),
                "r_avg": round(stats["r_avg"], 1), "g_avg": round(stats["g_avg"], 1), "b_avg": round(stats["b_avg"], 1),
                "delta": round(delta, 4), "pixels": n,
                "message": "白平衡已完成"
            }

        stage_names = ["coarse", "medium", "fine"]
        result = {
            "action": "continue",
            "stage": stage_names[self._stage],
            "step_size": step_size,
            "red_gain": new_red, "blue_gain": new_blue,
            "r_sum": round(r_sum, 1), "g_sum": round(g_sum, 1), "b_sum": round(b_sum, 1),
            "r_avg": round(stats["r_avg"], 1), "g_avg": round(stats["g_avg"], 1), "b_avg": round(stats["b_avg"], 1),
            "delta": round(delta, 4), "pixels": n,
            "message": f"{'粗调' if self._stage == 0 else '中调' if self._stage == 1 else '精调'} (±{step_size})"
        }

        self._current_red = new_red
        self._current_blue = new_blue
        return result


# ── 反差对焦搜索器 ───────────────────────────────────────

class ContrastAF:
    """反差对焦爬山搜索器（时间基）。

    用法:
        af = ContrastAF()
        for bgr in frames:
            cmd = af.step(bgr)
            if cmd["action"] == "stop": break
            # 用 cmd["duration"] (秒) 驱动设备对焦
    """

    def __init__(self):
        self._prev_contrast = 0.0
        self._direction = 1      # 1=far, -1=near
        self._peak_found = False
        self._reverse_count = 0
        # 时间阶梯: 0.5s→0.2s→0.1s
        self._durations = [0.5, 0.2, 0.1]
        self._duration_idx = 0

    def step(self, bgr: np.ndarray) -> dict:
        contrast = calc_contrast(bgr)

        if self._peak_found:
            return {"action": "stop", "contrast": round(contrast, 2),
                    "duration": 0, "message": "对焦完成"}

        if self._prev_contrast == 0:
            self._prev_contrast = contrast
            return {"action": "focus_far", "contrast": round(contrast, 2),
                    "duration": self._durations[self._duration_idx], "message": "开始对焦搜索"}

        if contrast > self._prev_contrast:
            self._prev_contrast = contrast
            return {"action": "focus_far" if self._direction > 0 else "focus_near",
                    "contrast": round(contrast, 2),
                    "duration": self._durations[self._duration_idx], "message": "反差上升, 继续"}
        else:
            self._reverse_count += 1
            self._direction *= -1
            self._prev_contrast = contrast

            # 反向时降低时间档
            if self._duration_idx < len(self._durations) - 1:
                self._duration_idx += 1

            if self._reverse_count >= 3 or self._duration_idx >= len(self._durations):
                self._peak_found = True
                return {"action": "stop", "contrast": round(contrast, 2),
                        "duration": 0, "message": "对焦完成"}

            return {"action": "focus_far" if self._direction > 0 else "focus_near",
                    "contrast": round(contrast, 2),
                    "duration": self._durations[self._duration_idx],
                    "message": f"反差下降, 反向精调 ({self._durations[self._duration_idx]}s)"}
