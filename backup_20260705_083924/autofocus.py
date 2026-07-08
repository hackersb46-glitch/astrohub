"""AstroHub v8.37 - 反差对焦模块（简化版）

包含：
- ContrastAF: 纯算法状态机
- FocusSearcher: 执行层（截图、移动、验证、SSE事件）
"""

import json
import asyncio
import numpy as np
from .region_base import calc_contrast


class ContrastAF:
    """反差对焦 - 状态机
    
    状态：COARSE → RETURN → APPROACH → DONE/FAILED
    
    精调阶段无步数限制，直到达到峰值。
    """
    
    COARSE = "coarse"
    RETURN = "return"
    APPROACH = "approach"
    DONE = "done"
    FAILED = "failed"
    
    def __init__(self):
        self._state = self.COARSE
        self._attempt = 0
        self._direction = -1
        
        # 粗调数据
        self._points = []
        self._best1_value = 0.0
        self._best1_pos = 0
        self._decline_count = 0
        self._decline_after_best = 0
        self._step_count = 0
        
        # 回退
        self._return_needed = 0
        self._return_done = 0
        
        # 精调（无步数限制）
        self._best2_value = 0.0
        self._overshoot = 0
        self._approach_step = 0
        self._fine_direction = 1
        
        # 最终
        self._best3_value = 0.0
        
        # 平坦区域追踪
        self._flat_reversed = False  # 是否已因平坦反向过
    
    def step(self, contrast: float) -> dict:
        if self._state == self.COARSE:
            return self._step_coarse(contrast)
        elif self._state == self.RETURN:
            return self._step_return(contrast)
        elif self._state == self.APPROACH:
            return self._step_approach(contrast)
        elif self._state == self.DONE:
            return {"action": "stop", "stage": "done", "message": "对焦成功", "best3": self._best3_value}
        else:
            return {"action": "stop", "stage": "error", "message": "对焦失败"}
    
    def _step_coarse(self, contrast):
        """粗调阶段（0.2s/步）"""
        pos = len(self._points)
        self._points.append((pos, contrast))
        self._step_count += 1
        
        # 更新best1
        is_new_best = False
        if contrast > self._best1_value:
            self._best1_value = contrast
            self._best1_pos = pos
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
                "stage": "coarse", "contrast": round(contrast, 2),
                "message": f"开始对焦(方向={dir_name},尝试{self._attempt+1}/3)"
            }
        
        # ── 进入精确对焦 ──
        # 条件: best1>100 + 下降≥3步
        if self._decline_after_best >= 3 and self._best1_value > 100:
            self._state = self.RETURN
            self._return_needed = len(self._points) - self._best1_pos - 1
            self._return_done = 0
            return {
                "action": action, "duration": 0.2,
                "stage": "coarse", "contrast": round(contrast, 2),
                "message": f"找到峰值(best1={self._best1_value:.1f}),回退{self._return_needed}步"
            }
        
        # ── 反向: 连续5步下降 ──
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
                "stage": "coarse", "contrast": round(contrast, 2),
                "message": f"反向(方向={dir_name},尝试{self._attempt+1}/3)"
            }
        
        # ── 平坦区域: 20步无变化 → 反向; 反向也平坦 → 加长到0.5s ──
        if self._step_count >= 20 and self._check_flat():
            if not self._flat_reversed:
                # 第一次平坦 → 反向
                self._flat_reversed = True
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
                    "stage": "coarse", "contrast": round(contrast, 2),
                    "message": f"平坦区({self._step_count}步),反向(方向={dir_name})"
                }
            else:
                # 反向后仍平坦 → 用0.5s步长
                return {
                    "action": action, "duration": 0.5,
                    "stage": "coarse", "contrast": round(contrast, 2),
                    "message": f"平坦区持续,加速({self._step_count}步,best={self._best1_value:.1f})"
                }
        
        # ── R²检测: R²≥80% 且 best1≤100 → 失败 ──
        if self._step_count % 5 == 0:
            r2 = self._calc_r2()
            if r2 is not None and r2 >= 0.8 and self._best1_value <= 100:
                if not self._do_retry():
                    self._state = self.FAILED
                    return {
                        "action": "stop", "duration": 0,
                        "stage": "error", "contrast": round(contrast, 2),
                        "message": f"对焦失败(R²={r2:.2f},best={self._best1_value:.1f}<=100)"
                    }
                action = "focus_near" if self._direction < 0 else "focus_far"
                return {
                    "action": action, "duration": 0.2,
                    "stage": "coarse", "contrast": round(contrast, 2),
                    "message": f"峰值过低,反向(尝试{self._attempt+1}/3)"
                }
        
        # ── 粗调超时（仅粗调阶段）──
        if self._step_count >= 90:
            self._state = self.FAILED
            return {
                "action": "stop", "duration": 0,
                "stage": "error", "contrast": round(contrast, 2),
                "message": f"粗调超时({self._step_count}步)"
            }
        
        # 继续采样
        return {
            "action": action, "duration": 0.2,
            "stage": "coarse", "contrast": round(contrast, 2),
            "message": f"采样(best={self._best1_value:.1f},方向={dir_name})"
        }
    
    def _step_return(self, contrast):
        """回退阶段"""
        self._return_done += 1
        
        rev_dir = -self._direction
        action = "focus_near" if rev_dir < 0 else "focus_far"
        
        # 进入精调
        self._state = self.APPROACH
        self._best2_value = contrast
        self._overshoot = 0
        self._approach_step = 0
        self._fine_direction = -self._direction  # 精调方向与扫描方向相反
        return {
            "action": "focus_near" if self._fine_direction < 0 else "focus_far",
            "duration": 0.05,
            "stage": "approach", "contrast": round(contrast, 2),
            "message": f"回退完成(反差={contrast:.1f},目标={self._best1_value:.1f}),进入精调"
        }
    
    def _step_approach(self, contrast):
        """精调阶段（无步数限制，越过best立即反向，无限逼近）"""
        self._approach_step += 1
        
        # 更新best2和best3
        if contrast > self._best2_value:
            self._best2_value = contrast
        if contrast > self._best3_value:
            self._best3_value = contrast
        
        # best2 >= best1 → 成功
        if self._best2_value >= self._best1_value:
            self._state = self.DONE
            return {
                "action": "stop", "duration": 0,
                "stage": "done", "contrast": round(self._best2_value, 2),
                "message": f"对焦成功(best2={self._best2_value:.1f}>=best1={self._best1_value:.1f})",
                "best3": self._best3_value
            }
        
        # 越过best → 立即反向（反差从峰值下降1步即反向）
        if contrast < self._best2_value:
            self._fine_direction = -self._fine_direction
            action = "focus_near" if self._fine_direction < 0 else "focus_far"
            return {
                "action": action, "duration": 0.05,
                "stage": "approach", "contrast": round(contrast, 2),
                "message": f"越过best反向(步{self._approach_step},best2={self._best2_value:.1f},目标={self._best1_value:.1f})"
            }
        
        # 继续逼近
        action = "focus_near" if self._fine_direction < 0 else "focus_far"
        return {
            "action": action, "duration": 0.05,
            "stage": "approach", "contrast": round(contrast, 2),
            "message": f"逼近(步{self._approach_step},best2={self._best2_value:.1f},目标={self._best1_value:.1f})"
        }
    
    def _check_flat(self):
        """检查平坦区域"""
        if len(self._points) < 5:
            return False
        recent = [p[1] for p in self._points[-5:]]
        max_v, min_v = max(recent), min(recent)
        if max_v <= 0:
            return False
        return (max_v - min_v) / max_v < 0.10
    
    def _calc_r2(self):
        """计算R²"""
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
        except:
            return None
    
    def _do_retry(self):
        """执行重试"""
        self._attempt += 1
        if self._attempt >= 3:
            return False
        self._direction *= -1
        self._points = []
        self._best1_value = 0.0
        self._best1_pos = 0
        self._decline_count = 0
        self._decline_after_best = 0
        self._step_count = 0
        return True


class FocusSearcher:
    """对焦搜索执行器"""
    
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
    
    def _interrupt(self):
        """v8.41: 中断对焦搜索"""
        self._interrupted = True
    
    def _set_manual_focus(self):
        """设置手动对焦模式"""
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
        except:
            pass
        return False
    
    def _capture(self):
        """截取框选区域"""
        bgr, crop_path, info = self._capture_func(
            self.client, self.mgr, self.device_ip, "Focus",
            self.x, self.y, self.w, self.h
        )
        return bgr, info
    
    def _move_focus(self, direction: str, duration: float):
        """移动焦点"""
        ptz_dir = "focus-far" if direction == "focus_far" else "focus-near"
        self.mgr.ptz_move(self.device_ip, direction=ptz_dir, speed=60)
    
    def _stop_focus(self):
        """停止焦点移动"""
        self.mgr.ptz_stop(self.device_ip)
    
    async def run(self):
        """运行对焦搜索，产生SSE事件"""
        
        # 1. 设置手动对焦
        ok = await asyncio.to_thread(self._set_manual_focus)
        if not ok:
            yield f"data: {json.dumps({'type': 'warning', 'message': '设置手动对焦失败'})}\n\n"
        
        # 2. 初始截图
        bgr, info = await asyncio.to_thread(self._capture)
        if bgr is None:
            yield f"data: {json.dumps({'type': 'error', 'message': '截图失败'})}\n\n"
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
                yield f"data: {json.dumps({
                    'type': 'interrupt',
                    'message': '用户停止'
                })}\n\n"
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
                best3 = cmd.get("best3", cmd["contrast"])
                verified = final_contrast >= best3 * 0.95
                
                yield f"data: {json.dumps({'type': 'done', 'final_contrast': round(final_contrast, 2), 'best_contrast': round(best3, 2), 'total_steps': step_count, 'verified': verified})}\n\n"
                break
            
            # 移动
            await asyncio.to_thread(self._move_focus, cmd["action"], cmd["duration"])
            await asyncio.sleep(cmd["duration"])
            await asyncio.to_thread(self._stop_focus)
            await asyncio.sleep(0.3)  # 等待稳定
            
            # 重新截图
            bgr, _ = await asyncio.to_thread(self._capture)
            if bgr is None:
                yield f"data: {json.dumps({'type': 'error', 'message': '截图失败'})}\n\n"
                break
        
        # 4. 清理
        await asyncio.to_thread(self._cleanup_func, "Focus", self.device_ip)
        yield f"data: {json.dumps({'type': 'cleanup'})}\n\n"
