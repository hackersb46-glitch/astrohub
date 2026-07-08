"""Rewrite whitebalance.py IterativeWB: dynamic 3-tier fine stage"""

path = r"C:\Users\admin\.openclaw\agents\dev-factory\astrohub\src\controlpanel\whitebalance.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Replace __init__
old_init = """    def __init__(self, current_red=100, current_blue=100):
        self._stage = 0
        self._stage_steps = [5, 2, 1]
        self._stage_min = [6, 3, 0]
        self._tolerances = [0.70, 0.80, 0.95]
        self._current_red = current_red
        self._current_blue = current_blue
        self._no_improve = 0
        self._stage_step_count = 0
        self._fine_steps = 0
        self._best_red = current_red
        self._best_blue = current_blue
        self._best_delta = 999.0
        self._best_step = 0
        self._step_count = 0"""

new_init = """    def __init__(self, current_red=100, current_blue=100):
        self._stage = 0
        self._stage_steps = [5, 2, 1]
        self._stage_min = [6, 3, 0]
        self._tolerances = [0.70, 0.80, 0.95]
        self._current_red = current_red
        self._current_blue = current_blue
        self._no_improve = 0
        self._stage_step_count = 0
        self._fine_steps = 0          # 1步模式计数器（上限30）
        self._best_red = current_red
        self._best_blue = current_blue
        self._best_delta = 999.0
        self._best_step = 0
        self._step_count = 0"""

content = content.replace(old_init, new_init)
print("OK: __init__ updated")

# 2. Replace the entire step() method
# Find step method start and end
step_start = content.find("    def step(self, bgr) -> dict:")
if step_start == -1:
    print("ERROR: step method not found")
    exit(1)

# Find next method (_eval)
step_end = content.find("\n    def _eval(self", step_start)
if step_end == -1:
    print("ERROR: _eval method not found")
    exit(1)

old_step = content[step_start:step_end]

new_step = '''    def step(self, bgr) -> dict:
        """输入BGR图像，返回下一步动作"""
        stats = _rgb_stats(bgr)
        n = stats["n"]
        r_sum, g_sum, b_sum = stats["r_sum"], stats["g_sum"], stats["b_sum"]

        self._step_count += 1
        self._stage_step_count += 1

        # 计算当前delta
        actual = abs(r_sum / max(1, g_sum) - 1.0) + abs(b_sum / max(1, g_sum) - 1.0)

        # 精调阶段：根据delta动态选择步长
        if self._stage == 2:
            if actual >= 200:
                step = 5
            elif actual >= 10:
                step = 2
            else:
                step = 1
        else:
            step = self._stage_steps[self._stage]

        # 计算候选增益
        cr = self._current_red + max(-step, min(step, int(g_sum / max(1, r_sum) * self._current_red) - self._current_red))
        cb = self._current_blue + max(-step, min(step, int(g_sum / max(1, b_sum) * self._current_blue) - self._current_blue))
        cr = max(1, min(255, cr))
        cb = max(1, min(255, cb))

        # 候选列表 (stage 2: R/B独立调整)
        if self._stage == 2:
            candidates = [(cr, self._current_blue, "red"), (self._current_red, cb, "blue")]
        else:
            candidates = [(cr, cb, "both"), (cr, self._current_blue, "red"), (self._current_red, cb, "blue")]

        # 选最优候选
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

        # 更新best
        prev_best = self._best_delta
        if actual < self._best_delta:
            self._best_delta = actual
            self._best_red = self._current_red
            self._best_blue = self._current_blue
            self._best_step = self._step_count

        # 无改善计数
        tolerance = self._tolerances[self._stage]
        if actual >= prev_best * tolerance:
            self._no_improve += 1
        else:
            self._no_improve = 0

        stage_name = ["coarse", "medium", "fine"][self._stage]
        min_steps = self._stage_min[self._stage]

        # 阶段升级
        if self._stage < 2 and self._stage_step_count >= min_steps and self._no_improve >= 2:
            self._stage += 1
            self._stage_step_count = 0
            self._no_improve = 0
            # 进入精调时重置best追踪
            if self._stage == 2:
                self._best_delta = 999.0
                self._best_red = self._current_red
                self._best_blue = self._current_blue
                self._best_step = self._step_count
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

        # 精调阶段：1步模式计数器（上限30）
        if self._stage == 2 and step == 1:
            self._fine_steps += 1
            if self._fine_steps >= 30:
                rollback = (self._best_red != self._current_red or self._best_blue != self._current_blue)
                self._current_red = self._best_red
                self._current_blue = self._best_blue
                return {
                    "action": "stop",
                    "stage": "done",
                    "step_size": 0,
                    "red_gain": self._best_red, "blue_gain": self._best_blue,
                    "r_avg": round(stats["r_avg"], 1), "g_avg": round(stats["g_avg"], 1), "b_avg": round(stats["b_avg"], 1),
                    "delta": round(self._best_delta, 4), "best_delta": round(self._best_delta, 4), "pixels": n,
                    "message": f"白平衡完成(1步精调{self._fine_steps}次上限) {'(回滚至最佳)' if rollback else '(已达最佳)'} 第{self._best_step}步"
                }

        # 应用新增益
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

'''

content = content[:step_start] + new_step + content[step_end:]
print("OK: step method replaced")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("DONE: whitebalance.py fully updated")
