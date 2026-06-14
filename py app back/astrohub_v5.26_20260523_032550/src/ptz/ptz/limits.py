"""
PTZ_ASTRO v1.1 - PTZ 限位测试模块
测试 P/T/Z 轴限位，包括跳变检测、翻转判断、稳定验证。

Author: 雅痞张@南方天文
"""

import time

from ptz.isapi.ptz import PTZController
from ptz.isapi.client import ISAPIClient
from ptz.core.recorder import CSVRecorder
from ptz.core.config import ConfigManager
from ptz.core.logger import LOG
from ptz.constants import (
    STABILIZATION_SECONDS,
    STABLE_POINTS_REQUIRED,
    STABLE_POINT_DEVIATION,
    SAMPLE_INTERVAL,
)


class LimitTester:
    """PTZ 限位测试器。"""

    def __init__(
        self,
        ptz: PTZController,
        recorder: CSVRecorder,
        client: ISAPIClient,
        config_manager: ConfigManager,
        device_mac: str,
    ) -> None:
        self.ptz = ptz
        self.recorder = recorder
        self.client = client
        self.config = config_manager
        self.device_mac = device_mac
        self.results: dict = {}
        self.supports_pan = True
        self.supports_tilt = True
        self.supports_zoom = True

    # --- P6.0: Axis support check ---

    def check_axis_support(self) -> dict:
        """判断设备是否支持 P/T/Z (P6.0)。

        通过 PTZ capabilities 端点或尝试获取状态来判断。
        """
        LOG.log("info", "=== P6.0: 判断 P/T/Z 轴支持情况 ===")

        result = {"pan": True, "tilt": True, "zoom": True}

        # 尝试获取 PTZ 状态，判断是否存在
        pos = self.ptz.get_position()
        if not pos:
            LOG.log("warning", "无法获取 PTZ 位置，所有轴标记为不支持")
            result = {"pan": False, "tilt": False, "zoom": False}
            self.supports_pan = False
            self.supports_tilt = False
            self.supports_zoom = False
            return result

        # 检查返回的字段是否存在
        self.supports_pan = "pan" in pos
        self.supports_tilt = "tilt" in pos
        self.supports_zoom = "zoom" in pos

        support_text = []
        if self.supports_pan:
            support_text.append("Pan ✓")
        else:
            support_text.append("Pan ✗")
        if self.supports_tilt:
            support_text.append("Tilt ✓")
        else:
            support_text.append("Tilt ✗")
        if self.supports_zoom:
            support_text.append("Zoom ✓")
        else:
            support_text.append("Zoom ✗")

        LOG.log("done", f"P/T/Z 支持: {', '.join(support_text)}")
        self.results["axis_support"] = result
        return result

    # --- P6.1: Stability check ---

    def _check_stability(self, duration: float = 2.0, tolerance: float = 0.0) -> bool:
        """检查当前位置是否稳定。

        参数:
            duration: 检测时长（秒）
            tolerance: 容差（允许的数值偏差）

        返回:
            True = 稳定（在持续期间内连续 STABLE_POINTS_REQUIRED 个点偏差不超过 tolerance）
        """
        LOG.log("info", f"稳定性检测: 持续 {duration} 秒，容差 {tolerance}")

        start = time.time()
        stable_count = 0
        last_pos = None

        while time.time() - start < duration:
            pos = self.ptz.get_position()
            if pos:
                if last_pos is not None:
                    pan_diff = abs(pos.get("pan", 0) - last_pos.get("pan", 0))
                    tilt_diff = abs(pos.get("tilt", 0) - last_pos.get("tilt", 0))
                    zoom_diff = abs(pos.get("zoom", 0) - last_pos.get("zoom", 0))

                    if pan_diff <= tolerance and tilt_diff <= tolerance and zoom_diff <= tolerance:
                        stable_count += 1
                        if stable_count >= STABLE_POINTS_REQUIRED:
                            LOG.log("done", "稳定性检测通过")
                            return True
                    else:
                        stable_count = 0
                last_pos = pos
            time.sleep(SAMPLE_INTERVAL)

        LOG.log("warning", f"稳定性检测未通过（仅稳定 {stable_count}/{STABLE_POINTS_REQUIRED} 点）")
        return False

    def _go_home_and_stabilize(self) -> bool:
        """回到 HOME 位并稳定。"""
        if not self.ptz.goto_home():
            LOG.log("error", "回到 HOME 位失败")
            return False
        time.sleep(STABILIZATION_SECONDS)

        if not self._check_stability():
            LOG.log("warning", "HOME 位稳定性不足，但仍继续")

        LOG.log("done", "HOME 位已稳定")
        return True

    # --- P6.2: Device identification ---

    def identify_device(self) -> dict | None:
        """通过 MAC 识别设备 (P6.2)。

        读取 config 中已保存设备列表，匹配 MAC。

        返回:
            设备信息字典，或 None
        """
        LOG.log("info", f"=== P6.2: 设备识别 (MAC={self.device_mac}) ===")

        device = self.config.get_device_by_mac(self.device_mac)

        if device:
            LOG.log("done", f"设备已识别: {device.get('model', 'Unknown')}")
            print(f"  设备: {device.get('model', 'Unknown')} | MAC={self.device_mac}")
        else:
            LOG.log("info", f"设备未识别: {self.device_mac} (将创建新条目)")
            print(f"  未识别设备: {self.device_mac}")

        return device

    # --- P6.3: Pan Limit ---

    def test_pan_limit(self) -> dict:
        """测试 Pan 轴限位 (P6.3)。

        方法:
        1. Gotohome 回到零位，稳定 2s
        2. PAN=50 持续运动，监测 P 轴数据
        3. 出现 3600→0 跳变 → 无限位
        4. 遇到 20 个连续点数值不变 → 有限位
        5. 反向 PAN=-50 测另一侧

        返回:
            {"has_limit": bool, "upper": ..., "lower": ..., "has_jump": bool}
        """
        LOG.log("info", "=== P6.3: Pan 轴限位测试 ===")
        result = {"has_limit": False, "upper": None, "lower": None, "has_jump": False}

        if not self.supports_pan:
            LOG.log("info", "设备不支持 Pan 轴，跳过")
            return result

        if not self._go_home_and_stabilize():
            return result

        # 正向测试 (PAN=50)
        LOG.log("info", "Pan 正向测试 (PAN=50)")
        self.recorder.start("panPositive", callback=lambda: self.ptz.get_position())

        jump_detected = False
        stable_count = 0
        last_pan = None
        pan_values = []

        self.ptz.continuous_move(pan=50, tilt=0, zoom=0)

        timeout = time.time() + 60  # 60 秒安全超时
        while time.time() < timeout:
            pos = self.ptz.get_position()
            if pos:
                curr_pan = pos.get("pan", 0)
                pan_values.append(curr_pan)

                # 检测 3600→0 跳变
                if last_pan is not None and last_pan > 3000 and curr_pan < 500:
                    jump_detected = True
                    LOG.log("info", f"  检测到 3600→0 跳变: {last_pan} → {curr_pan}")
                    break

                # 检测稳定（限位）
                if last_pan is not None and abs(curr_pan - last_pan) < 1:
                    stable_count += 1
                    if stable_count >= STABLE_POINTS_REQUIRED:
                        LOG.log("info", f"  检测到限位: 连续 {stable_count} 点停留在 {curr_pan}")
                        result["upper"] = curr_pan
                        result["has_limit"] = True
                        break
                else:
                    stable_count = 0

                last_pan = curr_pan
                self.recorder.write_row(curr_pan, pos.get("tilt", 0), pos.get("zoom", 0))

            time.sleep(SAMPLE_INTERVAL)

        # 停止
        self.ptz.stop_move()
        self.recorder.stop()

        if jump_detected:
            result["has_jump"] = True
            result["has_limit"] = False
            LOG.log("done", "Pan 轴无限位（检测到 3600→0 跳变）")
            print(f"  Pan 限位: 无限位（旋转式）")
        elif result["has_limit"]:
            LOG.log("done", f"Pan 轴上限: {result['upper']}")
            print(f"  Pan 上限: {result['upper']}")
        else:
            LOG.log("warning", f"Pan 正向测试未完成（{len(pan_values)} 点）")

        # 回到 HOME
        self.ptz.goto_home()
        time.sleep(STABILIZATION_SECONDS)

        # 反向测试 (PAN=-50) - 只在检测有限位时执行
        if result["has_limit"]:
            LOG.log("info", "Pan 反向测试 (PAN=-50)")
            self.recorder.start("panNegative", callback=lambda: self.ptz.get_position())

            stable_count = 0
            last_pan = None

            self.ptz.continuous_move(pan=-50, tilt=0, zoom=0)

            timeout = time.time() + 60
            while time.time() < timeout:
                pos = self.ptz.get_position()
                if pos:
                    curr_pan = pos.get("pan", 0)

                    # 检测 0→3600 跳变
                    if last_pan is not None and last_pan < 500 and curr_pan > 3000:
                        LOG.log("info", f"  反向检测到 0→3600 跳变")
                        break

                    if last_pan is not None and abs(curr_pan - last_pan) < 1:
                        stable_count += 1
                        if stable_count >= STABLE_POINTS_REQUIRED:
                            result["lower"] = curr_pan
                            LOG.log("info", f"  Pan 下限: {curr_pan}")
                            print(f"  Pan 下限: {curr_pan}")
                            break
                    else:
                        stable_count = 0

                    last_pan = curr_pan
                    self.recorder.write_row(curr_pan, pos.get("tilt", 0), pos.get("zoom", 0))

                time.sleep(SAMPLE_INTERVAL)

            self.ptz.stop_move()
            self.recorder.stop()

            self.ptz.goto_home()
            time.sleep(STABILIZATION_SECONDS)

        result["pan_tested"] = True
        self.results["pan_limit"] = result
        return result

    # --- P6.4: Tilt Limit / Flip ---

    def test_tilt_limit(self) -> dict:
        """测试 Tilt 轴限位/翻转 (P6.4)。

        方法:
        1. Gotohome 回到 home 位，稳定 2s
        2. Tilt=+50 移动
        3. 如果 T 上升到 900 位置后 20 点以内出现数值下降 → 有翻转
        4. 如果 Tilt+50 在某点位超过 20 点数值无变化 → 无翻转
        5. 执行 Tilt=-50 测下限

        返回:
            {"has_flip": bool, "upper": ..., "lower": ..., "tested": bool}
        """
        LOG.log("info", "=== P6.4: Tilt 轴限位/翻转测试 ===")
        result = {"has_flip": False, "upper": None, "lower": None, "tested": False}

        if not self.supports_tilt:
            LOG.log("info", "设备不支持 Tilt 轴，跳过")
            return result

        if not self._go_home_and_stabilize():
            return result

        # 正向测试 (Tilt=+50)
        LOG.log("info", "Tilt 正向测试 (Tilt=+50)")
        self.recorder.start("tiltPositive", callback=lambda: self.ptz.get_position())

        tilt_values = []
        stable_count = 0
        last_tilt = None
        peak_detected = False
        flip_detected = False
        max_tilt_seen = 0

        self.ptz.continuous_move(pan=0, tilt=50, zoom=0)

        timeout = time.time() + 60
        while time.time() < timeout:
            pos = self.ptz.get_position()
            if pos:
                curr_tilt = pos.get("tilt", 0)
                tilt_values.append(curr_tilt)
                max_tilt_seen = max(max_tilt_seen, curr_tilt)

                # 检测是否在 900 附近出现下降（翻转）
                if last_tilt is not None and curr_tilt > 800 and curr_tilt < last_tilt:
                    flip_detected = True
                    LOG.log("info", f"  检测到翻转: {last_tilt} → {curr_tilt}")
                    result["has_flip"] = True
                    result["upper"] = 900  # 翻转上限为 900
                    self.recorder.write_row(pos.get("pan", 0), curr_tilt, pos.get("zoom", 0))
                    # 继续运动到底
                    last_tilt = curr_tilt
                    stable_count = 0
                    continue

                # 检测稳定
                if last_tilt is not None and abs(curr_tilt - last_tilt) < 1:
                    stable_count += 1
                    if stable_count >= STABLE_POINTS_REQUIRED:
                        if not result["has_flip"]:
                            result["upper"] = curr_tilt
                            LOG.log("info", f"  无翻转，上限: {curr_tilt}")
                            print(f"  Tilt 上限: {curr_tilt} ({'自动翻转' if result['has_flip'] else '无限位'})")
                        break
                else:
                    stable_count = 0

                last_tilt = curr_tilt
                self.recorder.write_row(pos.get("pan", 0), curr_tilt, pos.get("zoom", 0))

            time.sleep(SAMPLE_INTERVAL)

        self.ptz.stop_move()
        self.recorder.stop()

        if result["has_flip"]:
            print(f"  Tilt: 自动翻转，上限=900")
        elif max_tilt_seen >= 900:
            result["has_flip"] = True
            result["upper"] = 900
            print(f"  Tilt: 自动翻转（达到 900）")

        # 回到 HOME
        self.ptz.goto_home()
        time.sleep(STABILIZATION_SECONDS)

        # 反向测试 (Tilt=-50)
        LOG.log("info", "Tilt 反向测试 (Tilt=-50)")
        self.recorder.start("tiltNegative", callback=lambda: self.ptz.get_position())

        stable_count = 0
        last_tilt = None

        self.ptz.continuous_move(pan=0, tilt=-50, zoom=0)

        timeout = time.time() + 60
        while time.time() < timeout:
            pos = self.ptz.get_position()
            if pos:
                curr_tilt = pos.get("tilt", 0)

                if last_tilt is not None and abs(curr_tilt - last_tilt) < 1:
                    stable_count += 1
                    if stable_count >= STABLE_POINTS_REQUIRED:
                        result["lower"] = curr_tilt
                        LOG.log("info", f"  Tilt 下限: {curr_tilt}")
                        print(f"  Tilt 下限: {curr_tilt}")
                        break
                else:
                    stable_count = 0

                last_tilt = curr_tilt
                self.recorder.write_row(pos.get("pan", 0), curr_tilt, pos.get("zoom", 0))

            time.sleep(SAMPLE_INTERVAL)

        self.ptz.stop_move()
        self.recorder.stop()

        result["tested"] = True
        self.results["tilt_limit"] = result
        return result

    # --- P6.5: Zoom Limit ---

    def test_zoom_limit(self) -> dict:
        """测试 Zoom 轴限位 (P6.5)。

        方法:
        1. ZOOM=+50 持续运动
        2. 观察 Z 变化，持续 2s 数值不变 → 上限
        3. ZOOM=-50 反向下限

        返回:
            {"upper": ..., "lower": ..., "tested": bool}
        """
        LOG.log("info", "=== P6.5: Zoom 轴限位测试 ===")
        result = {"upper": None, "lower": None, "tested": False}

        if not self.supports_zoom:
            LOG.log("info", "设备不支持 Zoom 轴，跳过")
            return result

        if not self._go_home_and_stabilize():
            return result

        # 正向 (ZOOM=+50)
        LOG.log("info", "Zoom 正向测试 (Zoom=+50)")
        self.recorder.start("zoomPositive", callback=lambda: self.ptz.get_position())

        stable_sec = 0.0
        last_zoom = None
        prev_zoom = None

        self.ptz.continuous_move(pan=0, tilt=0, zoom=50)

        timeout = time.time() + 30
        while time.time() < timeout:
            pos = self.ptz.get_position()
            if pos:
                curr_zoom = pos.get("zoom", 0)

                if last_zoom is not None and abs(curr_zoom - last_zoom) < 0.1:
                    stable_sec += SAMPLE_INTERVAL
                    if stable_sec >= 2.0:
                        result["upper"] = curr_zoom
                        LOG.log("info", f"  Zoom 上限: {curr_zoom} (持续 2s 不变)")
                        print(f"  Zoom 上限: {curr_zoom}")
                        break
                else:
                    stable_sec = 0.0

                last_zoom = curr_zoom
                self.recorder.write_row(pos.get("pan", 0), pos.get("tilt", 0), curr_zoom)

            time.sleep(SAMPLE_INTERVAL)

        self.ptz.stop_move()
        self.recorder.stop()

        # 回到 HOME
        self.ptz.goto_home()
        time.sleep(STABILIZATION_SECONDS)

        # 反向 (ZOOM=-50)
        LOG.log("info", "Zoom 反向测试 (Zoom=-50)")
        self.recorder.start("zoomNegative", callback=lambda: self.ptz.get_position())

        stable_sec = 0.0
        last_zoom = None

        self.ptz.continuous_move(pan=0, tilt=0, zoom=-50)

        timeout = time.time() + 30
        while time.time() < timeout:
            pos = self.ptz.get_position()
            if pos:
                curr_zoom = pos.get("zoom", 0)

                if last_zoom is not None and abs(curr_zoom - last_zoom) < 0.1:
                    stable_sec += SAMPLE_INTERVAL
                    if stable_sec >= 2.0:
                        result["lower"] = curr_zoom
                        LOG.log("info", f"  Zoom 下限: {curr_zoom}")
                        print(f"  Zoom 下限: {curr_zoom}")
                        break
                else:
                    stable_sec = 0.0

                last_zoom = curr_zoom
                self.recorder.write_row(pos.get("pan", 0), pos.get("tilt", 0), curr_zoom)

            time.sleep(SAMPLE_INTERVAL)

        self.ptz.stop_move()
        self.recorder.stop()

        result["tested"] = True
        self.results["zoom_limit"] = result
        return result

    # --- P6.6: Device Restore ---

    def restore_device(self) -> bool:
        """还原设备并停止数据读写 (P6.6)。
        
        1. 停止所有录制/移动
        2. 调用 ISAPI 恢复 API
        3. 回到 HOME 位
        4. 验证坐标回到默认值
        """
        LOG.log("info", "=== P6.6: 设备还原 ===")

        # 停止所有录制
        self.recorder.stop()

        # 停止移动
        self.ptz.stop_move()

        # 调用所有已修改参数的恢复 API
        try:
            restore_endpoint = "/System/restore"
            restore_xml = '<?xml version="1.0" encoding="UTF-8"?>' \
                '<restore xmlns="http://www.hikvision.com/ver20/XMLSchema"/>'
            restore_result = self.ptz.client.put(restore_endpoint, restore_xml)
            if restore_result.status_code == 200:
                LOG.log("info", "ISAPI 恢复默认参数成功")
            else:
                LOG.log("warning", f"ISAPI 恢复默认参数返回 {restore_result.status_code}")
            time.sleep(1)
        except Exception as e:
            LOG.log("warning", f"ISAPI 恢复默认参数失败: {e}")

        # 回到 HOME 位
        success = self.ptz.goto_home()
        if not success:
            LOG.log("error", "设备还原失败（回到预置点失败）")
            return False

        time.sleep(STABILIZATION_SECONDS)

        # 验证所有参数回到默认值
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
                LOG.log("error", f"还原后坐标偏差: P={pan} T={tilt} Z={zoom} "
                        f"(期望 P={HOME_COORDS['pan']}±5 T={HOME_COORDS['tilt']}±5 Z={HOME_COORDS['zoom']}±2)")
                return False
        else:
            LOG.log("error", "还原后无法获取位置")
            return False

    # --- Run all limit tests ---

    def run_all_limit_tests(self, device_info: dict | None = None) -> dict:
        """运行所有 P6 限位测试。

        返回:
            限位测试结果
        """
        LOG.log("info", "========================================")
        LOG.log("info", "  P6: PTZ 限位测试开始")
        LOG.log("info", "========================================")

        results = {}
        results["axis_support"] = self.check_axis_support()

        if not (self.supports_pan or self.supports_tilt or self.supports_zoom):
            LOG.log("warning", "设备不支持任何 PTZ 轴，跳过 P6")
            return results

        results["device"] = self.identify_device()
        results["pan_limit"] = self.test_pan_limit()
        results["tilt_limit"] = self.test_tilt_limit()
        results["zoom_limit"] = self.test_zoom_limit()
        results["restore"] = self.restore_device()

        return results
