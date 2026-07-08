"""AstroHub v8.37 - 白平衡模块

包含：
- IterativeWB: 纯算法迭代搜索
- WhiteBalanceSearcher: 执行层（截图、设置增益、验证、SSE事件）
"""

import json
import asyncio
from .region_base import _rgb_stats


# ─────────────────────────────────────────────
# 纯算法层：迭代搜索
# ─────────────────────────────────────────────

class IterativeWB:
    """白平衡迭代搜索器 - R/B 独立调整
    
    状态：粗调(±5) → 中调(±2) → 精调(±1)
    每步评估 [双通道, 仅R, 仅B] 三个候选，选 delta 最小。
    全程追踪 best_gains + best_delta，结束时回滚到最佳。
    
    输入：BGR图像
    输出：dict（action, red_gain, blue_gain, delta, message等）
    
    不涉及任何设备操作，纯粹数学逻辑。
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
        self._best_red = current_red
        self._best_blue = current_blue
        self._best_delta = 999.0
        self._best_step = 0
        self._step_count = 0

    def _eval(self, r_sum, g_sum, b_sum, red, blue) -> float:
        """评估RGB平衡程度"""
        if g_sum < 1: g_sum = 1
        ar = max(1, r_sum) * red / max(1, self._current_red)
        ab = max(1, b_sum) * blue / max(1, self._current_blue)
        return abs(ar / g_sum - 1.0) + abs(ab / g_sum - 1.0)

    def step(self, bgr) -> dict:
        """输入BGR图像，返回下一步动作"""
        stats = _rgb_stats(bgr)
        n = stats["n"]
        r_sum, g_sum, b_sum = stats["r_sum"], stats["g_sum"], stats["b_sum"]

        self._step_count += 1
        self._stage_step_count += 1
        step = self._stage_steps[self._stage]

        # 计算候选增益
        cr = self._current_red + max(-step, min(step, int(g_sum / max(1, r_sum) * self._current_red) - self._current_red))
        cb = self._current_blue + max(-step, min(step, int(g_sum / max(1, b_sum) * self._current_blue) - self._current_blue))
        cr = max(1, min(255, cr))
        cb = max(1, min(255, cb))

        # 候选列表 (- stage 2: R/B独立调整)
        if self._stage == 2:
            # 精调阶段：全部R/B独立，无"both"候选
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

        # 计算当前delta
        actual = abs(r_sum / max(1, g_sum) - 1.0) + abs(b_sum / max(1, g_sum) - 1.0)

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
            # 进入精调时重置best追踪，避免粗调阶段的best覆盖精调结果
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

        # 精调阶段处理
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


# ─────────────────────────────────────────────
# 执行层：协调设备操作
# ─────────────────────────────────────────────

class WhiteBalanceSearcher:
    """白平衡搜索执行器
    
    负责：
    - 切换手动白平衡模式
    - 读取当前增益
    - 截取框选区域
    - 调用IterativeWB.step()
    - 应用增益到设备
    - 切换锁定白平衡模式
    - 验证结果
    - 产生SSE事件
    
    不做任何算法决策，只执行。
    """
    
    def __init__(self, mgr, device_ip, client, x, y, w, h, capture_func, cleanup_func):
        self.mgr = mgr
        self.device_ip = device_ip
        self.client = client
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self._capture_func = capture_func
        self._cleanup_func = cleanup_func
        self._interrupted = False  # v8.41: 中断标志
    
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
    
    def _read_current_gains(self):
        """读取当前白平衡增益"""
        try:
            resp = self.client.get("/Image/channels/1/whiteBalance")
            if resp.status_code == 200:
                # 解析XML
                import xml.etree.ElementTree as ET
                root = ET.fromstring(resp.xml)
                red, blue = 100, 100
                for elem in root.iter():
                    tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
                    if tag in ("WhiteBalanceRed", "whiteBalanceRed"):
                        red = int(elem.text)
                    elif tag in ("WhiteBalanceBlue", "whiteBalanceBlue"):
                        blue = int(elem.text)
                return red, blue
        except:
            pass
        return 100, 100
    
    def _capture(self):
        """截取框选区域"""
        bgr, crop_path, info = self._capture_func(
            self.client, self.mgr, self.device_ip, "WB",
            self.x, self.y, self.w, self.h
        )
        return bgr, info
    
    def _interrupt(self):
        """v8.41: 中断白平衡搜索"""
        self._interrupted = True
    
    async def run(self):
        """运行白平衡搜索，产生SSE事件"""
        
        # 1. 切换手动白平衡模式
        ok = await asyncio.to_thread(self._set_wb_mode, "manual")
        if not ok:
            yield f"data: {json.dumps({'type': 'warning', 'message': '切换手动白平衡失败'})}\n\n"
        
        # 2. 读取当前增益
        current_red, current_blue = await asyncio.to_thread(self._read_current_gains)
        
        # 3. 初始截图
        bgr, info = await asyncio.to_thread(self._capture)
        if bgr is None:
            yield f"data: {json.dumps({'type': 'error', 'message': '截图失败'})}\n\n"
            return
        
        crop_msg = f"X={info['crop_x1']}~{info['crop_x2']}, Y={info['crop_y1']}~{info['crop_y2']}, 共{info['pixels']}像素"
        yield f"data: {json.dumps({'type': 'start', 'crop': crop_msg, 'initial_red': current_red, 'initial_blue': current_blue})}\n\n"
        
        # 4. 白平衡循环
        wb = IterativeWB(current_red, current_blue)
        step_count = 0
        
        while True:
            # v8.41: 检查中断
            if self._interrupted:
                # 写入best值并锁定
                await asyncio.to_thread(self._set_wb_gains, self._best_red, self._best_blue)
                await asyncio.sleep(0.3)
                await asyncio.to_thread(self._set_wb_mode, "locked")
                
                yield f"data: {json.dumps({
                    'type': 'interrupt',
                    'message': '用户停止',
                    'final_red': self._best_red,
                    'final_blue': self._best_blue
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
            
            # 停止？
            if cmd["action"] == "stop":
                # 应用最终增益
                await asyncio.to_thread(self._set_wb_gains, cmd["red_gain"], cmd["blue_gain"])
                await asyncio.sleep(0.3)
                
                # 验证
                bgr2, _ = await asyncio.to_thread(self._capture)
                verified_delta = cmd.get("best_delta", cmd.get("delta", 0))
                
                if bgr2 is not None:
                    stats = _rgb_stats(bgr2)
                    r_sum, g_sum, b_sum = stats["r_sum"], stats["g_sum"], stats["b_sum"]
                    verified_delta = abs(r_sum / max(1, g_sum) - 1.0) + abs(b_sum / max(1, g_sum) - 1.0)
                
                # 切换锁定白平衡模式
                await asyncio.to_thread(self._set_wb_mode, "locked")
                
                yield f"data: {json.dumps({'type': 'done', 'final_red': cmd['red_gain'], 'final_blue': cmd['blue_gain'], 'best_delta': round(cmd.get('best_delta', 0), 4), 'verified_delta': round(verified_delta, 4), 'total_steps': step_count, 'message': '切换锁定白平衡'})}\n\n"
                break
            
            # 应用增益
            await asyncio.to_thread(self._set_wb_gains, cmd["red_gain"], cmd["blue_gain"])
            await asyncio.sleep(0.3)  # 等待稳定
            
            # 重新截图
            bgr, _ = await asyncio.to_thread(self._capture)
            if bgr is None:
                yield f"data: {json.dumps({'type': 'error', 'message': '截图失败'})}\n\n"
                break
        
        # 5. 清理
        await asyncio.to_thread(self._cleanup_func, "WB", self.device_ip)
        yield f"data: {json.dumps({'type': 'cleanup'})}\n\n"