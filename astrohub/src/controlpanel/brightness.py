"""AstroHub v8.76 - 局部亮度控制模块（方向感知）

算法：
- IterativeBrightness: 方向感知迭代搜索器
- BrightnessSearcher: 执行层（截图、设置参数、验证、SSE事件）

亮度计算：
- Y = 0.299R + 0.587G + 0.114B（标准亮度）
- 排除死黑死白 → 取有效像素Y均值 → 映射0-100

调整逻辑（v8.76 方向感知）：
- 暗→亮（target > current）：快门→光圈→增益
- 亮→暗（target < current）：增益→快门→光圈
- 每参数震荡2次后冻结，进入下一参数
- 最终参数振荡3次后回滚最优值

增益精调：
- 仅当增益为最终参数（暗→亮）时启用2阶段（±5粗调→±1精调）
"""

import json
import asyncio
from .region_base import calc_brightness, calc_stable_delay, SearcherBase


class IterativeBrightness:
    """亮度迭代搜索器 - 方向感知

    暗→亮: shutter(阶段0) → iris(阶段1) → gain(阶段2, 粗→精)
    亮→暗: gain(阶段0) → shutter(阶段1) → iris(阶段2, 逼近)

    每阶段：震荡2次 → 冻结 → 下一阶段
    最终阶段震荡3次 → 回滚最优值完成
    """

    def __init__(self, target: float, shutter_idx: int, iris_idx: int,
                 gain: int, shutter_values: list, iris_values: list,
                 gain_min: int = 0, gain_max: int = 100,
                 brighten: bool = True):
        self._target = target
        self._shutter_values = shutter_values
        self._iris_values = iris_values
        self._gain_min = gain_min
        self._gain_max = gain_max
        self._tolerance = 0.5

        # 方向感知参数顺序
        self._brighten = brighten
        if brighten:
            self._order = ['shutter', 'iris', 'gain']
        else:
            self._order = ['gain', 'shutter', 'iris']
        self._stage = 0  # 当前阶段 0/1/2

        # 当前参数值
        self._cur = {
            'shutter': shutter_idx,
            'iris': iris_idx,
            'gain': gain
        }
        self._frozen = [False, False, False]
        self._osc_cnt = [0, 0, 0]
        self._last_side = 0
        self._best_val = {
            'shutter': shutter_idx,
            'iris': iris_idx,
            'gain': gain
        }
        self._best_bri = [None, None, None]

        # 增益2阶段（仅暗→亮时增益在阶段2才启用）
        self._gain_phase = 1 if brighten else 2
        self._gain_last_dir = 0

        self._step_count = 0

    def step(self, current_brightness: float) -> dict:
        """输入当前亮度(0-100)，返回下一步动作"""
        self._step_count += 1
        error = self._target - current_brightness
        too_dark = error > 0

        # 容差内 → 完成
        if abs(error) <= self._tolerance:
            return self._stop("done", current_brightness,
                              f"亮度达标 {current_brightness:.1f}≈{self._target}")

        s = self._stage
        param = self._order[s]

        # 振荡检测：方向穿越
        current_side = 1 if current_brightness > self._target else -1
        if self._last_side != 0 and current_side != self._last_side:
            self._osc_cnt[s] += 1
        self._last_side = current_side

        # 追踪最佳值
        if (self._best_bri[s] is None or
                abs(error) < abs(self._target - self._best_bri[s])):
            self._best_bri[s] = current_brightness
            self._best_val[param] = self._cur[param]

        # === 阶段推进：震荡2次 → 冻结 ===
        if self._osc_cnt[s] >= 2 and s < 2:
            self._cur[param] = self._best_val[param]
            self._frozen[s] = True
            self._stage += 1
            s = self._stage
            param = self._order[s]
            self._osc_cnt[s] = 0
            self._last_side = 0
            self._best_bri[s] = None

        # === 最终阶段(2) ===
        if s == 2:
            # 增益震荡3次 → 回滚完成
            if param == 'gain' and self._gain_phase == 2 and self._osc_cnt[2] >= 3:
                self._cur['gain'] = self._best_val['gain']
                return self._stop("done", current_brightness,
                                  f"增益震荡{self._osc_cnt[2]}次，回滚最佳增益{self._best_val['gain']}")

            # 增益调整（粗→精调）
            if param == 'gain':
                return self._adjust_gain(current_brightness, too_dark)

            # 非增益最终参数（亮→暗时阶段2=光圈）
            if param == 'iris':
                return self._adjust_iris_stage2(current_brightness, too_dark)

        # === 阶段0/1：通用参数调整 ===
        direction = 1 if too_dark else -1
        return self._adjust_param(param, current_brightness, direction)

    def _adjust_param(self, param: str, brightness: float, direction: int) -> dict:
        """通用参数调整（阶段0/1）
        
        direction: +1=需要更亮, -1=需要更暗
        快门/光圈: 索引+1=更暗(更快快门/更小光圈), 所以实际方向要取反
        增益: 索引+1=更亮, 方向不变
        """
        if param == 'shutter':
            # 快门: direction=+1(需更亮) → 索引减小(更慢快门=更亮)
            idx_change = -direction
            at_limit = (idx_change == -1 and self._cur['shutter'] <= 0) or \
                       (idx_change == 1 and self._cur['shutter'] >= len(self._shutter_values) - 1)
            if at_limit:
                return self._freeze_and_advance(brightness)
            self._cur['shutter'] += idx_change
            return self._result("set_shutter", brightness,
                                f"快门{'降' if idx_change > 0 else '升'}档 "
                                f"{self._shutter_values[self._cur['shutter']]}")

        elif param == 'iris':
            # 光圈: direction=+1(需更亮) → 索引减小(更小F值=更大光圈=更亮)
            idx_change = -direction
            at_limit = (idx_change == -1 and self._cur['iris'] <= 0) or \
                       (idx_change == 1 and self._cur['iris'] >= len(self._iris_values) - 1)
            if at_limit:
                return self._freeze_and_advance(brightness)
            self._cur['iris'] += idx_change
            return self._result("set_iris", brightness,
                                f"光圈{'收小' if idx_change > 0 else '开大'} "
                                f"F{int(self._iris_values[self._cur['iris']])/100:.1f}")

        else:  # gain (阶段0/1，无粗精调)
            at_limit = (direction == -1 and self._cur['gain'] <= self._gain_min) or \
                       (direction == 1 and self._cur['gain'] >= self._gain_max)
            if at_limit:
                return self._freeze_and_advance(brightness)
            self._cur['gain'] += direction
            phase = "粗调" if self._gain_phase == 1 else "精调"
            return self._result("set_gain", brightness,
                                f"增益{phase} {self._cur['gain']}",
                                gain_phase=self._gain_phase)

    def _adjust_gain(self, brightness: float, too_dark: bool) -> dict:
        """增益调整（阶段2，粗调→精调）"""
        gain_step = 5 if self._gain_phase == 1 else 1
        direction = 1 if too_dark else -1
        new_gain = self._cur['gain'] + gain_step * direction
        new_gain = max(self._gain_min, min(self._gain_max, new_gain))

        if new_gain == self._cur['gain']:
            # 增益到极限
            if self._gain_phase == 1:
                # 粗调→精调
                self._gain_phase = 2
                gain_step = 1
                new_gain = self._cur['gain'] + gain_step * direction
                new_gain = max(self._gain_min, min(self._gain_max, new_gain))
                if new_gain == self._cur['gain']:
                    if self._target in (0, 100):
                        return self._stop("done", brightness,
                                          f"目标极限，亮度={brightness:.1f}")
                    reason = "亮度不足" if too_dark else "亮度超出"
                    return self._stop(reason, brightness, f"{reason}(全部参数到极限)")
            else:
                if self._target in (0, 100):
                    return self._stop("done", brightness,
                                      f"目标极限，亮度={brightness:.1f}")
                reason = "亮度不足" if too_dark else "亮度超出"
                return self._stop(reason, brightness, f"{reason}(全部参数到极限)")

        # 过冲检测：方向反转 → 切精调
        if self._gain_phase == 1 and self._gain_last_dir != 0:
            if direction != self._gain_last_dir:
                self._gain_phase = 2

        self._gain_last_dir = direction
        self._cur['gain'] = new_gain
        phase = "粗调" if self._gain_phase == 1 else "精调"
        return self._result("set_gain", brightness,
                            f"增益{phase} {self._cur['gain']}",
                            gain_phase=self._gain_phase)

    def _adjust_iris_stage2(self, brightness: float, too_dark: bool) -> dict:
        """光圈调整（阶段2，亮→暗最终参数）"""
        direction = 1 if too_dark else -1
        val = self._cur['iris']

        at_limit = (direction == -1 and val <= 0) or \
                   (direction == 1 and val >= len(self._iris_values) - 1)

        if at_limit:
            if self._target in (0, 100):
                return self._stop("done", brightness,
                                  f"目标极限，亮度={brightness:.1f}")
            reason = "亮度不足" if too_dark else "亮度超出"
            return self._stop(reason, brightness, f"{reason}(全部参数到极限)")

        self._cur['iris'] = val + direction
        act = "光圈收小" if direction == 1 else "光圈开大"
        return self._result("set_iris", brightness,
                            f"{act} F{int(self._iris_values[val + direction])/100:.1f}")

    def _freeze_and_advance(self, brightness: float) -> dict:
        """当前参数到极限 → 冻结，进入下一阶段"""
        self._frozen[self._stage] = True
        self._stage += 1

        if self._stage >= 3:
            too_dark = self._target > brightness
            reason = "亮度不足" if too_dark else "亮度超出"
            return self._stop(reason, brightness, f"{reason}(全部参数到极限)")

        s = self._stage
        param = self._order[s]
        self._osc_cnt[s] = 0
        self._last_side = 0
        self._best_bri[s] = None

        # 继续执行下一阶段
        direction = 1 if (self._target > brightness) else -1
        return self._adjust_param(param, brightness, direction)

    def _result(self, action: str, brightness: float, message: str,
                gain_phase: int = 0) -> dict:
        return {
            "action": action,
            "step": self._step_count,
            "brightness": round(brightness, 1),
            "target": self._target,
            "shutter": self._shutter_values[self._cur['shutter']],
            "iris": self._iris_values[self._cur['iris']],
            "gain": self._cur['gain'],
            "gain_phase": gain_phase,
            "message": message
        }

    def _stop(self, reason: str, brightness: float, message: str) -> dict:
        return {
            "action": "stop",
            "reason": reason,
            "step": self._step_count,
            "brightness": round(brightness, 1),
            "target": self._target,
            "shutter": self._shutter_values[self._cur['shutter']],
            "iris": self._iris_values[self._cur['iris']],
            "gain": self._cur['gain'],
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

        # v8.76: 根据初始亮度与目标判断方向
        brighten = self._target >= initial_brightness

        crop_msg = f"X={info['crop_x1']}~{info['crop_x2']}, Y={info['crop_y1']}~{info['crop_y2']}, 共{info['pixels']}像素"
        yield f"data: {json.dumps({'type': 'start', 'crop': crop_msg,
                                    'initial_brightness': round(initial_brightness, 1),
                                    'target': self._target,
                                    'direction': 'brighten' if brighten else 'darken'})}\n\n"

        # 3. 创建迭代器（v8.76: 传入方向）
        ib = IterativeBrightness(
            self._target, self._shutter_idx, self._iris_idx, self._gain,
            self._shutter_values, self._iris_values, self._gain_min, self._gain_max,
            brighten=brighten
        )

        # 4. 迭代循环
        while True:
            if self._interrupted:
                cur_b = calc_brightness(bgr) * 100.0 / 255.0
                yield f"data: {json.dumps({'type': 'interrupt', 'message': '用户停止',
                                            'shutter': self._shutter_values[ib._cur['shutter']],
                                            'iris': f"F{int(self._iris_values[ib._cur['iris']])/100:.1f}",
                                            'gain': ib._cur['gain'],
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
