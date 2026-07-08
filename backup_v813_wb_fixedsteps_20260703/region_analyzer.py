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
    """白平衡迭代搜索器 - R/B 独立调整。

    每步先尝试双通道(±step), 再尝试单独R, 再单独B。
    选 delta 最小的方案。粗5→中2→精1 阶段递进。
    全程追踪 best_gains + best_delta，结束时通知回滚。

    用法:
        wb = IterativeWB()
        for bgr in frames:
            cmd = wb.step(bgr)
            if cmd["action"] == "stop":
                # 如有 cmd["rollback"]=True, 应用 best_gains
            # 应用 cmd["red_gain"], cmd["blue_gain"] 到设备
    """

    def __init__(self):
        self._stage = 0          # 0粗5, 1中2, 2精1
        self._stage_steps = [5, 2, 1]
        self._current_red = 100
        self._current_blue = 100
        self._no_improve = 0
        self._fine_steps = 0       # fine阶段步数
        # 最佳记录
        self._best_red = 100
        self._best_blue = 100
        self._best_delta = 999.0
        self._best_step = 0
        self._step_count = 0

    def _eval(self, r_sum, g_sum, b_sum, red, blue) -> float:
        """估算新增益下的 delta。先反除当前增益恢复原始信号，再乘新增益。"""
        if g_sum < 1: g_sum = 1
        ar = max(1, r_sum) * red / max(1, self._current_red)
        ab = max(1, b_sum) * blue / max(1, self._current_blue)
        return abs(ar / g_sum - 1.0) + abs(ab / g_sum - 1.0)

    def step(self, bgr: np.ndarray) -> dict:
        stats = _rgb_stats(bgr)
        n = stats["n"]
        r_sum, g_sum, b_sum = stats["r_sum"], stats["g_sum"], stats["b_sum"]

        self._step_count += 1
        step = self._stage_steps[self._stage]

        # 候选增益: [双通道, 仅R, 仅B]
        candidates = []
        # 双通道
        cr = self._current_red + max(-step, min(step, int(g_sum / max(1, r_sum) * self._current_red) - self._current_red))
        cb = self._current_blue + max(-step, min(step, int(g_sum / max(1, b_sum) * self._current_blue) - self._current_blue))
        cr = max(1, min(255, cr))
        cb = max(1, min(255, cb))
        candidates.append((cr, cb, "both"))
        # 仅R (B不变)
        candidates.append((cr, self._current_blue, "red"))
        # 仅B (R不变)
        candidates.append((self._current_red, cb, "blue"))

        # 评估所有候选
        best_cand = None
        best_d = 999.0
        for cr, cb, label in candidates:
            d = self._eval(r_sum, g_sum, b_sum, cr, cb)
            if d < best_d:
                best_d = d
                best_cand = (cr, cb, label)

        new_red, new_blue, direction = best_cand
        new_red = int(new_red)
        new_blue = int(new_blue)

        # 实测 delta
        actual = abs(r_sum / max(1, g_sum) - 1.0) + abs(b_sum / max(1, g_sum) - 1.0)

        # 追踪全局最佳
        if actual < self._best_delta:
            self._best_delta = actual
            self._best_red = new_red
            self._best_blue = new_blue
            self._best_step = self._step_count

        # 改善检测：对比全局最佳（抗帧噪声）
        if actual >= self._best_delta * 0.95:
            self._no_improve += 1
        else:
            self._no_improve = 0

        # 阶段升级
        stage_name = "coarse" if self._stage == 0 else "medium" if self._stage == 1 else "fine"
        if self._no_improve >= 2 and self._stage < 2:
            self._stage += 1
            self._no_improve = 0
            self._fine_steps = 0
            new_stage = "medium" if self._stage == 1 else "fine"
            self._current_red = new_red
            self._current_blue = new_blue
            return {
                "action": "continue",
                "stage": new_stage,
                "step_size": self._stage_steps[self._stage],
                "red_gain": new_red, "blue_gain": new_blue,
                "r_avg": round(stats["r_avg"], 1), "g_avg": round(stats["g_avg"], 1), "b_avg": round(stats["b_avg"], 1),
                "delta": round(actual, 4), "best_delta": round(self._best_delta, 4), "pixels": n,
                "message": f"进入{'中等' if self._stage == 1 else '精细'}调校 (±{self._stage_steps[self._stage]}) {direction}"
            }

        # fine 阶段计数
        if self._stage == 2:
            self._fine_steps += 1

        # 最终停止: fine 阶段收敛检查
        # fine_steps >= 3 仅在 delta 已较小时触发 (否则继续迭代)
        if self._stage == 2:
            converged = self._best_delta < 0.15
            if self._no_improve >= 2 or (converged and self._fine_steps >= 3) or self._best_delta < 0.03:
                rollback = (self._best_red != new_red or self._best_blue != new_blue)
                return {
                    "action": "stop",
                    "stage": "done",
                    "step_size": 0,
                    "red_gain": self._best_red, "blue_gain": self._best_blue,
                    "r_avg": round(stats["r_avg"], 1), "g_avg": round(stats["g_avg"], 1), "b_avg": round(stats["b_avg"], 1),
                    "delta": round(self._best_delta, 4), "pixels": n,
                    "message": f"白平衡完成 {'(回滚至最佳)' if rollback else '(已达最佳)'} 第{self._best_step}步"
                }

        self._current_red = new_red
        self._current_blue = new_blue
        return {
            "action": "continue",
            "stage": stage_name,
            "step_size": step,
            "red_gain": new_red, "blue_gain": new_blue,
            "r_avg": round(stats["r_avg"], 1), "g_avg": round(stats["g_avg"], 1), "b_avg": round(stats["b_avg"], 1),
            "delta": round(actual, 4), "best_delta": round(self._best_delta, 4), "pixels": n,
            "message": f"{'粗' if self._stage == 0 else '中' if self._stage == 1 else '精'}调 {direction} (±{step})"
        }


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
