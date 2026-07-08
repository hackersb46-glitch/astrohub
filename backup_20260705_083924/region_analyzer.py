"""AstroHub v8.36 - 框选区域分析
白平衡迭代搜索 + 反差对焦（状态机版）
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

    粗调(±5, 最少6步) → 中调(±2, 最少3步) → 精调(±1, 收敛检测)
    每步评估 [双通道, 仅R, 仅B] 三个候选，选 delta 最小。
    全程追踪 best_gains + best_delta，结束时回滚到最佳。
    """

    def __init__(self, current_red=100, current_blue=100):
        self._stage = 0
        self._stage_steps = [5, 2, 1]
        self._stage_min = [6, 3, 0]
        self._tolerances = [0.70, 0.80, 0.95]
        self._current_red = current_red
        self._current_blue = current_blue
        self._no_improve = 0
        self._stage_step_count = 0
        self._fine_steps = 0
        self._fine_sub = 0
        self._best_red = current_red
        self._best_blue = current_blue
        self._best_delta = 999.0
        self._best_step = 0
        self._step_count = 0

    def _eval(self, r_sum, g_sum, b_sum, red, blue) -> float:
        if g_sum < 1: g_sum = 1
        ar = max(1, r_sum) * red / max(1, self._current_red)
        ab = max(1, b_sum) * blue / max(1, self._current_blue)
        return abs(ar / g_sum - 1.0) + abs(ab / g_sum - 1.0)

    def step(self, bgr: np.ndarray) -> dict:
        stats = _rgb_stats(bgr)
        n = stats["n"]
        r_sum, g_sum, b_sum = stats["r_sum"], stats["g_sum"], stats["b_sum"]

        self._step_count += 1
        self._stage_step_count += 1
        step = self._stage_steps[self._stage]

        cr = self._current_red + max(-step, min(step, int(g_sum / max(1, r_sum) * self._current_red) - self._current_red))
        cb = self._current_blue + max(-step, min(step, int(g_sum / max(1, b_sum) * self._current_blue) - self._current_blue))
        cr = max(1, min(255, cr))
        cb = max(1, min(255, cb))

        if self._stage == 2:
            if self._fine_sub == 0:
                candidates = [(cr, cb, "both"), (cr, self._current_blue, "red"), (self._current_red, cb, "blue")]
            else:
                candidates = [(cr, self._current_blue, "red"), (self._current_red, cb, "blue")]
        else:
            candidates = [(cr, cb, "both"), (cr, self._current_blue, "red"), (self._current_red, cb, "blue")]

        best_cand = None
        best_d = 999.0
        for r, b, label in candidates:
            d = self._eval(r_sum, g_sum, b_sum, r, b)
            if d < best_d:
                best_d = d
                best_cand = (r, b, label)

        new_red, new_blue, direction = best_cand
        new_red = int(new_red)
        new_blue = int(new_blue)

        actual = abs(r_sum / max(1, g_sum) - 1.0) + abs(b_sum / max(1, g_sum) - 1.0)

        prev_best = self._best_delta
        if actual < self._best_delta:
            self._best_delta = actual
            self._best_red = self._current_red
            self._best_blue = self._current_blue
            self._best_step = self._step_count

        tolerance = self._tolerances[self._stage]
        if actual >= prev_best * tolerance:
            self._no_improve += 1
        else:
            self._no_improve = 0

        stage_name = ["coarse", "medium", "fine"][self._stage]
        min_steps = self._stage_min[self._stage]

        if self._stage < 2 and self._stage_step_count >= min_steps and self._no_improve >= 2:
            self._stage += 1
            self._stage_step_count = 0
            self._no_improve = 0
            new_stage = ["medium", "fine"][self._stage - 1]
            return {
                "action": "continue",
                "stage": new_stage,
                "step_size": self._stage_steps[self._stage],
                "red_gain": self._current_red, "blue_gain": self._current_blue,
                "r_avg": round(stats["r_avg"], 1), "g_avg": round(stats["g_avg"], 1), "b_avg": round(stats["b_avg"], 1),
                "delta": round(actual, 4), "best_delta": round(self._best_delta, 4), "pixels": n,
                "message": f"进入{'中等' if self._stage == 1 else '精细'}调校 (step=±{self._stage_steps[self._stage]})"
            }

        if self._stage == 2:
            self._fine_steps += 1
            if self._fine_sub == 0:
                if self._no_improve >= 2 or self._fine_steps >= 5:
                    self._fine_sub = 1
                    self._fine_steps = 0
                    self._no_improve = 0
                    return {
                        "action": "continue",
                        "stage": "fine",
                        "step_size": 1,
                        "red_gain": self._current_red, "blue_gain": self._current_blue,
                        "r_avg": round(stats["r_avg"], 1), "g_avg": round(stats["g_avg"], 1), "b_avg": round(stats["b_avg"], 1),
                        "delta": round(actual, 4), "best_delta": round(self._best_delta, 4), "pixels": n,
                        "message": "精调: 进入独立调整"
                    }
            else:
                if self._no_improve >= 3 or self._fine_steps >= 5:
                    rollback = (self._best_red != self._current_red or self._best_blue != self._current_blue)
                    self._current_red = self._best_red
                    self._current_blue = self._best_blue
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


# ── 反差对焦搜索器（v8.36 状态机版）──────────────────────────────────────

class ContrastAF:
    """反差对焦 - v8.36 状态机版
    
    状态：
    - COARSE: 粗调采样（0.2s移动）
    - PRECISE: 精确逼近（0.05s移动）
    - DONE: 完成
    - FAILED: 失败
    
    粗调阶段：
    - 进入精确对焦：4点连续下降 OR (best>100 且 下降后稳定)
    - 对焦失败：R²<80% 且 best<100
    - 反向：连续10点R²<10% 且 best<100
    - 最多3次反向（正-反-正），超过报错
    
    精确逼近：
    - 目标：拟合曲线的best位置
    - 移动直到出现下降的第一点，返回1点
    """

    COARSE = "coarse"
    PRECISE_RETURN = "precise_return"  # 回退到best附近（0.2s）
    PRECISE_APPROACH = "precise_approach"  # 缓慢逼近拟合峰值（0.05s）
    DONE = "done"
    FAILED = "failed"

    def __init__(self):
        self._state = self.COARSE
        self._points = []  # [(pos, contrast)]
        self._direction = 1  # 1=far, -1=near
        self._best_contrast = 0.0
        self._best_pos = 0
        self._reverse_count = 0
        self._max_reverse = 3
        self._fitted_peak = None  # (pos, val, r_squared)
        self._prev_contrast = 0.0
        self._approach_step = 0
        self._return_steps_needed = 0  # 回退步数
        self._return_steps_done = 0

    def _fit_gaussian(self):
        """高斯拟合: ln(y) = Ax² + Bx + C
        要求：best左侧≥4点，右侧≥3点（4点下降保证右侧至少3点）
        忽略基本不变的点（连续点绝对值误差<10%）
        返回：(peak_x, peak_y, r_squared) 或 None"""
        if len(self._points) < 8:
            return None
        best_idx = max(range(len(self._points)), key=lambda i: self._points[i][1])
        left = best_idx
        right = len(self._points) - best_idx - 1
        if left < 4 or right < 3:
            return None
        
        # 过滤无效点：去除连续基本不变的点（绝对值误差<10%）
        # 保留best左侧和右侧的有效变化点
        left_pts = self._points[:best_idx+1]  # 包含best
        right_pts = self._points[best_idx:]    # 包含best
        
        # 左侧：从best往前过滤
        filtered_left = [left_pts[-1]]  # best点
        for i in range(len(left_pts)-2, -1, -1):
            if left_pts[i][1] < 0.1:
                continue
            ratio = abs(left_pts[i+1][1] - left_pts[i][1]) / max(left_pts[i+1][1], 0.1)
            if ratio < 0.10:  # 基本不变，跳过
                continue
            filtered_left.append(left_pts[i])
        filtered_left.reverse()
        
        # 右侧：从best往后过滤
        filtered_right = [right_pts[0]]  # best点
        for i in range(1, len(right_pts)):
            if right_pts[i][1] < 0.1:
                continue
            ratio = abs(right_pts[i][1] - right_pts[i-1][1]) / max(right_pts[i-1][1], 0.1)
            if ratio < 0.10:  # 基本不变，跳过
                continue
            filtered_right.append(right_pts[i])
        
        # 合并去重（best点只保留一次）
        filtered = filtered_left[:-1] + filtered_right
        
        if len(filtered) < 8:
            return None
        
        # 重新找best在filtered中的位置
        best_fidx = max(range(len(filtered)), key=lambda i: filtered[i][1])
        f_left = best_fidx
        f_right = len(filtered) - best_fidx - 1
        if f_left < 4 or f_right < 3:
            return None
        
        xs = np.array([p[0] for p in filtered])
        ys = np.array([p[1] for p in filtered])
        if ys.max() < ys.min() * 1.3:
            return None
        ys_safe = np.maximum(ys, 0.1)
        ln_y = np.log(ys_safe)
        try:
            A, B, C = np.polyfit(xs, ln_y, 2)
            if A >= 0:
                return None
            ln_y_pred = A * xs**2 + B * xs + C
            ss_res = np.sum((ln_y - ln_y_pred)**2)
            ss_tot = np.sum((ln_y - np.mean(ln_y))**2)
            r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
            peak_x = -B / (2 * A)
            if peak_x < xs.min() or peak_x > xs.max():
                return None
            peak_y = float(np.exp(C - B**2 / (4 * A)))
            return (float(peak_x), peak_y, float(r2))
        except Exception:
            return None

    def _check_4pt_decline(self):
        """检查最近4点是否连续下降"""
        if len(self._points) < 5:
            return False
        recent = self._points[-4:]
        return all(recent[i+1][1] < recent[i][1] for i in range(len(recent)-1))

    def _check_flat_region(self):
        """平坦区域：连续10点波动<10% 且 best<100"""
        if len(self._points) < 10:
            return False
        if self._best_contrast >= 100:
            return False
        recent = [p[1] for p in self._points[-10:]]
        max_v, min_v = max(recent), min(recent)
        if max_v <= 0:
            return False
        return (max_v - min_v) / max_v < 0.10

    def _check_stable_after_decline(self):
        """边缘情况：过best后下降，然后稳定（最近10点波动<10%）
        条件：best>100 且 best之后≥5点 且 最近10点波动<10%"""
        if len(self._points) < 10:
            return False
        if self._best_contrast <= 100:
            return False
        if self._best_pos >= len(self._points) - 1:
            return False
        after_best = len(self._points) - self._best_pos - 1
        if after_best < 5:
            return False
        recent = [p[1] for p in self._points[-10:]]
        max_v, min_v = max(recent), min(recent)
        if max_v <= 0:
            return False
        return (max_v - min_v) / max_v < 0.10

    def _do_reverse(self):
        """执行反向：清空数据，翻转方向"""
        self._reverse_count += 1
        self._direction *= -1
        self._points = []
        self._best_contrast = 0.0
        self._best_pos = 0
        self._fitted_peak = None

    def _check_past_peak(self):
        """过峰值检测：best>100 且 best之后≥10点 且 当前反差<best的50%
        这意味着我们已经明显过峰值，应该停止采样进入精确对焦"""
        if len(self._points) < 15:
            return False
        if self._best_contrast <= 100:
            return False
        if self._best_pos >= len(self._points) - 1:
            return False
        after_best = len(self._points) - self._best_pos - 1
        if after_best < 10:
            return False
        # 检查当前反差是否明显低于best
        current = self._points[-1][1]
        return current < self._best_contrast * 0.5

    def _step_coarse(self, contrast):
        """粗调阶段（0.2s移动）
        
        判断顺序：
        1. 4点连续下降 → 尝试拟合
           a. R²≥0.8 → 进入精确对焦
           b. best>100 且 (下降后稳定 OR 过峰值) → 进入精确对焦（边缘情况）
           c. R²<0.8 且 best<100 且 平坦 → 反向
           d. 否则继续采样
        2. 平坦区域（10点波动<10%, best<100）→ 反向
        3. 过峰值检测（best>100 且 明显过峰值）→ 进入精确对焦
        4. R²<0.8 且 best<100 → 对焦失败
        """
        pos = len(self._points)
        self._points.append((pos, contrast))
        if contrast > self._best_contrast:
            self._best_contrast = contrast
            self._best_pos = pos

        action = "focus_far" if self._direction > 0 else "focus_near"
        dir_name = '远' if self._direction > 0 else '近'

        # 首步
        if pos == 0:
            return {"action": action, "contrast": round(contrast, 2),
                    "duration": 0.2, "stage": "coarse",
                    "message": f"开始对焦搜索(方向={dir_name})"}

        # ── 检查1: 4点连续下降 ──
        if self._check_4pt_decline():
            peak = self._fit_gaussian()
            r2 = peak[2] if peak else None

            # 1a. R²≥0.8 → 精确对焦
            if peak and r2 >= 0.8:
                self._fitted_peak = peak
                self._state = self.PRECISE_RETURN
                self._return_steps_needed = len(self._points) - self._best_pos - 1
                self._return_steps_done = 0
                return {"action": action, "contrast": round(contrast, 2),
                        "duration": 0.2, "stage": "coarse",
                        "message": f"4点下降+R²={r2:.3f},回退到best(需{self._return_steps_needed}步)"}

            # 1b. 4点下降但拟合失败，且best>100 → 边缘情况，直接进入精确对焦
            #    （避免继续采样导致偏离峰值太远）
            elif self._best_contrast > 100:
                self._fitted_peak = peak
                self._state = self.PRECISE_RETURN
                self._return_steps_needed = len(self._points) - self._best_pos - 1
                self._return_steps_done = 0
                r2_msg = f"R²={r2:.3f}" if r2 is not None else "无拟合"
                return {"action": action, "contrast": round(contrast, 2),
                        "duration": 0.2, "stage": "coarse",
                        "message": f"边缘情况({r2_msg},best={self._best_contrast:.1f}),回退到best(需{self._return_steps_needed}步)"}

            # 1c. best>100 且 下降后稳定 → 精确对焦（边缘情况）
            if self._best_contrast > 100 and self._check_stable_after_decline():
                peak = self._fit_gaussian()
                if peak is not None:
                    self._fitted_peak = peak
                    self._state = self.PRECISE_RETURN
                    self._return_steps_needed = len(self._points) - self._best_pos - 1
                    self._return_steps_done = 0
                    r2 = peak[2]
                    return {"action": action, "contrast": round(contrast, 2),
                            "duration": 0.2, "stage": "coarse",
                            "message": f"下降后稳定(R²={r2:.3f}),回退到best(需{self._return_steps_needed}步)"}

            # 1d. R²<0.8 且 best<100 且 平坦 → 反向
            if self._best_contrast < 100 and self._check_flat_region():
                self._do_reverse()
                if self._reverse_count >= self._max_reverse:
                    r2_val = r2 if r2 is not None else 0
                    self._state = self.FAILED
                    return {"action": "stop", "contrast": round(contrast, 2),
                            "duration": 0, "stage": "error",
                            "message": f"R²={r2_val:.3f},无法拟合,对焦失败"}
                action = "focus_far" if self._direction > 0 else "focus_near"
                dir_name = '远' if self._direction > 0 else '近'
                return {"action": action, "contrast": round(contrast, 2),
                        "duration": 0.2, "stage": "coarse",
                        "message": f"平坦+4点下降,反向(重试 {self._reverse_count}/3,方向={dir_name})"}
        
        # ── 检查2: 平坦区域（无4点下降）→ 反向 ──
        if self._check_flat_region():
            self._do_reverse()
            if self._reverse_count >= self._max_reverse:
                self._state = self.FAILED
                r2 = self._calc_r2() if len(self._points) >= 8 else None
                r2_val = r2 if r2 is not None else 0
                return {"action": "stop", "contrast": round(contrast, 2),
                        "duration": 0, "stage": "error",
                        "message": f"R²={r2_val:.3f},无法拟合,对焦失败"}
            action = "focus_far" if self._direction > 0 else "focus_near"
            dir_name = '远' if self._direction > 0 else '近'
            return {"action": action, "contrast": round(contrast, 2),
                    "duration": 0.2, "stage": "coarse",
                    "message": f"平坦区域,反向(重试 {self._reverse_count}/3,方向={dir_name})"}

        # ── 检查3: 过峰值检测 → 精确对焦 ──
        if self._check_past_peak():
            peak = self._fit_gaussian()
            self._fitted_peak = peak
            self._state = self.PRECISE_RETURN
            self._return_steps_needed = len(self._points) - self._best_pos - 1
            self._return_steps_done = 0
            r2_msg = f"R²={peak[2]:.3f}" if peak else "无拟合"
            return {"action": action, "contrast": round(contrast, 2),
                    "duration": 0.2, "stage": "coarse",
                    "message": f"过峰值检测({r2_msg},best={self._best_contrast:.1f}),回退到best(需{self._return_steps_needed}步)"}

        # ── 检查4: R²<0.8 且 best<100 → 对焦失败 ──
        r2 = self._calc_r2()
        if r2 is not None and r2 < 0.8 and self._best_contrast < 100:
            self._state = self.FAILED
            return {"action": "stop", "contrast": round(contrast, 2),
                    "duration": 0, "stage": "error",
                    "message": f"对焦失败(R²={r2:.3f}<0.8,best={self._best_contrast:.1f}<100)"}

        # ── 默认: 继续采样 ──
        if r2 is not None:
            return {"action": action, "contrast": round(contrast, 2),
                    "duration": 0.2, "stage": "coarse",
                    "message": f"采样(R²={r2:.3f},best={self._best_contrast:.1f},方向={dir_name})"}
        else:
            return {"action": action, "contrast": round(contrast, 2),
                    "duration": 0.2, "stage": "coarse",
                    "message": f"采样(best={self._best_contrast:.1f},方向={dir_name})"}

    def _calc_r2(self):
        """计算当前数据点的R²"""
        peak = self._fit_gaussian()
        if peak is None:
            return None
        return peak[2]

    def _step_precise_return(self, contrast):
        """精确对焦 - 回退阶段（0.2s粗调步长）
        
        回退到best位置附近，然后切换到缓慢逼近阶段。
        回退方向 = 反向（因为当前在best之后，需要回到best）
        """
        self._return_steps_done += 1
        # 回退方向 = 反向
        reverse_dir = -self._direction
        action = "focus_far" if reverse_dir > 0 else "focus_near"

        if self._return_steps_done >= self._return_steps_needed:
            # 回退完成，切换到缓慢逼近
            self._state = self.PRECISE_APPROACH
            self._prev_contrast = contrast
            return {"action": action, "contrast": round(contrast, 2),
                    "duration": 0.2, "stage": "precise_return",
                    "message": f"回退完成(反差={contrast:.1f}),切换到缓慢逼近"}

        return {"action": action, "contrast": round(contrast, 2),
                "duration": 0.2, "stage": "precise_return",
                "message": f"回退中({self._return_steps_done}/{self._return_steps_needed},反差={contrast:.1f})"}

    def _step_precise_approach(self, contrast):
        """精确对焦 - 缓慢逼近阶段（0.05s精调步长）
        
        向拟合峰值位置缓慢移动。
        从上升到出现下降的第一点，反向移动1步，完成。
        """
        self._approach_step += 1

        # 确定移动方向：向拟合峰值移动
        if self._fitted_peak is not None:
            fitted_pos = self._fitted_peak[0]
            current_pos = len(self._points)
            if current_pos < fitted_pos:
                action = "focus_far"
            else:
                action = "focus_near"
        else:
            # 无拟合数据：不移动，只采样等待下降信号
            action = "stop"

        # 检查下降（从上升到下降的第一点）
        if self._prev_contrast > 0 and contrast < self._prev_contrast:
            # 出现下降，反向移动1步，完成
            self._state = self.DONE
            return {"action": "stop", "contrast": round(self._prev_contrast, 2),
                    "duration": 0, "stage": "done",
                    "message": f"精确对焦完成(下降第一点,返回1步,best={self._prev_contrast:.1f})"}

        self._prev_contrast = contrast
        return {"action": action, "contrast": round(contrast, 2),
                "duration": 0.05, "stage": "precise_approach",
                "message": f"缓慢逼近(步{self._approach_step},反差={contrast:.1f},best={self._best_contrast:.1f})"}

    def step(self, bgr: np.ndarray) -> dict:
        contrast = calc_contrast(bgr)

        if self._state == self.COARSE:
            return self._step_coarse(contrast)
        elif self._state == self.PRECISE_RETURN:
            return self._step_precise_return(contrast)
        elif self._state == self.PRECISE_APPROACH:
            return self._step_precise_approach(contrast)
        elif self._state == self.DONE:
            return {"action": "stop", "contrast": round(contrast, 2),
                    "duration": 0, "stage": "done",
                    "message": "对焦完成"}
        else:  # FAILED
            return {"action": "stop", "contrast": round(contrast, 2),
                    "duration": 0, "stage": "error",
                    "message": "对焦失败"}