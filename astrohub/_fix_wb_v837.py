"""Fix whitebalance.py: 恢复精调停止条件，只保留步进5和2的动态调整"""

path = r"C:\Users\admin\.openclaw\agents\dev-factory\astrohub\src\controlpanel\whitebalance.py"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# ── 修改1: 把动态步进的delta<10改为delta<10时就不进入精调阶段（保持step=1） ──
old1 = """        # 精调阶段：根据delta动态选择步长
        if self._stage == 2:
            if actual >= 200:
                step = 5
            elif actual >= 10:
                step = 2
            else:
                step = 1
        else:
            step = self._stage_steps[self._stage]"""

new1 = """        # 精调阶段：根据delta动态选择步长（delta<10时保持step=1）
        if self._stage == 2:
            if actual >= 200:
                step = 5
            elif actual >= 10:
                step = 2
        else:
            step = self._stage_steps[self._stage]"""

if old1 not in content:
    print("ERROR: old1 not found")
    exit(1)
content = content.replace(old1, new1)
print("OK: 1/2 - fine stage step adjustment updated")

# ── 修改2: 替换精调阶段处理块，恢复 `_no_improve >= 3` 和 `_fine_steps >= 10` 停止条件 ──
old2 = """        # 精调阶段：1步模式计数器（上限30）
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

        # 应用新增益"""

new2 = """        # 精调阶段：恢复 `_no_improve >= 3` 和 `_fine_steps >= 10` 停止条件
        if self._stage == 2:
            self._fine_steps += 1
            if self._no_improve >= 3 or self._fine_steps >= 10:
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
                    "message": f"白平衡完成 {'(回滚至最佳)' if rollback else '(已达最佳)'} 第{self._best_step}步"
                }

        # 应用新增益"""

if old2 not in content:
    print("ERROR: old2 not found")
    exit(1)
content = content.replace(old2, new2)
print("OK: 2/2 - fine stage stop condition restored")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("DONE: whitebalance.py restored to manual version with dynamic step adjustment")
