"""AstroHub v8.77 - 白平衡模块

模块功能:
- IterativeWB: 三阶段迭代算法(BOTH→RED→BLUE→交叉)
- WhiteBalanceSearcher: 执行层(截图、设置参数、验证、SSE事件)

v8.77 变更:
- 三阶段状态机: BOTH→RED→BLUE→交叉检查
- 独立追踪 r_dev=|R/G-1| 和 b_dev=|B/G-1|
- 震荡处理: 3次无改善→回滚最佳→换通道
- 收敛阈值: r_dev≤0.1 且 b_dev≤0.1
- 最大交叉轮次: 3轮
"""

import json
import asyncio
from .region_base import _rgb_stats, calc_stable_delay, SearcherBase


# ==================================================================================================
# 算法层:纯迭代搜索
# ==================================================================================================

class IterativeWB:
    """白平衡迭代搜索器 - 三阶段迭代算法

    阶段:
    1. BOTH: R和B同时调,动态步长
    2. RED: 只调R,step=1
    3. BLUE: 只调B,step=1
    震荡→回滚最佳→换通道→交叉检查
    停止: r_dev≤0.1 且 b_dev≤0.1 且 无改善,或超过最大轮次

    输入:BGR图像
    输出:dict,含 action, red_gain, blue_gain, phase, r_dev, b_dev等。
    """

    DELTA_LIMIT = 0.1       # 收敛阈值
    OSC_LIMIT = 3           # 震荡阈值(3次无改善)
    MAX_CROSS = 3           # 最大交叉轮次

    def __init__(self, current_red=100, current_blue=100):
        self._current_red = current_red
        self._current_blue = current_blue

        # 各通道独立best追踪
        self._best_red = current_red
        self._best_blue = current_blue
        self._best_delta = 999.0
        self._best_step = 0

        # 阶段状态
        self._phase = "both"  # both / red / blue
        self._no_improve_count = 0
        self._cross_round = 0

        self._step_count = 0

    def _get_step_size(self, delta: float) -> int:
        """BOTH阶段根据delta动态确定步长"""
        if delta > 1:
            return 5
        elif delta > 0.3:
            return 2
        else:
            return 1

    def _calc_target(self, current: int, ch_sum: float, g_sum: float, step: int) -> int:
        """计算目标增益,限制步长"""
        if ch_sum < 1:
            ch_sum = 1
        target = int(g_sum / ch_sum * current)
        diff = target - current
        return current + max(-step, min(step, diff))

    def step(self, bgr) -> dict:
        """输入BGR图像,返回下一步操作"""
        stats = _rgb_stats(bgr)
        n = stats["n"]
        r_sum, g_sum, b_sum = stats["r_sum"], stats["g_sum"], stats["b_sum"]
        g_safe = max(1, g_sum)

        self._step_count += 1

        # ── 独立指标 ──
        r_dev = abs(r_sum / g_safe - 1.0)
        b_dev = abs(b_sum / g_safe - 1.0)
        delta = r_dev + b_dev

        # ── 更新best ──
        if delta < self._best_delta:
            self._best_delta = delta
            self._best_red = self._current_red
            self._best_blue = self._current_blue
            self._best_step = self._step_count
            self._no_improve_count = 0
        else:
            self._no_improve_count += 1

        # ── 收敛检查 ──
        if r_dev <= self.DELTA_LIMIT and b_dev <= self.DELTA_LIMIT:
            if self._no_improve_count >= 2:
                return {
                    "action": "stop", "stage": "converged",
                    "step_size": 0,
                    "red_gain": self._best_red, "blue_gain": self._best_blue,
                    "r_avg": round(stats["r_avg"], 1), "g_avg": round(stats["g_avg"], 1), "b_avg": round(stats["b_avg"], 1),
                    "delta": round(delta, 4), "best_delta": round(self._best_delta, 4),
                    "r_dev": round(r_dev, 4), "b_dev": round(b_dev, 4),
                    "phase": self._phase, "cross_round": self._cross_round, "pixels": n,
                    "message": f"收敛 R/G={r_dev:.3f} B/G={b_dev:.3f}"
                }

        # ── 阶段转换: 震荡处理 ──
        if self._no_improve_count >= self.OSC_LIMIT:
            transition = self._phase_transition(r_sum, g_sum, b_sum)
            if transition is not None:
                # 回滚到best后重新计算指标
                self._current_red = self._best_red
                self._current_blue = self._best_blue
                self._no_improve_count = 0
                return transition

            # _phase_transition返回None=真正停止
            return {
                "action": "stop", "stage": "max_cross",
                "step_size": 0,
                "red_gain": self._best_red, "blue_gain": self._best_blue,
                "r_avg": round(stats["r_avg"], 1), "g_avg": round(stats["g_avg"], 1), "b_avg": round(stats["b_avg"], 1),
                "delta": round(delta, 4), "best_delta": round(self._best_delta, 4),
                "r_dev": round(r_dev, 4), "b_dev": round(b_dev, 4),
                "phase": self._phase, "cross_round": self._cross_round, "pixels": n,
                "message": f"交叉{self._cross_round}轮未收敛"
            }

        # ── 计算调整(按阶段) ──
        if self._phase == "both":
            step = self._get_step_size(delta)
            new_red = self._calc_target(self._current_red, r_sum, g_sum, step)
            new_blue = self._calc_target(self._current_blue, b_sum, g_sum, step)
            direction = f"both(±{step})"
        elif self._phase == "red":
            step = 1
            new_red = self._calc_target(self._current_red, r_sum, g_sum, step)
            new_blue = self._current_blue  # 固定B
            direction = f"red(±{step})"
        else:  # blue
            step = 1
            new_red = self._current_red  # 固定R
            new_blue = self._calc_target(self._current_blue, b_sum, g_sum, step)
            direction = f"blue(±{step})"

        new_red = max(1, min(255, int(new_red)))
        new_blue = max(1, min(255, int(new_blue)))

        self._current_red = new_red
        self._current_blue = new_blue

        return {
            "action": "continue",
            "stage": f"{self._phase}",
            "step_size": step,
            "red_gain": new_red, "blue_gain": new_blue,
            "r_avg": round(stats["r_avg"], 1), "g_avg": round(stats["g_avg"], 1), "b_avg": round(stats["b_avg"], 1),
            "delta": round(delta, 4), "best_delta": round(self._best_delta, 4),
            "r_dev": round(r_dev, 4), "b_dev": round(b_dev, 4),
            "phase": self._phase, "cross_round": self._cross_round, "pixels": n,
            "message": direction
        }

    def _phase_transition(self, r_sum, g_sum, b_sum) -> dict | None:
        """震荡→回滚→换通道。
        返回过渡事件dict,或None表示应停止。"""
        g_safe = max(1, g_sum)
        r_dev = abs(r_sum / g_safe - 1.0)
        b_dev = abs(b_sum / g_safe - 1.0)

        if self._phase == "both":
            # BOTH震荡 → 进入偏差更大的单通道
            if r_dev >= b_dev:
                self._phase = "red"
            else:
                self._phase = "blue"
            return {
                "action": "continue", "stage": "transition",
                "step_size": 0,
                "red_gain": self._best_red, "blue_gain": self._best_blue,
                "r_avg": 0, "g_avg": 0, "b_avg": 0,
                "delta": round(r_dev + b_dev, 4), "best_delta": round(self._best_delta, 4),
                "r_dev": round(r_dev, 4), "b_dev": round(b_dev, 4),
                "phase": self._phase, "cross_round": self._cross_round, "pixels": 0,
                "message": f"BOTH震荡→{self._phase}"
            }
        elif self._phase == "red":
            # RED震荡 → 进入BLUE
            self._phase = "blue"
            self._cross_round += 1
            if self._cross_round > self.MAX_CROSS:
                return None  # 停止
            return {
                "action": "continue", "stage": "transition",
                "step_size": 0,
                "red_gain": self._best_red, "blue_gain": self._best_blue,
                "r_avg": 0, "g_avg": 0, "b_avg": 0,
                "delta": round(r_dev + b_dev, 4), "best_delta": round(self._best_delta, 4),
                "r_dev": round(r_dev, 4), "b_dev": round(b_dev, 4),
                "phase": self._phase, "cross_round": self._cross_round, "pixels": 0,
                "message": f"RED震荡→BLUE(轮次{self._cross_round})"
            }
        elif self._phase == "blue":
            # BLUE震荡 → 检查是否还需要继续
            if r_dev > self.DELTA_LIMIT:
                self._phase = "red"
                self._cross_round += 1
                if self._cross_round > self.MAX_CROSS:
                    return None
                return {
                    "action": "continue", "stage": "transition",
                    "step_size": 0,
                    "red_gain": self._best_red, "blue_gain": self._best_blue,
                    "r_avg": 0, "g_avg": 0, "b_avg": 0,
                    "delta": round(r_dev + b_dev, 4), "best_delta": round(self._best_delta, 4),
                    "r_dev": round(r_dev, 4), "b_dev": round(b_dev, 4),
                    "phase": self._phase, "cross_round": self._cross_round, "pixels": 0,
                    "message": f"BLUE震荡→RED(轮次{self._cross_round})"
                }
            else:
                return None  # R/G已收敛,停止


# ==================================================================================================
# 执行层:协调设备通信
# ==================================================================================================

class WhiteBalanceSearcher(SearcherBase):
    """白平衡搜索执行器

    职责:
    - 切换到手动白平衡模式
    - 读取当前增益
    - 获取选区截图
    - 调用IterativeWB.step()
    - 应用结果保存到设备
    - 切换回锁定白平衡模式
    - 验证结果
    - 发送SSE事件

    不包含任何算法逻辑,只负责执行。
    """

    def __init__(self, mgr, device_ip, client, x, y, w, h, capture_func, cleanup_func, mac_clean=""):
        super().__init__(mgr, device_ip, client, x, y, w, h, capture_func, cleanup_func, mac_clean)
        self.search_type = "WB"

    def _set_wb_mode(self, mode: str):
        """设置白平衡模式: manual/locked"""
        xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<WhiteBalance version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
<WhiteBalanceStyle>{mode}</WhiteBalanceStyle>
</WhiteBalance>'''
        resp = self.client.put("/Image/channels/1/whiteBalance", xml)
        return resp.status_code == 200

    def _set_wb_gains(self, red: int, blue: int):
        """设置白平衡增益"""
        xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<WhiteBalance version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
<WhiteBalanceStyle>manual</WhiteBalanceStyle>
<WhiteBalanceRed>{red}</WhiteBalanceRed>
<WhiteBalanceBlue>{blue}</WhiteBalanceBlue>
</WhiteBalance>'''
        resp = self.client.put("/Image/channels/1/whiteBalance", xml)
        return resp.status_code == 200

    def _read_wb_status(self):
        try:
            resp = self.client.get("/Image/channels/1/whiteBalance")
            if resp.status_code == 200:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(resp.xml)
                mode = "auto"
                red, blue = 100, 100
                for elem in root.iter():
                    tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
                    if tag in ("WhiteBalanceStyle", "whiteBalanceStyle"):
                        mode = (elem.text or "auto").lower()
                    elif tag in ("WhiteBalanceRed", "whiteBalanceRed"):
                        red = int(elem.text)
                    elif tag in ("WhiteBalanceBlue", "whiteBalanceBlue"):
                        blue = int(elem.text)
                return mode, red, blue
        except:
            pass
        return "auto", 100, 100

    async def run(self):
        """执行白平衡搜索,产生SSE事件"""

        # v8.64: 稳定延迟只计算一次
        self._stable_delay = await asyncio.to_thread(calc_stable_delay, self.client)

        # 1. 读取当前模式+增益(v8.62)
        current_mode, current_red, current_blue = await asyncio.to_thread(self._read_wb_status)

        # 2. 切换到手动白平衡模式
        ok = await asyncio.to_thread(self._set_wb_mode, "manual")
        if not ok:
            yield f"data: {json.dumps({'type': 'warning', 'message': '切换手动白平衡失败'})}\n\n"

        # 3. 初始值判断
        if current_mode == "auto":
            # 自动模式 → 从50/50起步,写入设备
            current_red, current_blue = 50, 50
            await asyncio.to_thread(self._set_wb_gains, 50, 50)
            yield f"data: {json.dumps({'type': 'info', 'message': '初始值: R=50, B=50'})}\n\n"
        else:
            # locked/manual 模式 → 从当前值开始(保留上次结果/手动设置)
            yield f"data: {json.dumps({'type': 'info', 'message': f'初始值: R={current_red}, B={current_blue}'})}\n\n"

        # 4. 首次截图(v8.62 恢复原逻辑)
        bgr, info = await asyncio.to_thread(self._capture)
        if bgr is None:
            err_msg = (info or {}).get('error', '截图失败')
            yield f"data: {json.dumps({'type': 'error', 'message': err_msg})}\n\n"
            return

        crop_msg = f"X={info['crop_x1']}~{info['crop_x2']}, Y={info['crop_y1']}~{info['crop_y2']}, 共{info['pixels']}像素"
        yield f"data: {json.dumps({'type': 'start', 'crop': crop_msg, 'initial_red': current_red, 'initial_blue': current_blue})}\n\n"

        # 4. 白平衡循环
        wb = IterativeWB(current_red, current_blue)
        step_count = 0

        while True:
            # v8.41: 检测中断
            if self._interrupted:
                # v8.62: 从 IterativeWB 实例获取 best 值
                best_red = wb._best_red
                best_blue = wb._best_blue
                # 写入best值到设备
                await asyncio.to_thread(self._set_wb_gains, best_red, best_blue)
                await asyncio.sleep(self._stable_delay)
                await asyncio.to_thread(self._set_wb_mode, "locked")

                yield f"data: {json.dumps({
                    'type': 'interrupt',
                    'message': '用户停止',
                    'final_red': best_red,
                    'final_blue': best_blue
                })}\n\n"
                break

            cmd = wb.step(bgr)
            step_count += 1

            # 发送步骤事件
            event = {
                "type": "wb",
                "step": step_count,
                "stage": cmd.get("stage", ""),
                "step_size": cmd.get("step_size", 0),
                "red_gain": cmd["red_gain"],
                "blue_gain": cmd["blue_gain"],
                "r_avg": cmd.get("r_avg", 0),
                "g_avg": cmd.get("g_avg", 0),
                "b_avg": cmd.get("b_avg", 0),
                "delta": cmd.get("delta", 0),
                "best_delta": cmd.get("best_delta", 0),
                "r_dev": cmd.get("r_dev", 0),
                "b_dev": cmd.get("b_dev", 0),
                "phase": cmd.get("phase", ""),
                "cross_round": cmd.get("cross_round", 0),
                "message": cmd["message"]
            }
            yield f"data: {json.dumps(event)}\n\n"

            # 停止判断
            if cmd["action"] == "stop":
                # 应用最佳结果到设备
                await asyncio.to_thread(self._set_wb_gains, cmd["red_gain"], cmd["blue_gain"])
                await asyncio.sleep(self._stable_delay)

                # 验证
                bgr2, _ = await asyncio.to_thread(self._capture)
                verified_delta = cmd.get("best_delta", cmd.get("delta", 0))

                if bgr2 is not None:
                    stats = _rgb_stats(bgr2)
                    r_sum, g_sum, b_sum = stats["r_sum"], stats["g_sum"], stats["b_sum"]
                    verified_delta = abs(r_sum / max(1, g_sum) - 1.0) + abs(b_sum / max(1, g_sum) - 1.0)

                # 切换回锁定白平衡模式
                await asyncio.to_thread(self._set_wb_mode, "locked")

                yield f"data: {json.dumps({'type': 'done', 'final_red': cmd['red_gain'], 'final_blue': cmd['blue_gain'], 'best_delta': round(cmd.get('best_delta', 0), 4), 'verified_delta': round(verified_delta, 4), 'total_steps': step_count, 'r_dev': cmd.get('r_dev', 0), 'b_dev': cmd.get('b_dev', 0), 'message': '切换锁定白平衡'})}\n\n"
                
                # v8.73: 存储基线
                from src.controlpanel.region_base import write_search_baseline
                write_search_baseline(self._mac_clean, 'whitebalance', {
                    'red': cmd['red_gain'],
                    'blue': cmd['blue_gain'],
                    'delta': round(cmd.get('best_delta', 0), 4)
                })
                
                break

            # 应用新增益
            await asyncio.to_thread(self._set_wb_gains, cmd["red_gain"], cmd["blue_gain"])
            await asyncio.sleep(self._stable_delay)  # 等待稳定

            # 重新截图
            bgr, info2 = await asyncio.to_thread(self._capture)
            if bgr is None:
                err_msg = (info2 or {}).get('error', '截图失败')
                yield f"data: {json.dumps({'type': 'error', 'message': err_msg})}\n\n"
                break

        # 5. 清理
        await asyncio.to_thread(self._cleanup_func, "WB", self.device_ip)
        yield f"data: {json.dumps({'type': 'cleanup'})}\n\n"
