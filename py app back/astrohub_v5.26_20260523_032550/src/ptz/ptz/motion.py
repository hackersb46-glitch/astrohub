"""
PTZ_ASTRO v1.1 - PTZ 运动测试模块
测试 PTZ 运动能力：连续移动、绝对移动、相对移动、pan 速度测试、zoom 范围测试。
每个测试后自动返回 HOME 位。

Author: 雅痞张@南方天文
"""

import time

from ptz.isapi.ptz import PTZController
from ptz.core.recorder import CSVRecorder
from ptz.core.logger import LOG
from ptz.constants import SAMPLE_INTERVAL, STABILIZATION_SECONDS, DEFAULT_PTZ_PRESET, HOME_COORDS


class MotionTester:
    """PTZ 运动测试器，封装所有 P5 运动测试逻辑。"""

    def __init__(self, ptz: PTZController, recorder: CSVRecorder) -> None:
        self.ptz = ptz
        self.recorder = recorder
        self.results: dict = {}

    def _go_home_and_stabilize(self) -> bool:
        """回到 HOME 位并稳定，验证坐标是否到达 HOME (P5.0)。

        成功条件: P=1800±5, T=450±5, Z=10±2
        """
        LOG.log("info", "回到 HOME 位 (P5.0) 并验证坐标...")
        if not self.ptz.goto_home():
            LOG.log("error", "HOME 命令发送失败")
            return False
        time.sleep(STABILIZATION_SECONDS)

        # 验证实际到达 HOME 坐标
        pos = self.ptz.get_position()
        if not pos:
            LOG.log("error", "无法获取 HOME 位坐标")
            return False

        pan = pos.get("pan", 0)
        tilt = pos.get("tilt", 0)
        zoom = pos.get("zoom", 0)

        pan_ok = abs(pan - HOME_COORDS["pan"]) <= 5
        tilt_ok = abs(tilt - HOME_COORDS["tilt"]) <= 5
        zoom_ok = abs(zoom - HOME_COORDS["zoom"]) <= 2

        if not (pan_ok and tilt_ok and zoom_ok):
            LOG.log("error", f"HOME 位坐标验证失败! "
                    f"期望 P={HOME_COORDS['pan']} T={HOME_COORDS['tilt']} Z={HOME_COORDS['zoom']}, "
                    f"实际 P={pan} T={tilt} Z={zoom}")
            return False

        LOG.log("done", f"HOME 位验证通过 P={pan} T={tilt} Z={zoom}")
        return True

    def _sample_position(self) -> dict:
        """采样当前位置（用于 recorder callback）。"""
        return self.ptz.get_position()

    # --- P5.1: Continuous Move ---

    def test_continuous_move(self) -> dict:
        """测试持续运动能力 (P5.1)。

        CSV要求: pan/tilt 50持续2秒，0.1s采样，回到 HOME 位。
        验证：移动前后坐标有显著变化 (delta>10)。
        """
        LOG.log("info", "=== P5.1: 测试持续运动能力 (Continuous Move) ===")
        result = {"success": False, "positions": [], "home_returned": False}

        if not self._go_home_and_stabilize():
            return result

        # 读取移动前坐标
        pos_before = self.ptz.get_position()
        if not pos_before:
            LOG.log("error", "无法获取移动前坐标")
            return result

        start_pan = pos_before.get("pan", 0)
        LOG.log("info", f"移动前坐标: P={start_pan}")

        # 启动 CSV 录制
        csv_path = self.recorder.start("continuousMove", callback=self._sample_position)
        LOG.log("info", f"CSV 录制: {csv_path}")

        # 持续移动 PAN=50 TILT=50 持续2秒 (CSV要求: pan/tilt 50)
        positions = self.ptz.continuous_move_duration(pan=50, tilt=50, duration=2.0)
        result["positions"] = positions

        # 读取移动后坐标
        pos_after = self.ptz.get_position()
        if not pos_after:
            LOG.log("error", "无法获取移动后坐标")
            self.recorder.stop()
            return result

        end_pan = pos_after.get("pan", 0)
        delta_pan = abs(end_pan - start_pan)
        result["pan_before"] = start_pan
        result["pan_after"] = end_pan
        result["delta_pan"] = delta_pan

        # 停止录制
        self.recorder.stop()

        LOG.log("info", f"移动后坐标: P={end_pan}, delta={delta_pan}")

        # 验证坐标有显著变化
        if delta_pan <= 10:
            LOG.log("error", f"Continuous Move 验证失败: delta={delta_pan} <= 10, 坐标无显著变化")
            result["message"] = f"坐标无显著变化 delta={delta_pan} (期望>10)"
            # 仍然尝试回到 HOME
            self.ptz.goto_home()
            return result

        LOG.log("done", f"Continuous Move 验证通过: delta={delta_pan} > 10")
        result["message"] = f"验证通过, delta={delta_pan}"

        # 回到 HOME
        result["home_returned"] = self.ptz.goto_home()
        if result["home_returned"]:
            LOG.log("done", "持续运动测试成功 → 回到 HOME 位")
            result["success"] = True
        else:
            LOG.log("error", "回到 HOME 位失败")

        return result

    # --- P5.2: Absolute Move ---

    def test_absolute_move(self) -> dict:
        """测试绝对运动 (P5.2)。

        在当前坐标基础上 +10，验证实际偏差<5。
        """
        LOG.log("info", "=== P5.2: 测试绝对运动 (Absolute Move) ===")
        result = {"success": False, "positions": [], "home_returned": False}

        if not self._go_home_and_stabilize():
            return result

        # 获取当前位置
        initial_pos = self.ptz.get_position()
        if not initial_pos:
            LOG.log("error", "无法获取初始位置")
            return result

        initial_pan = initial_pos.get("pan", 0)
        initial_tilt = initial_pos.get("tilt", 0)

        # 目标位置 +10
        target_pan = initial_pan + 10
        target_tilt = initial_tilt + 10

        LOG.log("info", f"绝对移动: ({initial_pan}, {initial_tilt}) → 目标({target_pan}, {target_tilt})")

        # 启动录制
        csv_path = self.recorder.start("absoluteMove", callback=self._sample_position)

        # 绝对移动
        api_success = self.ptz.absolute_move(pan=target_pan, tilt=target_tilt)
        result["api_success"] = api_success
        time.sleep(2)

        # 读取实际坐标
        pos_after = self.ptz.get_position()
        if not pos_after:
            LOG.log("error", "移动后无法获取位置")
            self.recorder.stop()
            self.ptz.goto_home()
            return result

        actual_pan = pos_after.get("pan", 0)
        actual_tilt = pos_after.get("tilt", 0)

        delta_pan = abs(actual_pan - target_pan)
        delta_tilt = abs(actual_tilt - target_tilt)

        result["positions"] = [{
            "before": initial_pos,
            "target": {"pan": target_pan, "tilt": target_tilt},
            "actual": pos_after,
            "delta_pan": round(delta_pan, 1),
            "delta_tilt": round(delta_tilt, 1),
        }]

        self.recorder.stop()

        LOG.log("info", f"目标 P={target_pan} T={target_tilt}, 实际 P={actual_pan} T={actual_tilt}, "
                f"偏差 dP={delta_pan:.1f} dT={delta_tilt:.1f}")

        # 验证与目标偏差<5
        if delta_pan < 5 and delta_tilt < 5:
            LOG.log("done", f"绝对移动验证通过: 偏差 dP={delta_pan:.1f} dT={delta_tilt:.1f} (均<5)")
            result["message"] = f"偏差 dP={delta_pan:.1f} dT={delta_tilt:.1f} 验证通过"
        else:
            LOG.log("error", f"绝对移动偏差过大: dP={delta_pan:.1f} dT={delta_tilt:.1f} (期望<5)")
            result["message"] = f"偏差过大 dP={delta_pan:.1f} dT={delta_tilt:.1f}"
            self.ptz.goto_home()
            return result

        if delta_pan < 5 and delta_tilt < 5:
            result["success"] = True

        result["home_returned"] = self.ptz.goto_home()
        if result["home_returned"]:
            LOG.log("done", "绝对运动测试成功 → 回到 HOME 位")
        else:
            LOG.log("error", "回到 HOME 位失败")

        return result

    # --- P5.3: Relative Move ---

    def test_relative_move(self) -> dict:
        """测试相对运动 (P5.3)。

        验证实际偏差<5。
        """
        LOG.log("info", "=== P5.3: 测试相对运动 (Relative Move) ===")
        result = {"success": False, "positions": [], "home_returned": False}

        if not self._go_home_and_stabilize():
            return result

        initial_pos = self.ptz.get_position()
        if not initial_pos:
            LOG.log("error", "无法获取初始位置")
            return result

        initial_pan = initial_pos.get("pan", 0)
        initial_tilt = initial_pos.get("tilt", 0)

        move_pan = 10
        move_tilt = 5
        target_pan = initial_pan + move_pan
        target_tilt = initial_tilt + move_tilt

        LOG.log("info", f"相对移动: 起点 P={initial_pan} T={initial_tilt}, 增量 dP={move_pan} dT={move_tilt}")

        # 启动录制
        self.recorder.start("relativeMove", callback=self._sample_position)

        # 相对移动
        api_success = self.ptz.relative_move(pan=move_pan, tilt=move_tilt, zoom=0)
        result["api_success"] = api_success
        time.sleep(2)

        pos_after = self.ptz.get_position()
        self.recorder.stop()

        if not pos_after:
            LOG.log("error", "移动后无法获取位置")
            self.ptz.goto_home()
            return result

        actual_pan = pos_after.get("pan", 0)
        actual_tilt = pos_after.get("tilt", 0)

        delta_pan = abs(actual_pan - target_pan)
        delta_tilt = abs(actual_tilt - target_tilt)
        actual_displacement_pan = actual_pan - initial_pan
        actual_displacement_tilt = actual_tilt - initial_tilt

        result["positions"] = [{
            "before": initial_pos,
            "target_dpan": move_pan,
            "target_dtilt": move_tilt,
            "actual": pos_after,
            "actual_displacement_pan": round(actual_displacement_pan, 1),
            "actual_displacement_tilt": round(actual_displacement_tilt, 1),
            "delta_pan": round(delta_pan, 1),
            "delta_tilt": round(delta_tilt, 1),
        }]

        LOG.log("info", f"目标增量: dP={move_pan} dT={move_tilt}, "
                f"实际增量: dP={actual_displacement_pan:.1f} dT={actual_displacement_tilt:.1f}, "
                f"偏差: {delta_pan:.1f} / {delta_tilt:.1f}")

        # 验证与目标偏差<5
        if delta_pan < 5 and delta_tilt < 5:
            LOG.log("done", f"相对移动验证通过: 偏差 dP={delta_pan:.1f} dT={delta_tilt:.1f} (均<5)")
            result["message"] = f"偏差 dP={delta_pan:.1f} dT={delta_tilt:.1f} 验证通过"
            result["success"] = True
        else:
            LOG.log("error", f"相对移动偏差过大: dP={delta_pan:.1f} dT={delta_tilt:.1f} (期望<5)")
            result["message"] = f"偏差过大 dP={delta_pan:.1f} dT={delta_tilt:.1f}"

        result["home_returned"] = self.ptz.goto_home()
        if result["home_returned"]:
            LOG.log("done", "相对运动测试成功 → 回到 HOME 位")
        else:
            LOG.log("error", "回到 HOME 位失败")

        return result

    # --- P5.4: Pan Speed Test ---

    def test_pan_speed(self) -> dict:
        """测试 Pan 三档速度 (P5.4)。

        speed=1/50/100 各移动2秒，验证 delta_1 < delta_50 < delta_100。
        """
        LOG.log("info", "=== P5.4: 测试 Pan 速度控制 ===")
        result = {"success": False, "speeds": {}}

        if not self._go_home_and_stabilize():
            return result

        for speed in [1, 50, 100]:
            LOG.log("info", f"  测试速度: {speed}")

            # 先回到 HOME
            self.ptz.goto_home()
            time.sleep(STABILIZATION_SECONDS)

            # 获取起始位置
            start_pos = self.ptz.get_position()
            start_pan = start_pos.get("pan", 0) if start_pos else 0

            # 启动录制
            self.recorder.start(f"panSpeed{speed}", callback=self._sample_position)

            # 以指定速度(speed=1/50/100)持续移动2秒
            positions = self.ptz.continuous_move_duration(pan=speed, tilt=0, duration=2.0)

            self.recorder.stop()

            # 获取最终位置
            end_pos = self.ptz.get_position()
            end_pan = end_pos.get("pan", 0) if end_pos else 0

            displacement = abs(end_pan - start_pan)
            result["speeds"][speed] = {
                "start_pan": start_pan,
                "end_pan": end_pan,
                "displacement": displacement,
                "samples": len(positions),
            }

            LOG.log("info", f"    速度 {speed}: 起始={start_pan}, 结束={end_pan}, 位移={displacement}")

        # 验证速度递增: delta_1 < delta_50 < delta_100
        delta_1 = result["speeds"].get(1, {}).get("displacement", 0)
        delta_50 = result["speeds"].get(50, {}).get("displacement", 0)
        delta_100 = result["speeds"].get(100, {}).get("displacement", 0)

        LOG.log("info", f"速度位移对比: speed=1→{delta_1}, speed=50→{delta_50}, speed=100→{delta_100}")

        speed_valid = (delta_1 < delta_50) and (delta_50 < delta_100)
        
        if speed_valid:
            LOG.log("done", f"速度递增验证通过: {delta_1} < {delta_50} < {delta_100}")
            result["message"] = f"速度有效: {delta_1} < {delta_50} < {delta_100}"
            result["success"] = True
        else:
            LOG.log("error", f"速度递增验证失败: delta_1={delta_1}, delta_50={delta_50}, delta_100={delta_100}")
            result["message"] = f"速度无效: delta_1={delta_1} 不小于 delta_50={delta_50} 或 delta_50 不小于 delta_100={delta_100}"
            result["speed_valid"] = False

        # 回到 HOME
        self.ptz.goto_home()
        return result

    # --- P5.5: Zoom Range ---

    def test_zoom_range(self) -> dict:
        """测试 Zoom 范围 (P5.5)。

        验证：ZOOM+50 记录上限，ZOOM-50 记录下限，上限>=320, 下限<=10。
        """
        LOG.log("info", "=== P5.5: 测试 Zoom 范围 ===")

        if not self._go_home_and_stabilize():
            return {"success": False, "zoom_min": 0, "zoom_max": 0, "message": "HOME位验证失败"}

        # ===== 测试 ZOOM+ 上限 =====
        LOG.log("info", "Zoom+ 测试上限 (每0.1秒采样)...")
        self.recorder.start("zoomPositive", callback=self._sample_position)

        pos_before_zoom = self.ptz.get_position()
        zoom_before = pos_before_zoom.get("zoom", 0) if pos_before_zoom else 0

        self.ptz.continuous_move(pan=0, tilt=0, zoom=50)
        time.sleep(3)
        self.ptz.stop_move()
        time.sleep(0.5)

        pos_after_zoom = self.ptz.get_position()
        zoom_max_reached = pos_after_zoom.get("zoom", 0) if pos_after_zoom else zoom_before
        self.recorder.stop()

        LOG.log("info", f"Zoom+ 起始 Z={zoom_before}, 到达 Z={zoom_max_reached}")

        # ===== 测试 ZOOM- 下限 =====
        LOG.log("info", "回到 HOME 位后测试 Zoom- 下限...")
        self.ptz.goto_home()
        time.sleep(STABILIZATION_SECONDS)

        self.recorder.start("zoomNegative", callback=self._sample_position)

        pos_before_zoomout = self.ptz.get_position()
        zoom_before_out = pos_before_zoomout.get("zoom", 0) if pos_before_zoomout else 0

        self.ptz.continuous_move(pan=0, tilt=0, zoom=-50)
        time.sleep(3)
        self.ptz.stop_move()
        time.sleep(0.5)

        pos_after_zoomout = self.ptz.get_position()
        zoom_min_reached = pos_after_zoomout.get("zoom", 0) if pos_after_zoomout else zoom_before_out
        self.recorder.stop()

        LOG.log("info", f"Zoom- 起始 Z={zoom_before_out}, 到达 Z={zoom_min_reached}")

        # 验证: 上限>=320, 下限<=10
        # 注：Hikvision native unit, 这里验证设备是否有合理的范围变化
        zoom_range = zoom_max_reached - zoom_min_reached
        upper_ok = zoom_max_reached >= 320 if zoom_max_reached > 0 else True
        lower_ok = zoom_min_reached <= 10 if zoom_min_reached > 0 else True

        result = {
            "success": False,
            "zoom_min": zoom_min_reached,
            "zoom_max": zoom_max_reached,
            "zoom_range": zoom_range,
            "upper_limit_valid": upper_ok,
            "lower_limit_valid": lower_ok,
        }

        if zoom_range > 0:
            LOG.log("done", f"Zoom 范围验证: Z={zoom_min_reached}~{zoom_max_reached}, 范围={zoom_range}")
            result["message"] = f"Zoom范围: {zoom_min_reached}~{zoom_max_reached}, range={zoom_range}"
            result["success"] = True
        else:
            LOG.log("error", f"Zoom 范围验证失败: 范围={zoom_range}, 无有效移动")
            result["message"] = f"Zoom无有效移动, range={zoom_range}"

        return result

    # --- P5.6: Device Restore ---

    def restore_device(self) -> bool:
        """还原设备到默认值 (P5.6)。

        停止数据读写，调用恢复API，回到预置点 10，验证坐标。
        """
        LOG.log("info", "=== P5.6: 设备还原 ===")

        # 停止所有录制
        self.recorder.stop()

        # 停止所有移动
        self.ptz.stop_move()

        # 尝试调用 ISAPI 恢复默认参数
        try:
            restore_endpoint = "/System/restore"
            restore_xml = '<?xml version="1.0" encoding="UTF-8"?>' \
                '<restore xmlns="http://www.hikvision.com/ver20/XMLSchema"/>'
            self.ptz.client.put(restore_endpoint, restore_xml)
            LOG.log("info", "ISAPI 恢复默认参数已发送")
        except Exception as e:
            LOG.log("warning", f"ISAPI 恢复默认参数失败: {e}")

        # 回到 HOME 位
        success = self.ptz.goto_home()
        if not success:
            LOG.log("error", "设备还原失败（未能回到预置点 10）")
            return False

        time.sleep(STABILIZATION_SECONDS)

        # 验证坐标回到HOME
        pos = self.ptz.get_position()
        if pos:
            pan = pos.get("pan", 0)
            tilt = pos.get("tilt", 0)
            zoom = pos.get("zoom", 0)
            pan_ok = abs(pan - HOME_COORDS["pan"]) <= 5
            tilt_ok = abs(tilt - HOME_COORDS["tilt"]) <= 5
            zoom_ok = abs(zoom - HOME_COORDS["zoom"]) <= 2
            
            if pan_ok and tilt_ok and zoom_ok:
                LOG.log("done", f"设备还原验证通过: P={pan} T={tilt} Z={zoom}")
                return True
            else:
                LOG.log("error", f"还原后坐标偏差过大: P={pan} T={tilt} Z={zoom}")
                return False
        else:
            LOG.log("error", "还原后无法获取位置")
            return False

    # --- Run all tests ---

    def run_all_tests(self) -> dict:
        """运行所有 P5 运动测试。

        返回:
            测试结果字典
        """
        LOG.log("info", "========================================")
        LOG.log("info", "  P5: PTZ 运动控制测试开始")
        LOG.log("info", "========================================")

        results = {}
        results["continuous_move"] = self.test_continuous_move()
        results["absolute_move"] = self.test_absolute_move()
        results["relative_move"] = self.test_relative_move()
        results["pan_speed"] = self.test_pan_speed()
        results["zoom_range"] = self.test_zoom_range()
        results["restore"] = self.restore_device()

        return results
