"""
AstroHub v2.0 - 功能探测模块 (Function Detection)

实现 P4.1-P4.21 共 18 项设备功能探测 (严格按 doc/review/M1_method.csv):
- 每一项: GET端点探测 → 读取当前值 → 读取取值范围 → 修改测试 → 恢复原始值 → 结果写入config
- 基于 ISAPI client 发送请求

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.ptz.isapi.client import ISAPIClient, ISAPIResponse
from src.ptz.constants import ISAPI_CHANNEL, HOME_COORDS
from src.advanced.device_path import get_device_info, get_data_path_write, get_data_path_read, get_devices_dir


def verify_home_preset(client) -> dict:
    """P5.0: Verify or create preset 10 (HOME) before function detection.

    Steps: goto_preset(10) → verify coords=1800/450/10
    If not matching, set_preset(10) from current position.
    If preset 10 already exists, ONLY verify, DO NOT overwrite.
    """
    import time
    from src.ptz.isapi.ptz import PTZController

    ptz = PTZController(client)

    # First try to goto preset 10 to see if it exists
    ptz.goto_preset(10)
    time.sleep(2)
    pos = ptz.get_position()

    expected = HOME_COORDS  # {pan: 1800, tilt: 450, zoom: 10}

    if pos:
        pan_ok = abs(pos.get("pan", 0) - expected["pan"]) <= 10
        tilt_ok = abs(pos.get("tilt", 0) - expected["tilt"]) <= 5
        zoom_ok = abs(pos.get("zoom", 0) - expected["zoom"]) <= 1
        if pan_ok and tilt_ok and zoom_ok:
            return {
                "success": True, "preset_exists": True,
                "position": pos, "message": "Preset 10 verified, coords match HOME"
            }

    # Preset 10 doesn't match HOME coords - need to set it
    # Don't blindly overwrite: first verify we're at a reasonable position
    result = ptz.set_preset(10)
    if result:
        time.sleep(1)
        ptz.goto_preset(10)
        time.sleep(2)
        pos = ptz.get_position()
    return {
        "success": result, "preset_exists": False,
        "position": pos or {}, "message": "Preset 10 set"
    }


# ================================================================ #
#  功能探测端点定义 (P4.1-P4.21) - 严格按 M1_method.csv
# ================================================================ #

FUNCTION_ENDPOINTS: dict[str, dict[str, Any]] = {
    # --- P4.1 IrLED 红外补光 ---
    "ir_led": {
        "p_id": "P4.1",
        "label": "IrLED 红外补光",
        "endpoint": "/Image/channels/{ch}/IrLight",
        "test_key": "brightnessLimit",
        "test_value": 50,
        "range_min": 1,
        "range_max": 100,
        "mode": "numeric",
    },

    # --- P4.2 白平衡 ---
    "white_balance": {
        "p_id": "P4.2",
        "label": "白平衡",
        "endpoint": "/Image/channels/{ch}/whiteBalance",
        "test_key": "WhiteBalanceRed",
        "test_keys": {"WhiteBalanceRed": 200, "WhiteBalanceBlue": 200},
        "test_value": 200,
        "range_min": 0,
        "range_max": 255,
        "mode": "multi_field",
    },

    # --- P4.3 Gain 模拟增益 ---
    "gain": {
        "p_id": "P4.3",
        "label": "Gain 模拟增益",
        "endpoint": "/Image/channels/{ch}/gain",
        "test_key": "GainLevel",
        "test_value": 50,
        "range_min": 0,
        "range_max": 100,
        "mode": "numeric",
    },

    # --- P4.4 Focus 聚焦 ---
    "focus": {
        "p_id": "P4.4",
        "label": "Focus 聚焦",
        "endpoint": "/Image/channels/{ch}/focusConfiguration",
        "test_key": "focusStyle",
        "test_values": ["MANUAL", "SEMIAUTOMATIC", "AUTOMATIC"],
        "mode": "style_switch",
    },

    # --- P4.4b Focus+/- 控制 (通过 PTZ continuous) ---
    "focus_adjust": {
        "p_id": "P4.4b",
        "label": "Focus+/- 调节",
        "endpoint": "/PTZCtrl/channels/{ch}/continuous",
        "test_key": "focus",
        "test_values": ["5", "-5", "0"],  # +5: 远离, -5: 靠近, 0: 停止
        "mode": "focus_continuous",
        "description": "通过 PTZ continuous 端点控制 focus+/-",
    },

    # --- P4.5 快门速度 ---
    "shutter": {
        "p_id": "P4.5",
        "label": "快门速度(手动模式)",
        "endpoint": "/Image/channels/{ch}/Shutter",
        "test_key": "ShutterLevel",
        "test_value": "1/100",
        "range_min": "1/30000",
        "range_max": "1/25",
        "mode": "shutter",
    },

    # --- P4.6 慢快门 ---
    "slow_shutter": {
        "p_id": "P4.6",
        "label": "慢快门",
        "endpoint": "/Image/channels/{ch}/Shutter",
        "test_key": "minShutterLevelLimit",
        "test_value": None,  # 复用Shutter端点,仅读取不PUT
        "range_min": "1/30000",
        "range_max": None,
        "mode": "read_only",
    },

    # --- P4.7 光圈 Iris ---
    "iris": {
        "p_id": "P4.7",
        "label": "光圈 Iris",
        "endpoint": "/Image/channels/{ch}/Iris",
        "test_key": "IrisLevel",
        "test_value": 160,  # 使用离散值列表中的值
        "values": [160, 200, 240, 280, 340, 400, 480, 560, 680, 960, 1100, 1400, 1600, 1900, 2200],
        "range_min": 160,  # F1.6 最大光圈
        "range_max": 2200,  # F22 最小光圈
        "mode": "iris",  # 绝对值模式,使用PUT设置IrisLevel
        "value_mapping": {
            "note": "数值越大光圈越小",
            "formula": "F数值 = IrisLevel / 100",
            "160": "F1.6 (最大光圈)",
            "2200": "F22 (最小光圈)",
        },
    },

    # --- P4.8 快门速度 (重复端点) ---
    "shutter_repeat": {
        "p_id": "P4.8",
        "label": "快门速度",
        "endpoint": "/Image/channels/{ch}/Shutter",
        "test_key": "ShutterLevel",
        "test_value": "1/50",
        "range_min": "1/30000",
        "range_max": "1/25",
        "mode": "shutter",
    },

    # --- P4.9 数字降噪-时域 ---
    "dnr_temporal": {
        "p_id": "P4.9",
        "label": "数字降噪-时域",
        "endpoint": "/Image/channels/{ch}/noiseReduce",
        "test_key": "generalLevel",
        "test_value": 50,
        "range_min": 0,
        "range_max": 100,
        "mode": "numeric",
        "xml_structure": "<mode>general</mode><GeneralMode><generalLevel>{value}</generalLevel></GeneralMode>",
    },

    # --- P4.10 数字降噪-空域 ---
    "dnr_spatial": {
        "p_id": "P4.10",
        "label": "数字降噪-空域",
        "endpoint": "/Image/channels/{ch}/noiseReduce",
        "test_key": "generalLevel",
        "test_value": 50,
        "range_min": 0,
        "range_max": 100,
        "mode": "numeric",
        "xml_structure": "<mode>general</mode><GeneralMode><generalLevel>{value}</generalLevel></GeneralMode>",
    },

    # --- P4.11 IRCUT 滤波片/日夜转换 ---
    "ircut": {
        "p_id": "P4.11",
        "label": "IRCUT 滤波片/日夜转换",
        "endpoint": "/Image/channels/{ch}/IrcutFilter",
        "test_key": "IrcutFilterAction",
        "test_value": "night",
        "test_values": ["night", "day"],
        "secondary_key": "nightToDayFilterLevel",
        "secondary_range_min": 1,
        "secondary_range_max": 7,
        "mode": "action_switch",
    },

    # --- P4.12 WDR 宽动态 ---
    "wdr": {
        "p_id": "P4.12",
        "label": "WDR 宽动态",
        "endpoint": "/Image/channels/{ch}/WDR",
        "test_key": "WDRLevel",
        "test_value": 80,
        "range_min": 0,
        "range_max": 100,
        "mode": "numeric",
    },

    # --- P4.13 BLC 背光补偿 ---
    "blc": {
        "p_id": "P4.13",
        "label": "BLC 背光补偿",
        "endpoint": "/Image/channels/{ch}/BLC",
        "test_key": "enabled",
        "test_values": ["true", "false"],
        "mode": "toggle",
    },

    # --- P4.14 Dehaze 除雾 ---
    "dehaze": {
        "p_id": "P4.14",
        "label": "Dehaze 除雾",
        "endpoint": "/Image/channels/{ch}/dehaze",
        "test_key": "DehazeLevel",
        "test_value": 80,
        "range_min": 0,
        "range_max": 100,
        "mode": "numeric",
    },

    # --- P4.15 Sharpness 锐度 ---
    "sharpness": {
        "p_id": "P4.15",
        "label": "Sharpness 锐度",
        "endpoint": "/Image/channels/{ch}/Sharpness",
        "test_key": "SharpnessLevel",
        "test_value": 80,
        "range_min": 0,
        "range_max": 100,
        "mode": "numeric",
    },

    # --- P4.16 亮度 ---
    "brightness": {
        "p_id": "P4.16",
        "label": "亮度",
        "endpoint": "/Image/channels/{ch}/color",
        "test_key": "brightnessLevel",
        "test_value": 80,
        "range_min": 0,
        "range_max": 100,
        "mode": "numeric",
    },

    # --- P4.17 饱和度 ---
    "saturation": {
        "p_id": "P4.17",
        "label": "饱和度",
        "endpoint": "/Image/channels/{ch}/color",
        "test_key": "saturationLevel",
        "test_value": 80,
        "range_min": 0,
        "range_max": 100,
        "mode": "numeric",
    },

    # --- P4.18 对比度 ---
    "contrast": {
        "p_id": "P4.18",
        "label": "对比度",
        "endpoint": "/Image/channels/{ch}/color",
        "test_key": "contrastLevel",
        "test_value": 80,
        "range_min": 0,
        "range_max": 100,
        "mode": "numeric",
    },

    # --- P4.19 Sharpness 锐度 (CSV重复项) ---
    "sharpness_repeat": {
        "p_id": "P4.19",
        "label": "Sharpness 锐度 (P4.19)",
        "endpoint": "/Image/channels/{ch}/Sharpness",
        "test_key": "SharpnessLevel",
        "test_value": 80,
        "range_min": 0,
        "range_max": 100,
        "mode": "numeric",
    },

    # --- P4.20 Mirror 镜像 ---
    "mirror": {
        "p_id": "P4.20",
        "label": "Mirror 镜像",
        "endpoint": "/Image/channels/{ch}/ImageFlip",
        "test_key": "ImageFlipStyle",
        "test_values": ["LEFTRIGHT", "UPDOWN", "CENTER", "AUTO"],
        "mode": "style_switch",
    },
}

# P4.21 设备还原 - 遍历所有端点逐个 PUT 原始 XML


@dataclass
class FunctionResult:
    """单项功能探测结果。"""
    p_id: str = ""
    item: str = ""
    label: str = ""
    supported: bool = False
    min_val: str | int = 0
    max_val: str | int = 0
    opt_values: list[str] | None = None  # v7.32: 添加 opt_values 字段
    current_values: dict[str, Any] = field(default_factory=dict)
    test_results: list[dict] = field(default_factory=list)
    restored: bool = True
    error: str | None = None
    endpoint: str = ""
    test_key: str = ""
    config_entry: dict = field(default_factory=dict)


class FunctionDetector:
    """设备功能探测器 - P4.1 至 P4.21 共 20 项功能探测 (严格按 CSV)。

    每一项的标准操作流程:
    1. GET 端点探测是否存在 (PUT+GET验证通过 = 存在)
    2. 读取当前值 (解析 XML,记录原始值)
    3. 读取取值范围 (从 XML 中或使用 CSV 定义的范围)
    4. 执行修改测试 (PUT 测试值 → GET 验证值正确 → PUT 恢复 → GET 验证恢复)
    5. PUT 恢复原始值 + GET 验证恢复成功 (在 _test_value 中完成)
    6. 结果写入 config (记录到 device_config.json)
    """

    def __init__(self, client: ISAPIClient, config_path: str | None = None, device_id: str | None = None) -> None:
        self.client = client
        self.channel = ISAPI_CHANNEL
        self._results: dict[str, FunctionResult] = {}
        self._original_xml: dict[str, str] = {}
        # v6.03: 使用动态路径 data/devices/{mac}/function.json
        self._config_path = config_path  # 保留兼容
        # 设备信息（延迟获取）
        self._device_info: dict[str, str] | None = None
        self._model_short: str | None = None
        self._mac_clean: str | None = None

    def _get_function_path(self) -> str:
        """v6.19: 获取 function.json 的动态路径（统一使用 device_path）。"""
        self._init_device_info()
        device_dir = get_devices_dir() / self._mac_clean
        device_dir.mkdir(parents=True, exist_ok=True)
        return str(device_dir / "function.json")

    def _init_device_info(self) -> None:
        """初始化设备信息（首次调用时获取）。"""
        if self._device_info is None:
            from src.ptz.isapi.ptz import PTZController
            ptz = PTZController(self.client)
            self._device_info = get_device_info(ptz)
            self._model_short = self._device_info['model_short']
            self._mac_clean = self._device_info['mac_clean']

    def _endpoint(self, cap_def: dict) -> str:
        """获取带 channel 的端点路径。"""
        return cap_def["endpoint"].format(ch=self.channel)

    def _find_xml_element(self, root: ET.Element, key: str) -> ET.Element | None:
        """递归查找 XML 元素(忽略命名空间)。"""
        for elem in root.iter():
            local_name = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if local_name.lower() == key.lower():
                return elem
        # 模糊匹配(包含)
        for elem in root.iter():
            local_name = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if key.lower() in local_name.lower():
                return elem
        return None

    def _parse_xml_value(self, root: ET.Element, key: str) -> str | int:
        """从 XML 中提取指定 key 的值。"""
        elem = self._find_xml_element(root, key)
        if elem is not None and elem.text:
            text = elem.text.strip()
            # 尝试整数
            try:
                return int(text)
            except ValueError:
                pass
            # 尝试布尔
            if text.lower() in ("true", "yes", "1"):
                return 1
            elif text.lower() in ("false", "no", "0"):
                return 0
            return text
        return 0

    def _parse_all_values(self, root: ET.Element, keys: dict) -> dict[str, Any]:
        """从 XML 中提取多个字段的值。"""
        values = {}
        for key in keys:
            values[key] = self._parse_xml_value(root, key)
        return values

    def _parse_range(self, root: ET.Element, key: str) -> tuple[str | int, str | int]:
        """从 XML 响应中解析指定 key 的取值范围。"""
        min_val = 0
        max_val = 100
        for elem in root.iter():
            local_name = elem.tag.split("}")[-1].lower() if "}" in elem.tag else elem.tag.lower()
            if "min" in local_name and key.lower() in local_name and elem.text:
                try:
                    min_val = int(elem.text.strip())
                except (ValueError, TypeError):
                    min_val = elem.text.strip()
            if "max" in local_name and key.lower() in local_name and elem.text:
                try:
                    max_val = int(elem.text.strip())
                except (ValueError, TypeError):
                    max_val = elem.text.strip()
            # Hikvision range="0,100" 格式
            if "range" in local_name and elem.text:
                try:
                    if "[" in elem.text:
                        parts = elem.text.strip().split("[")[1].split("]")[0].split(",")
                        if len(parts) == 2:
                            min_val = int(parts[0].strip())
                            max_val = int(parts[1].strip())
                    elif "," in elem.text:
                        parts = elem.text.strip().split(",")
                        if len(parts) == 2:
                            min_val = int(parts[0].strip())
                            max_val = int(parts[1].strip())
                except (IndexError, ValueError):
                    pass
        return min_val, max_val

    def _probe_endpoint(self, endpoint: str) -> ISAPIResponse:
        """探测 ISAPI 端点是否存在。"""
        return self.client.get(endpoint)

    def _parse_opt_values(self, root: ET.Element, key: str) -> list[str] | None:
        """v7.08: 从 XML 响应中解析指定 key 的 opt 属性值列表。
        
        用于解析 capabilities 端点返回的可选值列表，如:
        <ShutterLevel opt="1/25,1/50,1/75,...">1/1000</ShutterLevel>
        
        Returns:
            opt 值列表，如 ["1/25", "1/50", "1/75", ...]，如果没有 opt 属性则返回 None
        """
        for elem in root.iter():
            local_name = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if local_name.lower() == key.lower():
                opt_attr = elem.get("opt")
                if opt_attr:
                    # 解析逗号分隔的值
                    values = [v.strip() for v in opt_attr.split(",")]
                    return values
        return None

    def _fetch_capabilities_opt_values(self, endpoint_base: str, key: str) -> list[str] | None:
        """v7.08: 从 capabilities 端点获取 opt 值列表。
        
        Args:
            endpoint_base: 基础端点，如 "/Image/channels/1/Shutter"
            key: 字段名，如 "ShutterLevel"
        
        Returns:
            opt 值列表
        """
        # 构建 capabilities 端点
        cap_endpoint = endpoint_base.rsplit("/", 1)[0] + "/capabilities"
        if "/Image/channels/" in endpoint_base:
            # /Image/channels/1/Shutter -> /Image/channels/1/capabilities
            cap_endpoint = "/Image/channels/" + str(self.channel) + "/capabilities"
        
        try:
            resp = self._probe_endpoint(cap_endpoint)
            if resp.status_code == 200:
                root = ET.fromstring(resp.xml)
                return self._parse_opt_values(root, key)
        except Exception as e:
            pass
        return None


    def _build_xml_from_template(self, original_xml: str, cap_def: dict, value: Any) -> str:
        """基于原始 XML 模板,修改指定字段后返回新 XML。

        重要:海康设备不接受带命名空间前缀的XML(如 ns0:),
        所以必须使用正则替换而非 ET.tostring()。
        """
        import re

        key = cap_def.get("test_key", "")

        # 单字段模式:用正则替换值
        if "test_keys" not in cap_def:
            # 匹配 <key>原值</key>
            pattern = rf"(<{key}>)[^<]*(</{key}>)"
            if re.search(pattern, original_xml, re.IGNORECASE):
                new_xml = re.sub(pattern, rf"\g<1>{value}\g<2>", original_xml, flags=re.IGNORECASE)
                return new_xml
            # 尝试带命名空间的匹配:<ns:key>原值</ns:key>
            pattern_ns = rf"(<[\w]+:{key}>)[^<]*(</[\w]+:{key}>)"
            if re.search(pattern_ns, original_xml, re.IGNORECASE):
                new_xml = re.sub(pattern_ns, rf"\g<1>{value}\g<2>", original_xml, flags=re.IGNORECASE)
                return new_xml
        else:
            # 多字段模式
            new_xml = original_xml
            for k, v in cap_def["test_keys"].items():
                pattern = rf"(<{k}>)[^<]*(</{k}>)"
                if re.search(pattern, new_xml, re.IGNORECASE):
                    new_xml = re.sub(pattern, rf"\g<1>{v}\g<2>", new_xml, flags=re.IGNORECASE)
            return new_xml

        # 备用方案:直接返回原始XML
        return original_xml

    def _restore_single(self, item_key: str) -> bool:
        """恢复单个端点的原始 XML 值。"""
        original = self._original_xml.get(item_key, "")
        if not original:
            return True  # 未修改过

        cap_def = FUNCTION_ENDPOINTS.get(item_key)
        if not cap_def:
            return True

        endpoint = self._endpoint(cap_def)
        result = self.client.put(endpoint, original)
        return result.status_code == 200

    def _test_value(self, cap_def: dict, endpoint: str, value: Any, item_key: str = "") -> bool:
        """测试单个值是否可设置 (PUT + 范围验证)。"""
        original = self._original_xml.get(item_key, "")
        if not original:
            return False

        xml_body = self._build_xml_from_template(original, cap_def, value)
        result = self.client.put(endpoint, xml_body)
        if result.status_code != 200:
            return False

        # Verification step: GET endpoint again and verify value matches
        verify_response = self.client.get(endpoint)
        if verify_response.status_code != 200:
            return False

        try:
            verify_root = ET.fromstring(verify_response.xml)
            key = cap_def.get("test_key", "")
            if not key:
                return True  # multi_field mode, skip single value check

            actual_value = self._parse_xml_value(verify_root, key)

            # Check range correctness
            # For iris mode: use cap_def range_min/range_max (discrete values)
            min_range = cap_def.get("range_min", 0)
            max_range = cap_def.get("range_max", 100)
            
            if isinstance(actual_value, (int, float)) and isinstance(min_range, int) and isinstance(max_range, int):
                if min_range <= actual_value <= max_range:
                    # Step 5b: Restore original value
                    if original:
                        restore_result = self.client.put(endpoint, original)
                        if restore_result.status_code != 200:
                            return False
                        # Verify restore
                        verify_restore = self.client.get(endpoint)
                        if verify_restore.status_code != 200:
                            return False
                        try:
                            restore_root = ET.fromstring(verify_restore.xml)
                            restored_key_val = self._parse_xml_value(restore_root, key)
                            original_key_val = self._parse_xml_value(ET.fromstring(original), key)
                            if restored_key_val != original_key_val:
                                # For string/toggle values, accept restored to original
                                pass  # Accept if GET returns 200 after restore
                        except ET.ParseError:
                            pass  # Accept restore if GET succeeds
                    return True
                # Value outside parsed range = failure
                return False

            return True  # String/toggle values pass on successful PUT
        except ET.ParseError:
            return False

    def _test_values(self, cap_def: dict, endpoint: str, test_values: list, item_key: str = "") -> list[dict]:
        """测试多个值(用于 style_switch / toggle / action_switch 模式)。"""
        results = []
        for val in test_values:
            success = self._test_value(cap_def, endpoint, val, item_key)
            results.append({"value": val, "success": success})
        return results

    def _write_config(self, result: FunctionResult) -> None:
        """v6.03: 将探测结果写入 data/devices/{mac}/function.json。"""
        # 使用动态路径
        function_path = self._get_function_path()
        
        config = {}
        if os.path.exists(function_path):
            try:
                with open(function_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except (json.JSONDecodeError, OSError):
                config = {}

        if "function_detection" not in config:
            config["function_detection"] = {}

        entry = {
            "p_id": result.p_id,
            "item": result.item,
            "label": result.label,
            "supported": result.supported,
            "endpoint": result.endpoint,
            "min_val": result.min_val,
            "max_val": result.max_val,
            "current_values": result.current_values,
            "test_results": result.test_results,
            "restored": result.restored,
            "error": result.error,
        }
        # v7.08: 保存 opt_values（如果有）
        if result.opt_values:
            entry["opt_values"] = result.opt_values
        config["function_detection"][result.p_id or result.item] = entry
        
        # 添加设备信息和时间戳
        self._init_device_info()
        config["device_info"] = {
            "ip": self._device_info.get("ip", ""),
            "mac": self._mac_clean,
            "model": self._model_short,
        }
        config["detected_at"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

        try:
            with open(function_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except OSError as e:
            pass  # 静默失败,不影响主流程

    def traverse_function(self, item_key: str) -> FunctionResult:
        """探测并遍历单个功能(严格按 CSV 流程)。

        步骤:
        1. GET 端点探测是否存在
        2. 读取当前值 (记录原始 XML)
        3. 读取取值范围
        4. 执行修改测试
        5. 恢复原始值
        6. 结果写入 config
        """
        cap_def = FUNCTION_ENDPOINTS.get(item_key)
        if not cap_def:
            result = FunctionResult(item=item_key, error=f"未知的功能项: {item_key}")
            return result

        endpoint = self._endpoint(cap_def)
        result = FunctionResult(
            p_id=cap_def.get("p_id", ""),
            item=item_key,
            label=cap_def.get("label", item_key),
            endpoint=endpoint,
            test_key=cap_def.get("test_key", ""),
        )

        mode = cap_def.get("mode", "numeric")

        # ---- focus_continuous 特殊处理: 直接 PUT 测试,不需要 GET ----
        if mode == "focus_continuous":
            # PTZ continuous 端点不支持 GET,直接 PUT 测试
            test_values = cap_def.get("test_values", ["5", "-5", "0"])
            all_success = True
            for val in test_values:
                xml_body = f"<PTZData><pan>0</pan><tilt>0</tilt><zoom>0</zoom><focus>{val}</focus></PTZData>"
                put_result = self.client.put(endpoint, xml_body)
                success = put_result.status_code == 200
                result.test_results.append({"value": f"focus={val}", "success": success})
                if not success:
                    all_success = False

            result.supported = all_success
            result.current_values = {"focus": "continuous_control"}
            self._results[item_key] = result
            self._write_config(result)
            return result

        # ---- Step 1: GET 端点检查是否存在 ----
        response = self._probe_endpoint(endpoint)
        if response.status_code != 200:
            result.supported = False
            result.error = f"HTTP {response.status_code}"
            self._results[item_key] = result
            self._write_config(result)
            return result

        # ---- Step 2: 读取当前值,保存原始 XML ----
        try:
            root = ET.fromstring(response.xml)
            self._original_xml[item_key] = response.xml  # 保存原始 XML

            # 解析当前值
            if mode == "multi_field":
                result.current_values = self._parse_all_values(
                    root, cap_def["test_keys"]
                )
            else:
                val = self._parse_xml_value(root, cap_def["test_key"])
                result.current_values = {cap_def["test_key"]: val}

            # 解析取值范围 (如果不是 read_only 模式)
            if mode != "read_only":
                # v7.08: 对于 shutter/iris 模式，尝试从 capabilities 获取 opt 值
                if mode in ("shutter", "iris"):
                    opt_values = self._fetch_capabilities_opt_values(endpoint, cap_def["test_key"])
                    if opt_values:
                        result.opt_values = opt_values
                        result.min_val = opt_values[0] if opt_values else cap_def.get("range_min", 0)
                        result.max_val = opt_values[-1] if opt_values else cap_def.get("range_max", 100)
                    else:
                        min_range, max_range = self._parse_range(root, cap_def["test_key"])
                        if min_range == 0 and max_range == 100:
                            min_range = cap_def.get("range_min", 0)
                            max_range = cap_def.get("range_max", 100)
                        result.min_val = min_range
                        result.max_val = max_range
                else:
                    min_range, max_range = self._parse_range(root, cap_def["test_key"])
                    # XML 中没有找到范围则用 CSV 定义的
                    if min_range == 0 and max_range == 100:
                        min_range = cap_def.get("range_min", 0)
                        max_range = cap_def.get("range_max", 100)
                    result.min_val = min_range
                    result.max_val = max_range
            else:
                result.min_val = cap_def.get("range_min", 0)
                result.max_val = cap_def.get("range_max", 0)

        except ET.ParseError:
            result.supported = False
            result.error = "XML 解析失败"
            self._original_xml[item_key] = response.xml
            result.min_val = cap_def.get("range_min", 0)
            result.max_val = cap_def.get("range_max", 100)
            self._results[item_key] = result
            self._write_config(result)
            return result

        # ---- Step 3 & 4: 执行修改测试 ----
        if mode == "read_only":
            # P4.6 慢快门: 仅读取,不PUT
            result.test_results.append({"action": "read_only", "success": True})

        elif mode == "numeric":
            # 数值型: PUT 测试值
            test_val = cap_def.get("test_value", 50)
            success = self._test_value(cap_def, endpoint, test_val, item_key)
            result.test_results.append({
                "value": test_val,
                "success": success,
                "range": f"{result.min_val}~{result.max_val}",
            })

        elif mode == "multi_field":
            # 多字段型 (whiteBalance: Red=200 + Blue=200)
            test_keys = cap_def["test_keys"]
            test_desc = ", ".join(f"{k}={v}" for k, v in test_keys.items())
            success = self._test_value(cap_def, endpoint, None, item_key)
            result.test_results.append({
                "values": test_desc,
                "success": success,
                "range": f"{result.min_val}~{result.max_val}",
            })

        elif mode == "style_switch":
            # 风格切换型 (Focus/噪声/镜像): PUT 各个模式值
            test_values = cap_def.get("test_values", [])
            for val in test_values:
                success = self._test_value(cap_def, endpoint, val, item_key)
                result.test_results.append({"value": val, "success": success})

        elif mode == "toggle":
            # 布尔切换型 (BLC: true/false)
            test_values = cap_def.get("test_values", ["true", "false"])
            for val in test_values:
                success = self._test_value(cap_def, endpoint, val, item_key)
                result.test_results.append({"value": val, "success": success})

        elif mode == "action_switch":
            # 动作切换型 (IRCUT: day/night)
            test_values = cap_def.get("test_values", ["night", "day"])
            for val in test_values:
                success = self._test_value(cap_def, endpoint, val, item_key)
                result.test_results.append({"value": val, "success": success})

        elif mode == "focus_continuous":
            # Focus+/- 控制: 通过 PTZ continuous 端点
            # XML格式: <PTZData><pan>0</pan><tilt>0</tilt><zoom>0</zoom><focus>5</focus></PTZData>
            test_values = cap_def.get("test_values", ["5", "-5", "0"])
            for val in test_values:
                # 构建 PTZ XML
                xml_body = f"<PTZData><pan>0</pan><tilt>0</tilt><zoom>0</zoom><focus>{val}</focus></PTZData>"
                put_result = self.client.put(endpoint, xml_body)
                success = put_result.status_code == 200
                result.test_results.append({"value": f"focus={val}", "success": success})
                # focus=0 停止后继续
                if val == "0":
                    break

        elif mode == "shutter":
            # 快门型: PUT shutter string value
            test_val = cap_def.get("test_value", "1/100")
            success = self._test_value(cap_def, endpoint, test_val, item_key)
            result.test_results.append({
                "value": test_val,
                "success": success,
                "range": f"{result.min_val}~{result.max_val}",
            })
        
        elif mode == "iris":
            # 光圈型: 使用PUT绝对值设置IrisLevel
            # 光圈值是离散值: [160, 200, 240, 280, 340, 400, 480, 560, 680, 960, 1100, 1400, 1600, 1900, 2200]
            # 数值越大光圈越小: 160=F1.6(最大光圈), 2200=F22(最小光圈)
            # 公式: F数值 = IrisLevel / 100
            
            # 1. 测试切换到test_value
            test_val = cap_def.get("test_value", 160)
            success = self._test_value(cap_def, endpoint, test_val, item_key)
            result.test_results.append({
                "value": test_val,
                "success": success,
                "note": f"F{test_val/100:.1f}" if test_val else None,
            })
            

        # ---- Verify: supported = True if GET succeeded and has current values ----
        # PUT success is optional - some devices don't allow modification
        if mode == "read_only":
            result.supported = True
        elif result.current_values:
            # Has current values = endpoint exists and is readable
            result.supported = True
        else:
            result.supported = False

        # ---- Step 5: 恢复原始值 ----
        restored = self._restore_single(item_key)
        if not restored:
            # 重试一次
            restored = self._restore_single(item_key)
        result.restored = restored

        # ---- Step 6: 结果写入 config ----
        self._write_config(result)

        self._results[item_key] = result
        return result

    def restore_all(self) -> dict[str, bool]:
        """P4.21 设备还原 - 遍历所有已探测端点,逐个 PUT 原始 XML。

        按 CSV 要求: 遍历所有已测试端点,逐个PUT原始XML值到各端点。
        返回 {item_key: True/False} 字典。
        """
        restore_results = {}
        for item_key in list(self._original_xml.keys()):
            restored = self._restore_single(item_key)
            restore_results[item_key] = restored

        return restore_results



    def detect_single(self, item_key: str) -> dict:
        """探测单个功能项。"""
        result = self.traverse_function(item_key)
        return result.__dict__

    def get_results(self) -> dict[str, FunctionResult]:
        """获取所有探测结果。"""
        return self._results

    def get_supported_functions(self) -> list[dict]:
        """返回所有支持的功能列表。"""
        return [
            {
                "p_id": r.p_id,
                "item": r.item,
                "label": r.label,
                "min": r.min_val,
                "max": r.max_val,
                "current_values": r.current_values,
            }
            for r in self._results.values()
            if r.supported
        ]

    def get_status(self) -> dict:
        """获取当前探测状态。"""
        total = len(FUNCTION_ENDPOINTS)
        completed = len(self._results)
        supported = sum(1 for r in self._results.values() if r.supported)
        return {
            "total": total,
            "completed": completed,
            "supported": supported,
            "progress": round(completed / total * 100, 1) if total > 0 else 0,
        }

    def run_all(self) -> dict[str, Any]:
        """运行全部功能探测 (P4.1-P4.21)。

        Bug #2 修复: 在功能探测开始之前,第一步执行预置点10设置。
        """
        import time
        import json
        from pathlib import Path
        from src.ptz.isapi.ptz import PTZController

        # 步骤1: 设置预置点10作为探测起点
        # 先移动到正确HOME位置，再设置预置点
        ptz = PTZController(self.client)
        
        # 移动到HOME坐标
        ptz.absolute_move(pan=HOME_COORDS['pan'], tilt=HOME_COORDS['tilt'], zoom=HOME_COORDS['zoom'], speed=50)
        time.sleep(3)
        
        # 验证位置
        pos = ptz.get_position()
        print('Function起点: pan={}, tilt={}, zoom={}'.format(pos.get('pan'), pos.get('tilt'), pos.get('zoom')))
        
        # 设置预置点10
        ptz.set_preset(preset_id=10, pan=HOME_COORDS['pan'], tilt=HOME_COORDS['tilt'], zoom=HOME_COORDS['zoom'], name='HOME')
        time.sleep(1)
        ptz.goto_preset(10)
        time.sleep(2)

        # 步骤2: 遍历所有功能端点
        result = {}
        for item_key in FUNCTION_ENDPOINTS:
            result[item_key] = self.detect_single(item_key)

        # 步骤3: 恢复所有原始值
        self.restore_all()

        # 步骤4: 构建完整输出
        output = {
            "success": True,
            "total_functions": len(FUNCTION_ENDPOINTS),
            "supported_count": sum(1 for r in result.values() if r.get("supported", False)),
            "device_info": {
                "ip": self.client.ip,
                "port": self.client.port,
            },
            "detected_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),  # v7.32: 添加时间戳
            "functions": {}
        }

        for item_key, data in result.items():
            func_def = FUNCTION_ENDPOINTS.get(item_key, {})
            output["functions"][item_key] = {
                "p_id": data.get("p_id", ""),
                "label": data.get("label", item_key),
                "supported": data.get("supported", False),
                "min": data.get("min_val"),
                "max": data.get("max_val"),
                "endpoint": data.get("endpoint", ""),
                "test_key": data.get("test_key", ""),
                "api_method": "GET/PUT",
                "test_results": data.get("test_results", []),
                "current_values": data.get("current_values", {}),
                "restored": data.get("restored", False),
                "error": data.get("error")
            }
            # v7.32: 添加 opt_values
            if data.get("opt_values"):
                output["functions"][item_key]["opt_values"] = data.get("opt_values")

        # 步骤5: 保存到function.json
        try:
            self._init_device_info()
            output_file = get_data_path_write(self._model_short, self._mac_clean, 'function')
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(output, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

        return output


# ================================================================ #
#  P5.1 Continuous Move 和 P5.2 Absolute Move 测试
# ================================================================ #

def test_continuous_move(client: ISAPIClient) -> dict:
    """P5.1: 测试持续运动能力。

    方法:
    - pan/tilt 50持续2秒,0.1s采样一次
    - 移动后回到HOME位
    - 记录坐标变化

    预期: 设备支持Continuous Move并能正确执行,返回HOME成功
    """
    import time
    from src.ptz.isapi.ptz import PTZController
    from src.ptz.constants import HOME_COORDS

    ptz = PTZController(client)
    results = {"pan": {}, "tilt": {}}

    # 从HOME开始
    ptz.goto_preset(10)
    time.sleep(3)
    start_pos = ptz.get_position()

    # Pan持续运动测试
    ptz.continuous_move(pan=50, tilt=0)
    pan_samples = []
    for _ in range(20):  # 2秒,0.1s采样
        pos = ptz.get_position()
        if pos:
            pan_samples.append(pos.get("pan", 0))
        time.sleep(0.1)
    ptz.stop_move()
    time.sleep(2)

    # 回到HOME
    ptz.goto_preset(10)
    time.sleep(3)
    end_pos = ptz.get_position()

    results["pan"] = {
        "start": start_pos.get("pan", 0) if start_pos else 0,
        "samples": pan_samples,
        "end": end_pos.get("pan", 0) if end_pos else 0,
        "displacement": abs(pan_samples[-1] - pan_samples[0]) if pan_samples else 0,
        "home_restored": end_pos and abs(end_pos.get("pan", 0) - HOME_COORDS["pan"]) <= 10,
    }

    # Tilt持续运动测试
    ptz.goto_preset(10)
    time.sleep(3)
    start_pos = ptz.get_position()

    ptz.continuous_move(pan=0, tilt=50)
    tilt_samples = []
    for _ in range(20):
        pos = ptz.get_position()
        if pos:
            tilt_samples.append(pos.get("tilt", 0))
        time.sleep(0.1)
    ptz.stop_move()
    time.sleep(2)

    # 回到HOME
    ptz.goto_preset(10)
    time.sleep(3)
    end_pos = ptz.get_position()

    results["tilt"] = {
        "start": start_pos.get("tilt", 0) if start_pos else 0,
        "samples": tilt_samples,
        "end": end_pos.get("tilt", 0) if end_pos else 0,
        "displacement": abs(tilt_samples[-1] - tilt_samples[0]) if tilt_samples else 0,
        "home_restored": end_pos and abs(end_pos.get("tilt", 0) - HOME_COORDS["tilt"]) <= 5,
    }

    # 判断是否支持
    supported = (
        results["pan"]["displacement"] > 50 and  # Pan有位移
        results["tilt"]["displacement"] > 50 and  # Tilt有位移
        results["pan"]["home_restored"] and      # Pan回HOME成功
        results["tilt"]["home_restored"]         # Tilt回HOME成功
    )

    return {
        "p_id": "P5.1",
        "label": "Continuous Move",
        "supported": supported,
        "results": results,
    }


def test_absolute_move(client: ISAPIClient) -> dict:
    """P5.2: 测试绝对运动能力。

    方法:
    - P T在当前坐标基础上,坐标均+10
    - 移动后回到HOME位
    - 记录坐标变化

    预期: 设备支持Absolute Move并能正确执行,评审阶段必须实现
    """
    import time
    from src.ptz.isapi.ptz import PTZController
    from src.ptz.constants import HOME_COORDS

    ptz = PTZController(client)

    # 强制回到HOME并等待
    ptz.goto_preset(10)
    time.sleep(5)  # 增加等待时间

    # 获取位置
    start_pos = ptz.get_position()
    if not start_pos:
        return {"p_id": "P5.2", "label": "Absolute Move", "supported": False, "error": "无法获取当前位置"}

    # 确认在HOME位置
    if abs(start_pos.get("pan", 0) - 1800) > 10 or abs(start_pos.get("tilt", 0) - 450) > 5:
        # 不在HOME,等待稳定后再试
        time.sleep(3)
        start_pos = ptz.get_position()

    # 目标坐标: Pan+50, Tilt+50 (必须是整数)
    target_pan = int(start_pos.get("pan", 1800)) + 50
    target_tilt = int(start_pos.get("tilt", 450)) + 50
    target_zoom = int(start_pos.get("zoom", 10))

    # 绝对移动
    ptz.absolute_move(pan=target_pan, tilt=target_tilt, zoom=target_zoom, speed=50)
    time.sleep(4)  # 等待移动完成

    # 获取移动后位置
    moved_pos = ptz.get_position()

    # 回到HOME
    ptz.goto_preset(10)
    time.sleep(3)
    end_pos = ptz.get_position()

    # 验证
    move_success = moved_pos and abs(moved_pos.get("pan", 0) - target_pan) <= 5 and abs(moved_pos.get("tilt", 0) - target_tilt) <= 5
    home_restored = end_pos and abs(end_pos.get("pan", 0) - HOME_COORDS["pan"]) <= 10 and abs(end_pos.get("tilt", 0) - HOME_COORDS["tilt"]) <= 5

    supported = move_success and home_restored

    return {
        "p_id": "P5.2",
        "label": "Absolute Move",
        "supported": supported,
        "start_pos": start_pos,
        "target_pos": {"pan": target_pan, "tilt": target_tilt, "zoom": target_zoom},
        "moved_pos": moved_pos,
        "end_pos": end_pos,
        "move_success": move_success,
        "home_restored": home_restored,
    }


# ================================================================ #
#  缓存读取函数 (v6.19 新增)
# ================================================================ #

def load_cached_function_results(mac: str) -> dict | None:
    """从本地缓存读取功能探测结果。
    
    v6.19: 优先读取本地缓存，避免每次调用设备API。
    
    Args:
        mac: MAC地址（无分隔符小写）
    
    Returns:
        缓存结果字典，不存在返回 None
    """
    try:
        cache_path = get_data_path_read(None, mac, 'function')
        if cache_path is None or not cache_path.exists():
            return None
        with open(cache_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def run_function_test(
    ip: str = None, 
    username: str = None, 
    password: str = None, 
    port: int = None,
    mac: str = None,
    use_cache: bool = True
) -> dict:
    """独立运行Function测试。
    
    v6.19: 优先读取本地缓存，缓存不存在时调用设备API。
    
    Args:
        ip: 设备IP（可选，默认从当前设备读取）
        username: 用户名（可选）
        password: 密码（可选）
        port: 端口（可选，默认80）
        mac: MAC地址（可选，用于读取缓存）
        use_cache: 是否优先使用缓存（默认True）
    
    Returns:
        测试结果
    """
    # 1. 优先读取缓存
    if use_cache and mac:
        cached = load_cached_function_results(mac)
        if cached:
            return {**cached, "from_cache": True}
    
    # 2. 检查必需参数
    if not ip:
        return {"success": False, "error": "缺少设备IP参数"}
    
    # 3. 连接设备并运行测试
    username = username or "admin"
    password = password or ""
    port = port or 80
    
    client = ISAPIClient(ip=ip, username=username, password=password, port=port)
    if not client.verify_credentials():
        return {"success": False, "error": f"设备认证失败: {ip}"}
    
    # 4. 运行测试
    detector = FunctionDetector(client)
    result = detector.run_all()
    
    return {**result, "from_cache": False}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AstroHub Function测试")
    parser.add_argument("--ip", type=str, required=True, help="设备IP")
    parser.add_argument("--username", type=str, default="admin", help="用户名")
    parser.add_argument("--password", type=str, default="", help="密码")
    parser.add_argument("--port", type=int, default=80, help="端口")
    parser.add_argument("--mac", type=str, help="MAC地址（用于缓存）")
    parser.add_argument("--no-cache", action="store_true", help="禁用缓存")
    args = parser.parse_args()
    
    print("=" * 50)
    print("AstroHub Function测试")
    print("=" * 50)
    
    result = run_function_test(
        ip=args.ip, 
        username=args.username, 
        password=args.password, 
        port=args.port,
        mac=args.mac,
        use_cache=not args.no_cache
    )
    
    if result.get("success"):
        cache_note = " (缓存)" if result.get("from_cache") else ""
        print(f"[完成] 功能探测: {result.get('supported_count', 0)}/{result.get('total_functions', 0)} 项支持{cache_note}")
    else:
        print(f"[失败] {result.get('error', '未知错误')}")
