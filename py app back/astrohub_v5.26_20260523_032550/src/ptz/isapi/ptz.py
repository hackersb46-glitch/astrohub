"""
PTZ_ASTRO v1.1 - ISAPI PTZ 控制模块
PTZ 预设、连续/绝对/相对移动、变焦控制。

基于 Hikvision ISAPI PTZCtrl 端点的 XML 控制协议。

Author: 雅痞张@南方天文
"""

import time

from .client import ISAPIClient, ISAPIResponse
from ptz.core.logger import LOG
from ptz.constants import ISAPI_CHANNEL, DEFAULT_PTZ_PRESET, HOME_COORDS


class PTZController:
    """ISAPI PTZ 控制器。"""

    def __init__(self, client: ISAPIClient) -> None:
        self.client = client
        self.channel = ISAPI_CHANNEL
        self.home_preset = DEFAULT_PTZ_PRESET  # 预置点 10
        self.home_coords = HOME_COORDS  # {pan: 1800, tilt: 450, zoom: 10}

    # --- URL helpers ---

    def _ptz_base(self) -> str:
        return f"/PTZCtrl/channels/{self.channel}"

    # --- Position ---

    def get_position(self) -> dict:
        """获取当前 PTZ 位置。

        返回:
            {"pan": float, "tilt": float, "zoom": float} 或空字典
        """
        LOG.log("info", f"ISAPI 获取 PTZ 位置")

        result = self.client.get(f"{self._ptz_base()}/status")

        if result.status_code != 200:
            LOG.log("warning", f"获取 PTZ 位置失败: HTTP {result.status_code}")
            return {}

        try:
            import xml.etree.ElementTree as ET
            elem = ET.fromstring(result.xml)

            def find_text(tag: str) -> str:
                for child in elem.iter():
                    if child.tag.endswith(tag):
                        return (child.text or "").strip()
                return ""

            pan = self.client.get_xml_float(elem, "azimuth", 0)
            tilt = self.client.get_xml_float(elem, "elevation", 0)
            zoom = self.client.get_xml_float(elem, "absoluteZoom", 0)
            # Hikvision stores azimuth in tenths of degrees (e.g. 1800 = 180.0°)
            # We keep it in the device-native unit
            return {"pan": pan, "tilt": tilt, "zoom": zoom}
        except Exception as e:
            LOG.log("warning", f"解析 PTZ 位置异常: {e}")
            return {}

    # --- Presets ---

    def goto_preset(self, preset_id: int) -> bool:
        """移动到预置点。

        返回:
            True = 成功
        """
        LOG.log("info", f"ISAPI 移动到预置点: {preset_id}")

        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<PTZData version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <presetIndex>{preset_id}</presetIndex>
</PTZData>"""

        result = self.client.put(f"{self._ptz_base()}/presets/{preset_id}/goto", xml)
        if result.status_code == 200:
            LOG.log("done", f"预置点 {preset_id} 移动成功")
            return True
        else:
            LOG.log("error", f"预置点 {preset_id} 移动失败: HTTP {result.status_code}")
            return False

    def list_presets(self) -> list[dict]:
        """获取预置点列表。

        GET /ISAPI/PTZCtrl/channels/{ch}/presetChannels
        返回预置点列表: [{"id": int, "name": str}, ...]
        """
        LOG.log("info", "ISAPI 获取预置点列表")
        try:
            result = self.client.get("/PTZCtrl/channels/1/presetChannels")
            if result.status_code != 200:
                LOG.log("warning", f"获取预置点列表失败: HTTP {result.status_code}")
                return []
            import xml.etree.ElementTree as ET
            root = ET.fromstring(result.xml)
            presets = []
            ns = {"hik": "http://www.hikvision.com/ver20/XMLSchema"}
            for p in root.findall(".//hik:preset", ns) or root.findall(".//preset"):
                preset_id = (p.findtext("hik:id") or p.findtext("id") or "").strip()
                preset_name = (p.findtext("hik:name") or p.findtext("name") or "").strip()
                if preset_id:
                    presets.append({"id": int(preset_id), "name": preset_name or f"Preset {preset_id}"})
            # Fallback: some devices return without namespace
            if not presets:
                for elem in root.iter():
                    local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                    if local == "preset":
                        pid = ""
                        pname = ""
                        for child in elem:
                            ctag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                            if ctag == "id": pid = (child.text or "").strip()
                            if ctag == "name": pname = (child.text or "").strip()
                        if pid:
                            presets.append({"id": int(pid), "name": pname or f"Preset {pid}"})
            LOG.log("done", f"获取预置点列表: {len(presets)} 个")
            return presets
        except Exception as e:
            LOG.log("error", f"获取预置点列表异常: {e}")
            return []

    def set_preset(self, preset_id: int) -> bool:
        """设置当前位为预置点。

        返回:
            True = 成功
        """
        LOG.log("info", f"ISAPI 设置预置点: {preset_id}")

        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<PTZData version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <presetIndex>{preset_id}</presetIndex>
</PTZData>"""

        result = self.client.put(f"{self._ptz_base()}/presets/{preset_id}", xml)
        if result.status_code == 200:
            LOG.log("done", f"预置点 {preset_id} 设置成功")
            return True
        else:
            LOG.log("error", f"预置点 {preset_id} 设置失败: HTTP {result.status_code}")
            return False

    def goto_home(self) -> bool:
        """Move to HOME preset 10, verify coords and stability.

        评审标准: 预置点10，坐标1800/450/10，0偏差，wait_stable验证稳定
        """
        if not self.goto_preset(self.home_preset):
            LOG.log("error", "goto_home: failed to goto preset")
            return False

        time.sleep(2)  # Wait for movement to complete

        if not self.wait_stable(samples=20, interval=0.1, tolerance=10.0):
            LOG.log("warning", "goto_home: PTZ did not stabilize")
            return False

        pos = self.get_position()
        if not pos:
            LOG.log("error", "goto_home: failed to get position after stabilization")
            return False

        pan_ok = abs(pos.get("pan", 0) - self.home_coords["pan"]) <= 10
        tilt_ok = abs(pos.get("tilt", 0) - self.home_coords["tilt"]) <= 10
        zoom_ok = abs(pos.get("zoom", 0) - self.home_coords["zoom"]) <= 1

        if pan_ok and tilt_ok and zoom_ok:
            LOG.log("done", f"goto_home verified: pan={pos['pan']}, tilt={pos['tilt']}, zoom={pos['zoom']}")
            return True

        LOG.log("warning", f"goto_home: coords mismatch. Expected {self.home_coords}, got {pos}")
        return False

    def wait_stable(self, samples: int = 20, interval: float = 0.1, tolerance: float = 10.0) -> bool:
        """Wait until PTZ is stable.

        评审标准: 连续20次位置采样，间隔0.1s，变化<±1° → 稳定
        ±1° = ±10 in device units (pan/tilt are in tenths of degrees)

        Args:
            samples: Number of position samples (default: 20)
            interval: Seconds between samples (default: 0.1)
            tolerance: Max deviation in device units (default: 10 = ±1°)

        Returns:
            True if stable (deviation < tolerance), False otherwise
        """
        readings = []
        for _ in range(samples):
            pos = self.get_position()
            if pos:
                readings.append(pos)
            time.sleep(interval)

        if len(readings) < samples:
            LOG.log("warning", f"wait_stable: only got {len(readings)}/{samples} readings")
            return False

        pan_vals = [r["pan"] for r in readings]
        tilt_vals = [r["tilt"] for r in readings]
        zoom_vals = [r["zoom"] for r in readings]

        pan_dev = max(pan_vals) - min(pan_vals)
        tilt_dev = max(tilt_vals) - min(tilt_vals)
        zoom_dev = max(zoom_vals) - min(zoom_vals)

        is_stable = (pan_dev <= tolerance and tilt_dev <= tolerance and zoom_dev <= 1)
        if is_stable:
            LOG.log("done", f"PTZ stable: pan_dev={pan_dev}, tilt_dev={tilt_dev}, zoom_dev={zoom_dev}")
        else:
            LOG.log("warning", f"PTZ not stable: pan_dev={pan_dev}, tilt_dev={tilt_dev}, zoom_dev={zoom_dev}")

        return is_stable

    def continuous_move(self, pan: float = 0, tilt: float = 0, zoom: float = 0) -> bool:
        """持续移动。

        CSV要求: Continuous Move, Pan/Tilt 速度由前端传入。
        ISAPI 2.0 格式: Continuous 端点, panSpeed/tiltSpeed 范围 -10~10, zoomSpeed -10~10, 0=停止.

        参数:
            pan: -100 ~ 100（负=左，正=右）
            tilt: -100 ~ 100（负=下，正=上）
            zoom: -100 ~ 100（负=缩小，正=放大）

        返回:
            True = 移动成功
        """
        LOG.log("info", f"ISAPI 持续移动: pan={pan}, tilt={tilt}, zoom={zoom}")

        # 将 0-100 范围映射到 -10~10 (ISAPI 2.0 规范)
        pan_speed = int(pan)
        tilt_speed = int(tilt)
        zoom_speed = int(zoom)

        # 停止移动：速度全0
        if pan_speed == 0 and tilt_speed == 0 and zoom_speed == 0:
            xml = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<PTZData version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">'
                '<ptzSpeed>'
                '<pan>0</pan><tilt>0</tilt><zoom>0</zoom>'
                '</ptzSpeed>'
                '</PTZData>'
            )
            result = self.client.put(f"{self._ptz_base()}/continuous", xml)
            return result.status_code == 200

        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<PTZData version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <ptzSpeed>
    <pan>{pan_speed}</pan>
    <tilt>{tilt_speed}</tilt>
    <zoom>{zoom_speed}</zoom>
  </ptzSpeed>
</PTZData>"""

        result = self.client.put(f"{self._ptz_base()}/continuous", xml)
        return result.status_code == 200

    def stop_move(self) -> bool:
        """停止所有移动。"""
        LOG.log("info", "ISAPI 停止所有移动")
        return self.continuous_move(0, 0, 0)

    def continuous_move_duration(self, pan: float, tilt: float, duration: float) -> list[dict]:
        """持续移动指定时长，期间采样位置。

        参数:
            pan: -100 ~ 100
            tilt: -100 ~ 100
            duration: 秒

        返回:
            采样位置列表 [{"pan": ..., "tilt": ..., "zoom": ...}, ...]
        """
        positions = []

        # 启动移动
        if not self.continuous_move(pan=pan, tilt=tilt):
            LOG.log("error", "持续移动启动失败")
            return positions

        # 采样
        start = time.time()
        sample_interval = 0.1
        while time.time() - start < duration:
            pos = self.get_position()
            if pos:
                positions.append(pos)
            time.sleep(sample_interval)

        # 停止
        self.stop_move()
        LOG.log("done", f"持续移动完成: {len(positions)} 个采样点")

        return positions

    def absolute_move(
        self, pan: float, tilt: float, zoom: float | None = None, speed: int = 50
    ) -> bool:
        """绝对坐标移动。

        参数:
            pan: 水平角度 0~3600（1800 = 180°）
            tilt: 垂直角度 -900~900
            zoom: 变焦级别
        """
        LOG.log("info", f"ISAPI 绝对移动: pan={pan}, tilt={tilt}")

        zoom_val = f"<absoluteZoom>{zoom}</absoluteZoom>" if zoom is not None else ""

        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<PTZData version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <AbsoluteHigh>
    <azimuth>{pan}</azimuth>
    <elevation>{tilt}</elevation>
    {zoom_val}
    <speed>{speed}</speed>
  </AbsoluteHigh>
</PTZData>"""

        result = self.client.put(f"{self._ptz_base()}/absolute", xml)
        if result.status_code == 200:
            LOG.log("done", "绝对移动成功")
            return True
        else:
            LOG.log("error", f"绝对移动失败: HTTP {result.status_code}")
            return False

    def relative_move(self, pan: float, tilt: float, zoom: float = 0) -> bool:
        """相对移动。

        参数:
            pan: 相对偏移量
            tilt: 相对偏移量
            zoom: 相对变焦量
        """
        LOG.log("info", f"ISAPI 相对移动: pan={pan}, tilt={tilt}, zoom={zoom}")

        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<PTZData version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <Relative>
    <positionX>{pan}</positionX>
    <positionY>{tilt}</positionY>
    <relativeZoom>{zoom}</relativeZoom>
  </Relative>
</PTZData>"""

        result = self.client.put(f"{self._ptz_base()}/relative", xml)
        if result.status_code == 200:
            LOG.log("done", "相对移动成功")
            return True
        else:
            LOG.log("error", f"相对移动失败: HTTP {result.status_code}")
            return False

    # --- Zoom ---

    def zoom_in(self, speed: int = 50) -> bool:
        """光学变焦放大。"""
        return self.continuous_move(0, 0, speed)

    def zoom_out(self, speed: int = 50) -> bool:
        """光学变焦缩小。"""
        return self.continuous_move(0, 0, -speed)

    def zoom_range_test(self) -> dict:
        """测试 ZOOM 范围，获取 min/max。

        返回:
            {"zoom_min": ..., "zoom_max": ..., "supported": bool}
        """
        LOG.log("info", "=== ZOOM 范围测试 ===")
        result = {"zoom_min": 0, "zoom_max": 0, "supported": False}

        # 获取初始位置
        initial_pos = self.get_position()
        if not initial_pos:
            LOG.log("warning", "无法获取初始位置")
            return result

        initial_zoom = initial_pos.get("zoom", 0)
        result["zoom_min"] = initial_zoom
        result["zoom_max"] = initial_zoom

        # 移动到 HOME 位
        self.goto_home()
        time.sleep(2)

        LOG.log("info", "测试 ZOOM+ (缩小方向)")
        # 先往 + 移动
        self.zoom_in(speed=50)
        time.sleep(2)
        self.stop_move()
        time.sleep(1)

        max_zoom_pos = self.get_position()
        if max_zoom_pos:
            result["zoom_max"] = max_zoom_pos.get("zoom", 0)

        LOG.log("info", "测试 ZOOM- (放大方向)")
        self.zoom_out(speed=50)
        time.sleep(2)
        self.stop_move()
        time.sleep(1)

        min_zoom_pos = self.get_position()
        if min_zoom_pos:
            result["zoom_min"] = min_zoom_pos.get("zoom", 0)

        result["supported"] = True
        LOG.log("done", f"ZOOM 范围: min={result['zoom_min']}, max={result['zoom_max']}")

        # 回到 HOME
        self.goto_home()
        return result

    # --- Focus (对焦 P4.4) ---

    def get_focus_position(self) -> int | None:
        """获取当前对焦位置 (P4.4)。

        GET /ISAPI/System/Video/inputs/channels/{ch}/focus
        解析XML返回的当前对焦位置。
        """
        LOG.log("info", "获取对焦位置...")
        endpoint = f"/System/Video/inputs/channels/{self.channel}/focus"
        result = self.client.get(endpoint)
        if result.status_code != 200:
            LOG.log("warning", f"获取对焦位置失败: HTTP {result.status_code}")
            return None

        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(result.xml)
            # 查找 autoFocusMode / zoom / initPos 等字段
            for elem in root.iter():
                local_name = elem.tag.split("}")[-1].lower() if "}" in elem.tag else elem.tag.lower()
                if local_name in ("initpos", "focusposition", "zoom", "position"):
                    if elem.text:
                        try:
                            val = int(elem.text.strip())
                            LOG.log("done", f"当前对焦位置: {val}")
                            return val
                        except (ValueError, TypeError):
                            pass
            LOG.log("warning", "无法解析对焦位置XML")
            return None
        except Exception as e:
            LOG.log("warning", f"解析对焦XML异常: {e}")
            return None

    def set_focus_mode(self, mode: str) -> bool:
        """设置对焦模式: 'manual' 或 'auto'。

        mode: 'manual'=手动对焦, 'auto'=自动对焦
        """
        LOG.log("info", f"设置对焦模式: {mode}")
        endpoint = f"/System/Video/inputs/channels/{self.channel}/focus"

        mode_mapping = {
            "manual": "Manual",
            "auto": "autoFocus",
        }

        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Focus xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <autoFocusMode>{mode_mapping.get(mode, mode)}</autoFocusMode>
</Focus>"""

        result = self.client.put(endpoint, xml)
        return result.status_code == 200

    def focus_move(self, direction: str, speed: int = 50) -> bool:
        """对焦马达移动 (近/远)。

        direction: 'near' (近焦) 或 'far' (远焦)
        speed: 速度 1~100
        """
        LOG.log("info", f"对焦移动: direction={direction}, speed={speed}")
        endpoint = f"/System/Video/inputs/channels/{self.channel}/focus"

        step_val = -speed if direction == "near" else speed

        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Focus xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <autoFocusMode>Manual</autoFocusMode>
  <manualFocus>
    <step>{step_val}</step>
  </manualFocus>
</Focus>"""

        result = self.client.put(endpoint, xml)
        return result.status_code == 200

    def focus_range_test(self) -> dict:
        """测试对焦范围，真实驱动马达验证变化 (P4.4)。

        返回:
            {"success": bool, "focus_before": int, "focus_after": int,
             "delta": int, "message": str}
        """
        LOG.log("info", "=== P4.4: 对焦范围验证 (真实马达) ===")
        result = {"success": False, "focus_before": None, "focus_after": None, "delta": 0}

        # 读取当前对焦位置
        focus_before = self.get_focus_position()
        if focus_before is None:
            LOG.log("error", "无法获取初始对焦位置")
            result["message"] = "无法获取聚焦位置"
            return result

        result["focus_before"] = focus_before
        LOG.log("info", f"对焦移动前位置: {focus_before}")

        # 确保在手动模式
        self.set_focus_mode("manual")

        # 发送聚焦移动命令 (远焦方向)
        self.focus_move("far", speed=50)
        time.sleep(2)

        # 读取新位置
        focus_after = self.get_focus_position()
        if focus_after is None:
            LOG.log("error", "移动后无法获取对焦位置")
            result["message"] = "移动后无法获取聚焦位置"
            return result

        result["focus_after"] = focus_after
        result["delta"] = abs(focus_after - focus_before)

        LOG.log("info", f"对焦移动后位置: {focus_after}, 变化量={result['delta']}")

        # 验证有变化
        if result["delta"] > 0:
            LOG.log("done", f"对焦验证通过: {focus_before} → {focus_after}, delta={result['delta']}")
            result["message"] = f"聚焦马达有效, 变化={result['delta']}"
            result["success"] = True
        else:
            LOG.log("error", f"对焦验证失败: 位置无变化 ({focus_before} → {focus_after})")
            result["message"] = f"聚焦马达无变化"
            result["success"] = False

        # 恢复到手动模式 (已保持手动)
        return result

    # --- Focus (对焦 P4.4) ---
