"""AstroHub v8.59 - 反差对焦模块（黄金分割+三次样条）

算法流程：
1. 扫描：等步长移动焦点，每步截图计算反差 → 收集 (position, contrast) 数据点
2. 峰值检测：反差下降N步后确认峰值，停止扫描
3. 三次样条拟合：对数据点拟合自然三次样条
4. 黄金分割搜索：在样条曲线上精确找峰
5. 移动到峰值位置

参考：github.com/russwong89/sharpness_detection_autofocus
"""

import json
import asyncio
import math
import numpy as np
from .region_base import calc_contrast, calc_stable_delay, SearcherBase

# 黄金分割比例
GR = (math.sqrt(5) - 1) / 2


class CubicSpline:
    """自然三次样条插值。

    在数据点之间拟合三次多项式段，
    端点处二阶导数=0（自然样条）。
    """

    def __init__(self, x_vals, y_vals):
        self.x_vals = np.array(x_vals, dtype=float)
        self.y_vals = np.array(y_vals, dtype=float)
        self.n = len(x_vals) - 1
        self._coeffs = None
        self._fit()

    def _fit(self):
        """求解三次样条系数。"""
        n = self.n
        if n < 1:
            return

        size = 4 * n
        A = np.zeros((size, size))
        b = np.zeros(size)

        row = 0
        # 2*n 方程：每段通过两端点
        for i in range(n):
            A[row][4*i] = self.x_vals[i]**3
            A[row][4*i+1] = self.x_vals[i]**2
            A[row][4*i+2] = self.x_vals[i]
            A[row][4*i+3] = 1
            b[row] = self.y_vals[i]
            row += 1

            A[row][4*i] = self.x_vals[i+1]**3
            A[row][4*i+1] = self.x_vals[i+1]**2
            A[row][4*i+2] = self.x_vals[i+1]
            A[row][4*i+3] = 1
            b[row] = self.y_vals[i+1]
            row += 1

        # n-1 方程：一阶导数连续
        for i in range(n-1):
            A[row][4*i] = 3*self.x_vals[i+1]**2
            A[row][4*i+1] = 2*self.x_vals[i+1]
            A[row][4*i+2] = 1
            A[row][4*i+4] = -3*self.x_vals[i+1]**2
            A[row][4*i+5] = -2*self.x_vals[i+1]
            A[row][4*i+6] = -1
            row += 1

        # n-1 方程：二阶导数连续
        for i in range(n-1):
            A[row][4*i] = 6*self.x_vals[i+1]
            A[row][4*i+1] = 2
            A[row][4*i+4] = -6*self.x_vals[i+1]
            A[row][4*i+5] = -2
            row += 1

        # 2 方程：自然样条端点
        A[row][0] = 6*self.x_vals[0]
        A[row][1] = 2
        row += 1
        A[row][4*(n-1)] = 6*self.x_vals[n]
        A[row][4*(n-1)+1] = 2

        try:
            self._coeffs = np.linalg.solve(A, b)
        except np.linalg.LinAlgError:
            self._coeffs = None

    def evaluate(self, x):
        """计算样条在 x 处的值。"""
        if self._coeffs is None:
            return 0.0

        # 找到对应段
        idx = 0
        for i in range(self.n):
            if self.x_vals[i] <= x <= self.x_vals[i+1]:
                idx = i
                break

        a = self._coeffs[4*idx]
        b = self._coeffs[4*idx+1]
        c = self._coeffs[4*idx+2]
        d = self._coeffs[4*idx+3]
        return float(a*x**3 + b*x**2 + c*x + d)


def golden_section_search(spline, x_low, x_up, req_err=0.01):
    """黄金分割法在样条曲线上搜索峰值。

    返回 (x_optimal, y_optimal)。
    """
    d = GR * abs(x_up - x_low)
    x1 = x_low + d
    x2 = x_up - d

    while True:
        d = GR * d
        y1 = spline.evaluate(x1)
        y2 = spline.evaluate(x2)

        if y1 >= y2:
            max_err = max(abs(x_up - x1), abs(x1 - x2))
            if max_err < req_err:
                return (x1, y1)
            x_low = x2
            x1 = x_low + d
            x2 = x_up - d
        else:
            max_err = max(abs(x1 - x2), abs(x2 - x_low))
            if max_err < req_err:
                return (x2, y2)
            x_up = x1
            x1 = x_low + d
            x2 = x_up - d


class ContrastAF:
    """反差对焦 - 黄金分割+三次样条。

    状态：SCAN → APPROACH → DONE/FAILED

    扫描阶段等步长移动，收集(位置,反差)数据点。
    峰值确认后拟合三次样条，用黄金分割法精确找峰。
    """

    SCAN = "scan"
    APPROACH = "approach"
    FINE = "fine"   # 0.1s 精逼近
    DONE = "done"
    FAILED = "failed"

    def __init__(self):
        self._state = self.SCAN
        self._direction = -1  # -1=near, 1=far
        self._attempt = 0

        # 搜索数据
        self._points = []  # [(position, contrast), ...]
        self._step_count = 0
        self._best1_value = 0.0  # 扫描峰值（保留）
        self._best_value = 0.0   # 当前最佳（可能被样条覆盖）
        self._best2_value = 0.0   # approach阶段最佳
        self._best3_value = 0.0   # 0.1s精逼近最佳
        self._best_pos = 0
        self._decline_count = 0
        self._decline_after_best = 0

        # 平坦区域
        self._flat_reversed = False

        # 回退/精逼近
        self._optimal_pos = None
        self._approach_remaining = 0
        self._approach_dir = 1
        self._fine_step = 0
        self._fine_dir = 1
        self._fine_max_steps = 10

    def step(self, contrast: float) -> dict:
        if self._state == self.SCAN:
            return self._step_scan(contrast)
        elif self._state == self.APPROACH:
            return self._step_approach(contrast)
        elif self._state == self.FINE:
            return self._step_fine(contrast)
        elif self._state == self.DONE:
            return {"action": "stop", "duration": 0, "stage": "done",
                    "contrast": round(self._best3_value or self._best_value, 2),
                    "message": "对焦成功", "best": self._best3_value or self._best_value}
        else:
            return {"action": "stop", "duration": 0, "stage": "error",
                    "contrast": 0, "message": "对焦失败"}

    def _step_scan(self, contrast):
        """扫描阶段：等步长移动，收集数据点。"""
        pos = len(self._points)
        self._points.append((pos, contrast))
        self._step_count += 1

        # 更新 best1/best
        is_new_best = False
        if contrast > self._best_value:
            self._best_value = contrast
            self._best1_value = contrast  # best1 = 扫描峰值
            self._best_pos = pos
            self._decline_after_best = 0
            is_new_best = True

        # 下降检测
        if pos > 0:
            prev = self._points[pos-1][1]
            if contrast < prev:
                self._decline_count += 1
            else:
                self._decline_count = 0
            if not is_new_best:
                self._decline_after_best += 1

        action = "focus_near" if self._direction < 0 else "focus_far"
        dir_name = '近' if self._direction < 0 else '远'

        # 首步
        if pos == 0:
            return {
                "action": action, "duration": 0.2,
                "stage": "scan", "contrast": round(contrast, 2),
                "message": f"开始对焦(方向={dir_name},尝试{self._attempt+1}/3)"
            }

        # 峰值确认：best>25 + 下降≥3步 → 样条拟合+黄金分割
        if self._decline_after_best >= 3 and self._best_value > 25:
            return self._fit_and_search(contrast)

        # 趋势下降检测：最近8步中后半均值明显低于前半 → 反向
        if self._step_count >= 8 and self._check_declining_trend():
            if not self._do_retry():
                self._state = self.FAILED
                return {
                    "action": "stop", "duration": 0,
                    "stage": "error", "contrast": round(contrast, 2),
                    "message": "对焦失败(3次重试耗尽)"
                }
            action = "focus_near" if self._direction < 0 else "focus_far"
            dir_name = '近' if self._direction < 0 else '远'
            return {
                "action": action, "duration": 0.2,
                "stage": "scan", "contrast": round(contrast, 2),
                "message": f"趋势下降,反向(方向={dir_name},尝试{self._attempt+1}/3)"
            }

        # 趋势恶化：连续8步无新best → 方向错误，反向（不限best值）
        if self._decline_after_best >= 8:
            if not self._do_retry():
                self._state = self.FAILED
                return {
                    "action": "stop", "duration": 0,
                    "stage": "error", "contrast": round(contrast, 2),
                    "message": "对焦失败(3次重试耗尽)"
                }
            action = "focus_near" if self._direction < 0 else "focus_far"
            dir_name = '近' if self._direction < 0 else '远'
            return {
                "action": action, "duration": 0.2,
                "stage": "scan", "contrast": round(contrast, 2),
                "message": f"趋势恶化(8步无新best),反向(方向={dir_name},尝试{self._attempt+1}/3)"
            }

        # 反向：连续5步下降
        if self._decline_count >= 5:
            if not self._do_retry():
                self._state = self.FAILED
                return {
                    "action": "stop", "duration": 0,
                    "stage": "error", "contrast": round(contrast, 2),
                    "message": "对焦失败(3次重试耗尽)"
                }
            action = "focus_near" if self._direction < 0 else "focus_far"
            dir_name = '近' if self._direction < 0 else '远'
            return {
                "action": action, "duration": 0.2,
                "stage": "scan", "contrast": round(contrast, 2),
                "message": f"反向(方向={dir_name},尝试{self._attempt+1}/3)"
            }

        # 平坦区域: 10步无变化 → 反向; 反向也平坦 → 0.5s加速
        if self._step_count >= 10 and self._check_flat():
            if not self._flat_reversed:
                self._flat_reversed = True
                if not self._do_retry():
                    self._state = self.FAILED
                    return {
                        "action": "stop", "duration": 0,
                        "stage": "error", "contrast": round(contrast, 2),
                        "message": "对焦失败(3次重试耗尽)"
                    }
                action = "focus_near" if self._direction < 0 else "focus_far"
                return {
                    "action": action, "duration": 0.2,
                    "stage": "scan", "contrast": round(contrast, 2),
                    "message": f"平坦区({self._step_count}步),反向"
                }
            else:
                return {
                    "action": action, "duration": 0.5,
                    "stage": "scan", "contrast": round(contrast, 2),
                    "message": f"平坦区持续,加速({self._step_count}步,best={self._best_value:.1f})"
                }

        # R²检测: R²≥80% 且 best≤50 → 失败
        if self._step_count % 5 == 0:
            r2 = self._calc_r2()
            if r2 is not None and r2 >= 0.8 and self._best_value <= 25:
                if not self._do_retry():
                    self._state = self.FAILED
                    return {
                        "action": "stop", "duration": 0,
                        "stage": "error", "contrast": round(contrast, 2),
                        "message": f"对焦失败(R²={r2:.2f},best={self._best_value:.1f}<=25)"
                    }
                action = "focus_near" if self._direction < 0 else "focus_far"
                return {
                    "action": action, "duration": 0.2,
                    "stage": "scan", "contrast": round(contrast, 2),
                    "message": f"峰值过低,反向(尝试{self._attempt+1}/3)"
                }

        # 超时
        if self._step_count >= 90:
            self._state = self.FAILED
            return {
                "action": "stop", "duration": 0,
                "stage": "error", "contrast": round(contrast, 2),
                "message": f"扫描超时({self._step_count}步)"
            }

        return {
            "action": action, "duration": 0.2,
            "stage": "scan", "contrast": round(contrast, 2),
            "message": f"采样(best={self._best_value:.1f},方向={dir_name})"
        }

    def _fit_and_search(self, contrast: float):
        """三次样条拟合 + 黄金分割搜索。"""
        x_vals = [p[0] for p in self._points]
        y_vals = [p[1] for p in self._points]

        # 数据点不足 → 回退到简单 best
        if len(x_vals) < 4:
            self._state = self.DONE
            return {
                "action": "stop", "duration": 0,
                "stage": "done", "contrast": round(self._best_value, 2),
                "message": f"对焦成功(数据不足,使用best={self._best_value:.1f})",
                "best": self._best_value
            }

        # R²质量检验 → 低质量：不拟合样条，但仍回退到 best_pos
        r2 = self._calc_r2()
        if r2 is not None and r2 < 0.6:
            current_pos = len(self._points) - 1
            delta = current_pos - self._best_pos  # 需要回退的步数
            if abs(delta) < 1:
                self._state = self.DONE
                return {
                    "action": "stop", "duration": 0,
                    "stage": "done", "contrast": round(self._best_value, 2),
                    "message": f"对焦成功(R²={r2:.2f}<0.6,已在best={self._best_value:.1f})",
                    "best": self._best_value
                }
            self._approach_remaining = abs(delta)
            self._approach_dir = -self._direction
            action = "focus_near" if self._approach_dir < 0 else "focus_far"
            self._best2_value = self._best_value
            self._state = self.APPROACH
            return {
                "action": action,
                "duration": 0.2,
                "stage": "approach",
                "contrast": round(contrast, 2),
                "message": f"R²={r2:.2f}<0.6,回退到best(剩余{self._approach_remaining}步,best={self._best_value:.1f})"
            }

        # 拟合样条
        spline = CubicSpline(x_vals, y_vals)
        if spline._coeffs is None:
            # 拟合失败：回退到 best_pos
            current_pos = len(self._points) - 1
            delta = current_pos - self._best_pos
            if abs(delta) < 1:
                self._state = self.DONE
                return {
                    "action": "stop", "duration": 0,
                    "stage": "done", "contrast": round(self._best_value, 2),
                    "message": f"对焦成功(样条拟合失败,已在best={self._best_value:.1f})",
                    "best": self._best_value
                }
            self._approach_remaining = abs(delta)
            self._approach_dir = -self._direction
            action = "focus_near" if self._approach_dir < 0 else "focus_far"
            self._best2_value = self._best_value
            self._state = self.APPROACH
            return {
                "action": action,
                "duration": 0.2,
                "stage": "approach",
                "contrast": round(contrast, 2),
                "message": f"样条拟合失败,回退到best(剩余{self._approach_remaining}步)"
            }

        # 黄金分割搜索（缩小到峰值附近±2步，避免样条振荡区）
        best_idx = self._best_pos
        x_low = max(x_vals[0], best_idx - 2)
        x_up = min(x_vals[-1], best_idx + 2)

        candidates = []
        try:
            opt = golden_section_search(spline, x_low, x_up)
            candidates.append(opt)
        except Exception:
            pass

        if not candidates:
            # 搜索失败：回退到 best_pos
            current_pos = len(self._points) - 1
            delta = current_pos - self._best_pos
            if abs(delta) < 1:
                self._state = self.DONE
                return {
                    "action": "stop", "duration": 0,
                    "stage": "done", "contrast": round(self._best_value, 2),
                    "message": f"对焦成功(搜索失败,已在best={self._best_value:.1f})",
                    "best": self._best_value
                }
            self._approach_remaining = abs(delta)
            self._approach_dir = -self._direction
            action = "focus_near" if self._approach_dir < 0 else "focus_far"
            self._best2_value = self._best_value
            self._state = self.APPROACH
            return {
                "action": action,
                "duration": 0.2,
                "stage": "approach",
                "contrast": round(contrast, 2),
                "message": f"搜索失败,回退到best(剩余{self._approach_remaining}步)"
            }

        opt_x, opt_y = max(candidates, key=lambda c: c[1])
        self._best1_value = self._best_value  # 保存扫描峰值
        self._best_value = opt_y  # 用样条峰值覆盖
        self._optimal_pos = opt_x

        # 计算回退步数（整数，每步0.2s，与扫描步长一致）
        current_pos = x_vals[-1]
        delta = current_pos - opt_x  # 需要回退的步数

        if abs(delta) < 0.5:
            # 已在峰值附近
            self._state = self.DONE
            return {
                "action": "stop", "duration": 0,
                "stage": "done", "contrast": round(opt_y, 2),
                "message": f"对焦成功(峰值={opt_y:.1f}@pos={opt_x:.2f},已在峰值)",
                "best": opt_y
            }

        # 离散回退：每步0.2s（与扫描步长一致，消除电机非线性）
        self._approach_remaining = int(round(abs(delta)))
        self._approach_dir = -self._direction  # 回退方向

        if self._approach_remaining <= 0:
            self._state = self.DONE
            return {
                "action": "stop", "duration": 0,
                "stage": "done", "contrast": round(opt_y, 2),
                "message": f"对焦成功(峰值={opt_y:.1f}@pos={opt_x:.2f})",
                "best": opt_y
            }

        action = "focus_near" if self._approach_dir < 0 else "focus_far"
        self._best2_value = self._best_value
        self._state = self.APPROACH

        return {
            "action": action,
            "duration": 0.2,
            "stage": "approach",
            "contrast": round(self._points[-1][1], 2),
            "message": f"样条峰值={opt_y:.1f}@pos={opt_x:.2f},回退{self._approach_remaining}步"
        }

    def _step_approach(self, contrast):
        """逐步回退到峰值位置（每步0.2s，与扫描步长一致）。"""
        # best2 = 扫描峰值，approach 阶段继续跟踪 max
        if contrast > self._best2_value:
            self._best2_value = contrast

        self._approach_remaining -= 1

        if self._approach_remaining <= 0:
            # 0.2s 回退完成 → 进入 0.1s 精逼近
            # best2 = max(扫描峰值, approach阶段最大值)
            self._best3_value = self._best2_value
            self._fine_step = 0
            self._fine_dir = self._approach_dir  # 继续同方向
            self._state = self.FINE
            action = "focus_near" if self._fine_dir < 0 else "focus_far"
            return {
                "action": action,
                "duration": 0.1,
                "stage": "fine",
                "contrast": round(contrast, 2),
                "message": f"粗逼近完成(best2={self._best2_value:.1f}),开始精逼近(0.1s)"
            }

        # 继续回退
        action = "focus_near" if self._approach_dir < 0 else "focus_far"
        return {
            "action": action,
            "duration": 0.2,
            "stage": "approach",
            "contrast": round(contrast, 2),
            "message": f"逼近(剩余{self._approach_remaining}步,峰值={self._best_value:.1f})"
        }

    def _step_fine(self, contrast):
        """精逼近阶段：0.1s步进微调，最多10步。
        
        成功条件：best3 > best2 或 best3 > best1
        失败（10步未达标）：全流程重置
        """
        self._fine_step += 1

        # 追踪 best3
        if contrast > self._best3_value:
            self._best3_value = contrast

        # 成功：best3 > best2 或 best3 > best1
        if self._best3_value > self._best2_value or self._best3_value > self._best1_value:
            self._state = self.DONE
            best = max(self._best3_value, self._best2_value, self._best1_value)
            return {
                "action": "stop", "duration": 0,
                "stage": "done", "contrast": round(contrast, 2),
                "message": f"对焦成功(best3={self._best3_value:.1f},best2={self._best2_value:.1f},best1={self._best1_value:.1f})",
                "best": best
            }

        # 趋势下降 → 反向
        if contrast < self._best3_value:
            self._fine_dir = -self._fine_dir

        # 达到最大步数仍未达标 → 全流程重置
        if self._fine_step >= self._fine_max_steps:
            if self._do_retry():
                action = "focus_near" if self._direction < 0 else "focus_far"
                dir_name = '近' if self._direction < 0 else '远'
                return {
                    "action": action, "duration": 0.2,
                    "stage": "scan", "contrast": round(contrast, 2),
                    "message": f"精逼近未达标(best3={self._best3_value:.1f}≤best2={self._best2_value:.1f}),全流程重启(尝试{self._attempt+1}/3)"
                }
            self._state = self.FAILED
            return {
                "action": "stop", "duration": 0,
                "stage": "error", "contrast": round(contrast, 2),
                "message": f"对焦失败(3次重试耗尽,best3={self._best3_value:.1f},best2={self._best2_value:.1f})"
            }

        # 继续精逼近
        action = "focus_near" if self._fine_dir < 0 else "focus_far"
        return {
            "action": action,
            "duration": 0.1,
            "stage": "fine",
            "contrast": round(contrast, 2),
            "message": f"精逼近(步{self._fine_step}/{self._fine_max_steps},best3={self._best3_value:.1f},best2={self._best2_value:.1f})"
        }


    def _check_flat(self):
        """检查平坦区域。"""
        if len(self._points) < 5:
            return False
        recent = [p[1] for p in self._points[-5:]]
        max_v, min_v = max(recent), min(recent)
        if max_v <= 0:
            return False
        return (max_v - min_v) / max_v < 0.10

    def _check_declining_trend(self):
        """检查最近8步是否明显趋势下降（后半均值 < 前半均值 × 0.8）。"""
        if len(self._points) < 8:
            return False
        recent = [p[1] for p in self._points[-8:]]
        first_half = recent[:4]
        second_half = recent[4:]
        avg_first = sum(first_half) / 4
        avg_second = sum(second_half) / 4
        if avg_first <= 0:
            return False
        return avg_second < avg_first * 0.9

    def _calc_r2(self):
        """计算 R²。"""
        if len(self._points) < 8:
            return None
        best_idx = max(range(len(self._points)), key=lambda i: self._points[i][1])
        left, right = best_idx, len(self._points) - best_idx - 1
        if left < 4 or right < 3:
            return None
        xs = np.array([p[0] for p in self._points])
        ys = np.array([p[1] for p in self._points])
        ys_safe = np.maximum(ys, 0.1)
        ln_y = np.log(ys_safe)
        try:
            A, B, C = np.polyfit(xs, ln_y, 2)
            if A >= 0:
                return None
            ln_y_pred = A * xs**2 + B * xs + C
            ss_res = np.sum((ln_y - ln_y_pred)**2)
            ss_tot = np.sum((ln_y - np.mean(ln_y))**2)
            return 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        except Exception:
            return None

    def _do_retry(self):
        """执行重试：全流程重置。"""
        self._attempt += 1
        if self._attempt >= 3:
            return False
        self._direction *= -1
        self._points = []
        self._best1_value = 0.0
        self._best_value = 0.0
        self._best2_value = 0.0
        self._best3_value = 0.0
        self._best_pos = 0
        self._decline_count = 0
        self._decline_after_best = 0
        self._step_count = 0
        self._optimal_pos = None
        self._approach_remaining = 0
        self._fine_step = 0
        self._state = self.SCAN
        return True


class FocusSearcher(SearcherBase):
    """对焦搜索执行器。"""

    def __init__(self, mgr, device_ip, client, x, y, w, h, capture_func, cleanup_func, mac_clean=""):
        super().__init__(mgr, device_ip, client, x, y, w, h, capture_func, cleanup_func, mac_clean)
        self.search_type = "Focus"

    def _set_manual_focus(self):
        """设置手动对焦模式。"""
        try:
            ctrl, err = self.mgr._get_controller(self.device_ip)
            if not err and ctrl.client:
                xml = '''<?xml version="1.0" encoding="UTF-8"?>
<FocusConfiguration version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <focusStyle>MANUAL</focusStyle>
  <focusLimited>300</focusLimited>
</FocusConfiguration>'''
                result = ctrl.client.put("/Image/channels/1/focusConfiguration", xml)
                return result.status_code == 200
        except Exception:
            pass
        return False

    def _move_focus(self, direction: str, duration: float):
        """移动焦点。"""
        ptz_dir = "focus-far" if direction == "focus_far" else "focus-near"
        self.mgr.ptz_move(self.device_ip, direction=ptz_dir, speed=60)

    def _stop_focus(self):
        """停止焦点移动。"""
        self.mgr.ptz_stop(self.device_ip)

    async def run(self):
        """运行对焦搜索，产生 SSE 事件。"""

        # v8.64: 快门延迟只读一次
        self._stable_delay = await asyncio.to_thread(calc_stable_delay, self.client)

        # 1. 设置手动对焦
        ok = await asyncio.to_thread(self._set_manual_focus)
        if not ok:
            yield f"data: {json.dumps({'type': 'warning', 'message': '设置手动对焦失败'})}\n\n"

        # 2. 初始截图
        bgr, info = await asyncio.to_thread(self._capture)
        if bgr is None:
            err_msg = (info or {}).get('error', '截图失败')
            yield f"data: {json.dumps({'type': 'error', 'message': err_msg})}\n\n"
            return

        crop_msg = f"X={info['crop_x1']}~{info['crop_x2']}, Y={info['crop_y1']}~{info['crop_y2']}, 共{info['pixels']}像素"
        yield f"data: {json.dumps({'type': 'start', 'crop': crop_msg})}\n\n"

        # 3. 对焦循环
        af = ContrastAF()
        step_count = 0

        while True:
            # v8.41: 检查中断
            if self._interrupted:
                await asyncio.to_thread(self._stop_focus)
                yield f"data: {json.dumps({'type': 'interrupt', 'message': '用户停止'})}\n\n"
                break

            contrast = calc_contrast(bgr)
            cmd = af.step(contrast)
            step_count += 1

            event = {
                "type": "focus",
                "step": step_count,
                "stage": cmd.get("stage", ""),
                "action": cmd["action"],
                "contrast": cmd["contrast"],
                "duration": cmd["duration"],
                "message": cmd["message"]
            }
            yield f"data: {json.dumps(event)}\n\n"

            if cmd["action"] == "stop":
                # 验证
                bgr2, _ = await asyncio.to_thread(self._capture)
                final_contrast = calc_contrast(bgr2) if bgr2 is not None else cmd["contrast"]
                best = cmd.get("best", cmd["contrast"])
                verified = final_contrast >= best * 0.95

                yield f"data: {json.dumps({'type': 'done', 'final_contrast': round(final_contrast, 2), 'best_contrast': round(best, 2), 'total_steps': step_count, 'verified': verified})}\n\n"
                # v8.73: 存储基线
                from src.controlpanel.region_base import write_search_baseline
                write_search_baseline(self.device_ip, 'focus', {
                    'contrast': round(final_contrast, 2),
                    'best_contrast': round(best, 2)
                })
                break

            # 移动
            await asyncio.to_thread(self._move_focus, cmd["action"], cmd["duration"])
            await asyncio.sleep(cmd["duration"])
            await asyncio.to_thread(self._stop_focus)
            await asyncio.sleep(self._stable_delay)  # v8.64: 等待稳定（快门缓存）

            # 重新截图
            bgr, info2 = await asyncio.to_thread(self._capture)
            if bgr is None:
                await asyncio.to_thread(self._stop_focus)
                err_msg = (info2 or {}).get('error', '截图失败')
                yield f"data: {json.dumps({'type': 'error', 'message': err_msg})}\n\n"
                break

        # 4. 清理
        await asyncio.to_thread(self._cleanup_func, "Focus", self.device_ip)
        yield f"data: {json.dumps({'type': 'cleanup'})}\n\n"
