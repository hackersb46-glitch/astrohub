"""AstroHub v8.70 - 白平衡模块

模块功能:
- IterativeWB: 动态步长算法(delta>10→5步, 1-10→2步, <1→1步)
- WhiteBalanceSearcher: 执行层(截图、设置参数、验证、SSE事件)

v8.70 变更:
- 移除固定阶段(coarse/medium/fine),改为动态步长
- 移除固定步数限制,改为震荡3次停止
- 步长:delta>10→5, 1<delta<=10→2, delta<=1→1
- 震荡检测:step=1时,连续3次无改善→回滚最佳值并停止
"""

import json
import asyncio
from .region_base import _rgb_stats, calc_stable_delay, SearcherBase


# ==================================================================================================
# 算法层:纯迭代搜索
# ==================================================================================================

class IterativeWB:
    """白平衡迭代搜索器 - 动态步长算法

    步长规则:
    - delta > 10 → step=5
    - 1 < delta <= 10 → step=2
    - delta <= 1 → step=1

    无固定步数限制。step=1时启用震荡检测:
    连续3次无改善(delta不下降)→ 回滚到最佳值并停止。

    输入:BGR图像
    输出:dict,含 action, red_gain, blue_gain, delta, message等。
    """

    def __init__(self, current_red=100, current_blue=100):
        self._current_red = current_red
        self._current_blue = current_blue

        # 全局追踪最佳
        self._best_red = current_red
        self._best_blue = current_blue
        self._best_delta = 999.0
        self._best_step = 0

        # 震荡检测(step=1时生效)
        self._no_improve_count = 0  # 连续无改善次数

        self._step_count = 0

    def _eval(self, r_sum, g_sum, b_sum, red, blue) -> float:
        """评估RGB平衡度"""
        if g_sum < 1: g_sum = 1
        ar = max(1, r_sum) * red / max(1, self._current_red)
        ab = max(1, b_sum) * blue / max(1, self._current_blue)
        return abs(ar / g_sum - 1.0) + abs(ab / g_sum - 1.0)

    def _get_step_size(self, delta: float) -> int:
        """根据delta动态确定步长"""
        if delta > 10:
            return 5
        elif delta > 1:
            return 2
        else:
            return 1

    def step(self, bgr) -> dict:
        """输入BGR图像,返回下一步操作"""
        stats = _rgb_stats(bgr)
        n = stats["n"]
        r_sum, g_sum, b_sum = stats["r_sum"], stats["g_sum"], stats["b_sum"]

        self._step_count += 1

        # 计算当前delta
        actual = abs(r_sum / max(1, g_sum) - 1.0) + abs(b_sum / max(1, g_sum) - 1.0)

        # 动态步长
        step = self._get_step_size(actual)

        # 更新全局best
        if actual < self._best_delta:
            self._best_delta = actual
            self._best_red = self._current_red
            self._best_blue = self._current_blue
            self._best_step = self._step_count
            self._no_improve_count = 0  # 有改善,重置计数
        else:
            # 无改善,增加计数(仅step=1时检测)
            if step == 1:
                self._no_improve_count += 1

        # 震荡检测:step=1时,连续3次无改善→停止
        if step == 1 and self._no_improve_count >= 3:
            rollback = (self._best_red != self._current_red or self._best_blue != self._current_blue)
            return {
                "action": "stop",
                "stage": "done",
                "step_size": 0,
                "red_gain": self._best_red, "blue_gain": self._best_blue,
                "r_avg": round(stats["r_avg"], 1), "g_avg": round(stats["g_avg"], 1), "b_avg": round(stats["b_avg"], 1),
                "delta": round(self._best_delta, 4), "best_delta": round(self._best_delta, 4), "pixels": n,
                "message": f"白平衡完成{'(回滚最佳)' if rollback else ''} 第{self._best_step}步"
            }

        # 计算候选值
        cr = self._current_red + max(-step, min(step, int(g_sum / max(1, r_sum) * self._current_red) - self._current_red))
        cb = self._current_blue + max(-step, min(step, int(g_sum / max(1, b_sum) * self._current_blue) - self._current_blue))
        cr = max(1, min(255, cr))
        cb = max(1, min(255, cb))

        # 生成候选列表
        # step=1时,分别调整R和B(独立)
        # step>1时,同时调整R和B(both)
        if step == 1:
            candidates = [(cr, self._current_blue, "red"), (self._current_red, cb, "blue")]
        else:
            candidates = [(cr, cb, "both"), (cr, self._current_blue, "red"), (self._current_red, cb, "blue")]

        # 选择最优候选
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

        # 应用新值
        self._current_red = new_red
        self._current_blue = new_blue

        stage_msg = f"step={step}"
        return {
            "action": "continue",
            "stage": stage_msg,
            "step_size": step,
            "red_gain": new_red, "blue_gain": new_blue,
            "r_avg": round(stats["r_avg"], 1), "g_avg": round(stats["g_avg"], 1), "b_avg": round(stats["b_avg"], 1),
            "delta": round(actual, 4), "best_delta": round(self._best_delta, 4), "pixels": n,
            "message": f"{direction} (±{step})"
        }


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

                yield f"data: {json.dumps({'type': 'done', 'final_red': cmd['red_gain'], 'final_blue': cmd['blue_gain'], 'best_delta': round(cmd.get('best_delta', 0), 4), 'verified_delta': round(verified_delta, 4), 'total_steps': step_count, 'message': '切换锁定白平衡'})}\n\n"
                
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
