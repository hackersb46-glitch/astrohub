"""AstroHub v8.67 - 局部亮度控制模块

算法：
- IterativeBrightness: 纯算法迭代搜索（三阶优先级：快门→光圈→增益）
- BrightnessSearcher: 执行层（截图、设置参数、验证、SSE事件）

亮度计算：
- Y = 0.299R + 0.587G + 0.114B（标准亮度）
- 排除死黑死白 → 取有效像素Y均值 → 映射0-100

调整逻辑：
- 优先快门（每次1步opt_values档位）
- 快门到极限 → 调光圈（每次1步opt_values档位）
- 光圈快门都到极限 → 调增益（2阶段：±5粗调→±1精调）
- 全部到极限 → 返回"亮度不足"或"亮度超出"
"""

import json
import asyncio
from .region_base import calc_brightness, calc_stable_delay, SearcherBase


class IterativeBrightness:
    """亮度迭代搜索器 - 三阶优先级

    优先级：快门 → 光圈 → 增益
    快门/光圈：每次±1步（opt_values档位）
    增益：2阶段（±5粗调 → ±1精调）
    无步数限制，全部到极限时终止
    """

    def __init__(self, target: float, shutter_idx: int, iris_idx: int,
                 gain: int, shutter_values: list, iris_values: list,
                 gain_min: int = 0, gain_max: int = 100):
        self._target = target  # 0-100
        self._shutter_values = shutter_values
        self._iris_values = iris_values
        self._gain_min = gain_min
        self._gain_max = gain_max
        self._tolerance = 0.5  # ±0.5 on 0-100 scale

        self._shutter_idx = shutter_idx
        self._iris_idx = iris_idx
        self._gain = gain

        # 增益阶段：1=粗调(±5), 2=精调(±1)
        self._gain_phase = 1
        self._gain_last_direction = 0  # 1=增, -1=减

        # 振荡检测：亮度在目标上下交替超过N次 → 切换到下一参数
        self._cross_count = 0  # 穿越目标次数
        self._last_side = 0  # 1=高于目标, -1=低于目标
        self._best_brightness = None  # 最接近目标的亮度
        self._best_shutter_idx = shutter_idx
        self._best_iris_idx = iris_idx
        self._best_gain = gain
        
        # 参数锁定标记（振荡时锁定当前参数，切换到下一参数）
        self._shutter_frozen = False
        self._iris_frozen = False

        # v8.68: 增益震荡检测
        self._gain_osc_count = 0  # 增益震荡次数
        self._gain_last_side = 0  # 上次在目标哪侧（1=高于, -1=低于）
        self._best_gain_val = gain  # 震荡期间最佳增益

        self._step_count = 0

    def step(self, current_brightness: float) -> dict:
        """输入当前亮度(0-100)，返回下一步动作"""
        self._step_count += 1
        error = self._target - current_brightness
        too_dark = error > 0

        # 容差内 → 完成
        if abs(error) <= self._tolerance:
            return self._make_stop_result("done", current_brightness,
                f"亮度达标 {current_brightness:.1f}≈{self._target}")

        # 振荡检测：跟踪亮度在目标上下穿越
        current_side = -1 if too_dark else 1  # -1=低于目标, 1=高于目标
        if self._last_side != 0 and current_side != self._last_side:
            self._cross_count += 1
        self._last_side = current_side

        # 追踪最接近目标的参数值
        if self._best_brightness is None or abs(error) < abs(self._target - self._best_brightness):
            self._best_brightness = current_brightness
            self._best_shutter_idx = self._shutter_idx
            self._best_iris_idx = self._iris_idx
            self._best_gain = self._gain

        # === 优先级1: 快门 ===
        if not self._shutter_frozen:
            # 振荡检测：穿越目标2次 → 冻结快门，进入光圈
            if self._cross_count >= 2:
                self._shutter_frozen = True
                self._shutter_idx = self._best_shutter_idx
                self._cross_count = 0
                self._last_side = 0
                self._best_brightness = None
                # fall through to iris
            elif too_dark and self._shutter_idx > 0:
                self._shutter_idx -= 1
                return self._make_result("set_shutter", current_brightness,
                    f"快门降档 {self._shutter_values[self._shutter_idx]}")
            elif not too_dark and self._shutter_idx < len(self._shutter_values) - 1:
                self._shutter_idx += 1
                return self._make_result("set_shutter", current_brightness,
                    f"快门升档 {self._shutter_values[self._shutter_idx]}")
            # 快门到极限 → fall through to iris

        # === 优先级2: 光圈 ===
        if not self._iris_frozen:
            # 振荡检测（仅当快门已冻结后生效）
            if self._shutter_frozen and self._cross_count >= 2:
                self._iris_frozen = True
                self._iris_idx = self._best_iris_idx
                self._cross_count = 0
                self._last_side = 0
                self._best_brightness = None
                # fall through to gain
            elif too_dark and self._iris_idx > 0:
                self._iris_idx -= 1
                return self._make_result("set_iris", current_brightness,
                    f"光圈开大 F{int(self._iris_values[self._iris_idx])/100:.1f}")
            elif not too_dark and self._iris_idx < len(self._iris_values) - 1:
                self._iris_idx += 1
                return self._make_result("set_iris", current_brightness,
                    f"光圈收小 F{int(self._iris_values[self._iris_idx])/100:.1f}")
            # 光圈到极限 → fall through to gain

        # === 优先级3: 增益 ===
        # v8.70: 增益震荡检测 - 只在精调阶段（步长=1）检测
        if self._gain_phase == 2:
            current_side = 1 if current_brightness > self._target else -1
            if self._gain_last_side != 0 and current_side != self._gain_last_side:
                self._gain_osc_count += 1
                if self._gain_osc_count >= 3:
                    # 震荡3次，回滚到最佳增益
                    self._gain = self._best_gain_val
                    return self._make_stop_result("done", current_brightness,
                        f"增益震荡{self._gain_osc_count}次，回滚最佳增益{self._gain}")
            self._gain_last_side = current_side

        # 更新最佳增益（最接近目标的亮度）
        if self._best_brightness is None or abs(current_brightness - self._target) < abs(self._best_brightness - self._target):
            self._best_brightness = current_brightness
            self._best_gain_val = self._gain

        gain_step = 5 if self._gain_phase == 1 else 1
        direction = 1 if too_dark else -1
        new_gain = self._gain + gain_step * direction
        new_gain = max(self._gain_min, min(self._gain_max, new_gain))

        # 增益到极限
        if new_gain == self._gain:
            if self._gain_phase == 1:
                # 粗调到极限 → 切换精调
                self._gain_phase = 2
                gain_step = 1
                new_gain = self._gain + gain_step * direction
                new_gain = max(self._gain_min, min(self._gain_max, new_gain))
                if new_gain == self._gain:
                    # v8.68: target=0/100碰到极限 = 成功完成
                    if self._target == 0 or self._target == 100:
                        return self._make_stop_result("done", current_brightness,
                            f"目标极限，亮度={current_brightness:.1f}")
                    reason = "亮度不足" if too_dark else "亮度超出"
                    return self._make_stop_result(reason, current_brightness,
                        f"{reason}(全部参数到极限)")
            else:
                # v8.68: target=0/100碰到极限 = 成功完成
                if self._target == 0 or self._target == 100:
                    return self._make_stop_result("done", current_brightness,
                        f"目标极限，亮度={current_brightness:.1f}")
                reason = "亮度不足" if too_dark else "亮度超出"
                return self._make_stop_result(reason, current_brightness,
                    f"{reason}(全部参数到极限)")

        # 过冲检测：方向反转 → 切换精调
        if self._gain_phase == 1 and self._gain_last_direction != 0:
            if direction != self._gain_last_direction:
                self._gain_phase = 2

        self._gain_last_direction = direction
        self._gain = new_gain
        phase_name = "粗调" if self._gain_phase == 1 else "精调"
        return self._make_result("set_gain", current_brightness,
            f"增益{phase_name} {self._gain}")

    def _make_result(self, action: str, brightness: float, message: str) -> dict:
        return {
            "action": action,
            "step": self._step_count,
            "brightness": round(brightness, 1),
            "target": self._target,
            "shutter": self._shutter_values[self._shutter_idx],
            "iris": self._iris_values[self._iris_idx],
            "gain": self._gain,
            "gain_phase": self._gain_phase,
            "message": message
        }

    def _make_stop_result(self, reason: str, brightness: float, message: str) -> dict:
        return {
            "action": "stop",
            "reason": reason,
            "step": self._step_count,
            "brightness": round(brightness, 1),
            "target": self._target,
            "shutter": self._shutter_values[self._shutter_idx],
            "iris": self._iris_values[self._iris_idx],
            "gain": self._gain,
            "steps": self._step_count,
            "message": message
        }


class BrightnessSearcher(SearcherBase):
    """亮度搜索执行器

    复用白平衡模式：
    - 每步：1读(截图) + 1写(设参数)
    - 等待：calc_stable_delay()
    - 中断：_interrupt()
    """

    def __init__(self, mgr, device_ip, client, x, y, w, h, capture_func,
                 cleanup_func, target, shutter_idx, iris_idx, gain,
                 shutter_values, iris_values, gain_min=0, gain_max=100,
                 mac_clean=""):
        super().__init__(mgr, device_ip, client, x, y, w, h, capture_func, cleanup_func, mac_clean)
        self.search_type = "Brightness"
        self._target = target
        self._shutter_idx = shutter_idx
        self._iris_idx = iris_idx
        self._gain = gain
        self._shutter_values = shutter_values
        self._iris_values = iris_values
        self._gain_min = gain_min
        self._gain_max = gain_max

    def _set_shutter(self, level: str):
        xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Shutter version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
<ShutterLevel>{level}</ShutterLevel>
</Shutter>'''
        self.client.put("/Image/channels/1/Shutter", xml)

    def _set_iris(self, level: str):
        xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Iris version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
<IrisLevel>{level}</IrisLevel>
</Iris>'''
        self.client.put("/Image/channels/1/Iris", xml)

    def _set_gain(self, level: int, gain_limit: int = None):
        xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Gain version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
<GainLevel>{level}</GainLevel>
{'<GainLimit>' + str(gain_limit) + '</GainLimit>' if gain_limit is not None else ''}
</Gain>'''
        self.client.put("/Image/channels/1/gain", xml)

    def _set_exposure_manual(self):
        xml = '''<?xml version="1.0" encoding="UTF-8"?>
<Exposure version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
<ExposureType>manual</ExposureType>
</Exposure>'''
        self.client.put("/Image/channels/1/exposure", xml)

    async def run(self):
        """运行亮度搜索，产生SSE事件"""

        # 读取快门延迟
        self._stable_delay = await asyncio.to_thread(calc_stable_delay, self.client)

        # 1. 切换手动曝光模式
        await asyncio.to_thread(self._set_exposure_manual)

        # 2. 初始截图
        bgr, info = await asyncio.to_thread(self._capture)
        if bgr is None:
            err_msg = (info or {}).get('error', '截图失败')
            yield f"data: {json.dumps({'type': 'error', 'message': err_msg})}\n\n"
            return

        initial_brightness = calc_brightness(bgr) * 100.0 / 255.0

        crop_msg = f"X={info['crop_x1']}~{info['crop_x2']}, Y={info['crop_y1']}~{info['crop_y2']}, 共{info['pixels']}像素"
        yield f"data: {json.dumps({'type': 'start', 'crop': crop_msg,
                                    'initial_brightness': round(initial_brightness, 1),
                                    'target': self._target})}\n\n"

        # 3. 创建迭代器
        ib = IterativeBrightness(
            self._target, self._shutter_idx, self._iris_idx, self._gain,
            self._shutter_values, self._iris_values, self._gain_min, self._gain_max
        )

        # 4. 迭代循环
        while True:
            if self._interrupted:
                cur_b = calc_brightness(bgr) * 100.0 / 255.0
                yield f"data: {json.dumps({'type': 'interrupt', 'message': '用户停止',
                                            'shutter': self._shutter_values[ib._shutter_idx],
                                            'iris': f"F{int(self._iris_values[ib._iris_idx])/100:.1f}",
                                            'gain': ib._gain,
                                            'brightness': round(cur_b, 1)})}\n\n"
                break

            cur_b = calc_brightness(bgr) * 100.0 / 255.0
            cmd = ib.step(cur_b)

            # SSE事件
            event = {
                "type": "brightness",
                "step": cmd.get("step", 0),
                "action": cmd["action"],
                "brightness": cmd["brightness"],
                "target": cmd["target"],
                "shutter": cmd["shutter"],
                "iris": f"F{int(cmd['iris'])/100:.1f}",
                "gain": cmd["gain"],
                "gain_phase": cmd.get("gain_phase", 0),
                "message": cmd["message"]
            }
            yield f"data: {json.dumps(event)}\n\n"

            if cmd["action"] == "stop":
                yield f"data: {json.dumps({'type': 'done',
                                            'final_brightness': cmd['brightness'],
                                            'target': self._target,
                                            'shutter': cmd['shutter'],
                                            'iris': f"F{int(cmd['iris'])/100:.1f}",
                                            'gain': cmd['gain'],
                                            'total_steps': cmd['steps'],
                                            'reason': cmd['reason']})}\n\n"
                
                # v8.73: 存储基线
                from src.controlpanel.region_base import write_search_baseline
                write_search_baseline(self._mac_clean, 'brightness', {
                    'brightness': cmd['brightness'],
                    'shutter': cmd['shutter'],
                    'iris': cmd['iris'],
                    'gain': cmd['gain']
                })
                
                break

            # 应用参数（1写）
            if cmd["action"] == "set_shutter":
                await asyncio.to_thread(self._set_shutter, cmd["shutter"])
            elif cmd["action"] == "set_iris":
                await asyncio.to_thread(self._set_iris, cmd["iris"])
            elif cmd["action"] == "set_gain":
                await asyncio.to_thread(self._set_gain, cmd["gain"])

            # 等待稳定
            await asyncio.sleep(self._stable_delay)

            # 重新截图（1读）
            bgr, info2 = await asyncio.to_thread(self._capture)
            if bgr is None:
                err_msg = (info2 or {}).get('error', '截图失败')
                yield f"data: {json.dumps({'type': 'error', 'message': err_msg})}\n\n"
                break

        # 5. 清理
        await asyncio.to_thread(self._cleanup_func, "Brightness", self.device_ip)
        yield f"data: {json.dumps({'type': 'cleanup'})}\n\n"
