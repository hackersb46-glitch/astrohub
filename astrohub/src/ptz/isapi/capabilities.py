"""
PTZ_ASTRO v1.1 - ISAPI 能力探测模块
探测 21 个设备能力端点，获取取值范围，测试后还原。
严格按 doc/review/M1_method.csv P4.1-P4.21 定义。

Author: 雅痞张@南方天文
"""

import xml.etree.ElementTree as ET

from .client import ISAPIClient, ISAPIResponse
from src.ptz.core.logger import LOG
from src.ptz.constants import ISAPI_CHANNEL


# === 能力端点定义 (严格按 M1_method.csv) ===
# 每个能力: 端点, test_key, min, max, test_value, label, mode
CAPABILITIES = {
    # --- P4.1 IrLED 红外补光 ---
    "ir_led": {
        "endpoint": "/Image/channels/{ch}/IrLight",
        "test_key": "brightnessLimit",
        "min_val": 1,
        "max_val": 100,
        "test_val": 50,
        "label": "IrLED 红外补光",
        "mode": "numeric",
    },
    # --- P4.2 白光灯 ---
    "white_balance": {
        "endpoint": "/Image/channels/{ch}/whiteBalance",
        "test_key": "WhiteBalanceRed",
        "min_val": 0,
        "max_val": 255,
        "test_val": 200,
        "label": "白平衡",
        "mode": "multi_field",
        "test_keys": {"WhiteBalanceRed": 200, "WhiteBalanceBlue": 200},
    },
    # --- P4.3 Gain 模拟增益 ---
    "gain": {
        "endpoint": "/Image/channels/{ch}/gain",
        "test_key": "GainLevel",
        "min_val": 0,
        "max_val": 100,
        "test_val": 50,
        "label": "Gain 模拟增益",
        "mode": "numeric",
    },
    # --- P4.4 Focus 聚焦 ---
    "focus": {
        "endpoint": "/Image/channels/{ch}/focusConfiguration",
        "test_key": "focusStyle",
        "min_val": 0,
        "max_val": 0,
        "test_val": "MANUAL",
        "label": "Focus 聚焦",
        "mode": "style_switch",
        "test_values": ["MANUAL", "SEMIAUTOMATIC", "AUTOMATIC"],
    },
    # --- P4.5 快门速度（手动模式） ---
    "shutter": {
        "endpoint": "/Image/channels/{ch}/Shutter",
        "test_key": "ShutterLevel",
        "min_val": "1/30000",
        "max_val": "1/25",
        "test_val": "1/100",
        "label": "快门速度（手动模式）",
        "mode": "shutter",
    },
    # --- P4.6 慢快门 ---
    "slow_shutter": {
        "endpoint": "/Image/channels/{ch}/Shutter",
        "test_key": "minShutterLevelLimit",
        "min_val": "1/30000",
        "max_val": "1/25",
        "test_val": None,  # 仅读取不PUT
        "label": "慢快门",
        "mode": "read_only",
    },
    # --- P4.7 光圈 Iris ---
    "iris": {
        "endpoint": "/Image/channels/{ch}/Iris",
        "test_key": "IrisLevel",
        "min_val": 0,
        "max_val": 400,
        "test_val": 50,
        "label": "光圈 Iris",
        "mode": "numeric",
    },
    # --- P4.8 快门速度(重复端点) ---
    "shutter_repeat": {
        "endpoint": "/Image/channels/{ch}/Shutter",
        "test_key": "ShutterLevel",
        "min_val": "1/30000",
        "max_val": "1/25",
        "test_val": "1/50",
        "label": "快门速度",
        "mode": "shutter",
    },
    # --- P4.9 数字降噪-时域 ---
    "dnr_temporal": {
        "endpoint": "/Image/channels/{ch}/noiseReduce",
        "test_key": "mode",
        "min_val": 0,
        "max_val": 0,
        "test_val": "auto",
        "label": "数字降噪-时域",
        "mode": "style_switch",
        "test_values": ["auto", "close"],
    },
    # --- P4.10 数字降噪-空域 ---
    "dnr_spatial": {
        "endpoint": "/Image/channels/{ch}/noiseReduce",
        "test_key": "mode",
        "min_val": 0,
        "max_val": 0,
        "test_val": "auto",
        "label": "数字降噪-空域",
        "mode": "style_switch",
        "test_values": ["auto", "close"],
    },
    # --- P4.11 IRCUT 滤波片/日夜转换 ---
    "ircut": {
        "endpoint": "/Image/channels/{ch}/IrcutFilter",
        "test_key": "IrcutFilterAction",
        "min_val": 1,
        "max_val": 7,  # nightToDayFilterLevel range
        "test_val": "night",
        "label": "IRCUT 滤波片/日夜转换",
        "mode": "action_switch",
        "test_values": ["night", "day"],
    },
    # --- P4.12 WDR 宽动态 ---
    "wdr": {
        "endpoint": "/Image/channels/{ch}/WDR",
        "test_key": "WDRLevel",
        "min_val": 0,
        "max_val": 100,
        "test_val": 80,
        "label": "WDR 宽动态",
        "mode": "numeric",
    },
    # --- P4.13 BLC 背光补偿 ---
    "blc": {
        "endpoint": "/Image/channels/{ch}/BLC",
        "test_key": "enabled",
        "min_val": 0,
        "max_val": 1,
        "test_val": "true",
        "label": "BLC 背光补偿",
        "mode": "toggle",
        "test_values": ["true", "false"],
    },
    # --- P4.14 Dehaze 除雾 ---
    "dehaze": {
        "endpoint": "/Image/channels/{ch}/dehaze",
        "test_key": "DehazeLevel",
        "min_val": 0,
        "max_val": 100,
        "test_val": 80,
        "label": "Dehaze 除雾",
        "mode": "numeric",
    },
    # --- P4.15 Sharpness 锐度 ---
    "sharpness": {
        "endpoint": "/Image/channels/{ch}/Sharpness",
        "test_key": "SharpnessLevel",
        "min_val": 0,
        "max_val": 100,
        "test_val": 80,
        "label": "Sharpness 锐度",
        "mode": "numeric",
    },
    # --- P4.16 亮度 ---
    "brightness": {
        "endpoint": "/Image/channels/{ch}/color",
        "test_key": "brightnessLevel",
        "min_val": 0,
        "max_val": 100,
        "test_val": 80,
        "label": "亮度",
        "mode": "numeric",
    },
    # --- P4.17 饱和度 ---
    "saturation": {
        "endpoint": "/Image/channels/{ch}/color",
        "test_key": "saturationLevel",
        "min_val": 0,
        "max_val": 100,
        "test_val": 80,
        "label": "饱和度",
        "mode": "numeric",
    },
    # --- P4.18 对比度 ---
    "contrast": {
        "endpoint": "/Image/channels/{ch}/color",
        "test_key": "contrastLevel",
        "min_val": 0,
        "max_val": 100,
        "test_val": 80,
        "label": "对比度",
        "mode": "numeric",
    },
    # --- P4.19 Sharpness 锐度 (CSV重复项) ---
    "sharpness_repeat": {
        "endpoint": "/Image/channels/{ch}/Sharpness",
        "test_key": "SharpnessLevel",
        "min_val": 0,
        "max_val": 100,
        "test_val": 80,
        "label": "Sharpness 锐度 (P4.19)",
        "mode": "numeric",
    },
    # --- P4.20 Mirror 镜像 ---
    "mirror": {
        "endpoint": "/Image/channels/{ch}/ImageFlip",
        "test_key": "ImageFlipStyle",
        "min_val": 0,
        "max_val": 0,
        "test_val": "LEFTRIGHT",
        "label": "Mirror 镜像",
        "mode": "style_switch",
        "test_values": ["LEFTRIGHT", "UPDOWN", "CENTER", "AUTO"],
    },
    # --- P4.21 设备还原 ---
    "restore_all": {
        "endpoint": "N/A (遍历所有端点)",
        "test_key": "",
        "min_val": 0,
        "max_val": 0,
        "test_val": None,
        "label": "设备还原",
        "mode": "restore",
    },
    # --- P2 OSD 开关 ---
    "osd_overlay": {
        "endpoint": "/Image/channels/{ch}/Overlays",
        "test_key": "enabled",
        "min_val": 0,
        "max_val": 1,
        "test_val": "true",
        "label": "OSD 开关",
        "mode": "toggle",
        "test_values": ["true", "false"],
    },
    # --- P4 PTZCtrl 能力探测 ---
    "ptz_functions": {
        "endpoint": "/PTZCtrl/capabilities",
        "test_key": "supportedPTZFunction",
        "min_val": 0,
        "max_val": 0,
        "test_val": None,
        "label": "PTZ 能力探测",
        "mode": "read_only",
    },
}


class CapabilityDetector:
    """设备能力探测器。"""

    def __init__(self, client: ISAPIClient) -> None:
        self.client = client
        self.channel = ISAPI_CHANNEL
        self.capabilities: dict = {}
        self._original_values: dict = {}

    def _get_endpoint(self, cap_def: dict) -> str:
        """获取带 channel 的端点路径。"""
        return cap_def["endpoint"].format(ch=self.channel)

    def _find_xml_range(self, xml_text: str, key: str, cap_def: dict) -> dict:
        """从 XML 响应中提取 min/max 范围。"""
        result = {
            "supported": False,
            "min": cap_def["min_val"],
            "max": cap_def["max_val"],
            "value": 0,
        }

        try:
            root = ET.fromstring(xml_text)
            # 查找包含 key 的元素
            for elem in root.iter():
                tag_lower = elem.tag.split("}")[-1].lower()
                if key.lower() in tag_lower:
                    result["supported"] = True
                    if elem.text:
                        try:
                            result["value"] = int(elem.text.strip())
                        except ValueError:
                            result["value"] = 0

            # 尝试查找 min/max 范围
            for elem in root.iter():
                tag_lower = elem.tag.split("}")[-1].lower()
                if "min" in tag_lower and elem.text:
                    try:
                        result["min"] = int(elem.text.strip())
                    except ValueError:
                        pass
                if "max" in tag_lower and elem.text:
                    try:
                        result["max"] = int(elem.text.strip())
                    except ValueError:
                        pass
        except ET.ParseError:
            pass

        return result

    def check_endpoint_exists(self, endpoint: str) -> bool:
        """检查 ISAPI 端点是否存在（HTTP 200）。"""
        result = self.client.get(endpoint)
        return result.status_code == 200

    def detect_capability(self, cap_key: str) -> dict:
        """检测单个能力。

        步骤:
        1. GET 端点，检查是否存在
        2. 解析 min/max 范围
        3. 保存原始值
        4. PUT 测试值 (委托给 test_capability)
        5. PUT 恢复原始值
        """
        cap_def = CAPABILITIES.get(cap_key)
        if not cap_def:
            LOG.log("warning", f"未知能力: {cap_key}")
            return {"supported": False}

        endpoint = self._get_endpoint(cap_def)
        LOG.log("info", f"检测能力: {cap_def['label']} ({endpoint})")

        mode = cap_def.get("mode", "numeric")

        cap_info = {
            "label": cap_def["label"],
            "supported": False,
            "min": cap_def["min_val"],
            "max": cap_def["max_val"],
            "original_value": 0,
            "endpoint": endpoint,
            "test_key": cap_def["test_key"],
            "mode": mode,
            "p_id": cap_def.get("p_id", ""),
        }

        if mode == "restore":
            # P4.21 设备还原 - 跳过端点检测，交给 restore_all 处理
            cap_info["supported"] = True
            self.capabilities[cap_key] = cap_info
            return cap_info

        # Step 1: GET 端点
        result = self.client.get(endpoint)

        if result.status_code != 200:
            LOG.log("info", f"  → {cap_def['label']} 不支持 (HTTP {result.status_code})")
            cap_info["supported"] = False
            self.capabilities[cap_key] = cap_info
            return cap_info

        # Step 2: 解析原始值
        range_info = self._find_xml_range(result.xml, cap_def["test_key"], cap_def)
        cap_info["original_value"] = range_info["value"]
        cap_info["min"] = range_info.get("min", cap_def["min_val"])
        cap_info["max"] = range_info.get("max", cap_def["max_val"])
        cap_info["supported"] = True

        LOG.log("info", f"  → {cap_def['label']} 支持，当前值={range_info['value']}")

        # Step 3: 保存原始值
        self._original_values[cap_key] = result.xml

        # Step 4 & 5: PUT 测试值 + 恢复原始值
        self.test_capability(cap_key)

        return cap_info

    def detect_all(self) -> dict:
        """检测所有 21 个能力端点。

        返回:
            {cap_key: cap_info} 字典
        """
        LOG.log("info", "=== 开始设备能力探测 (21 个端点) ===")

        for cap_key, cap_def in CAPABILITIES.items():
            cap_info = self.detect_capability(cap_key)
            status = "✓" if cap_info["supported"] else "✗"
            value_info = f" 值={cap_info.get('original_value', 0)}" if cap_info["supported"] else ""
            LOG.log("info", f"  {status} {cap_def['label']}{value_info}")

        supported_count = sum(1 for c in self.capabilities.values() if c.get("supported"))
        LOG.log("done", f"能力探测完成: {supported_count}/{len(CAPABILITIES)} 个能力支持")

        return self.capabilities

    def test_capability(self, cap_key: str, test_value=None) -> bool:
        """测试单个能力（修改值然后还原）。

        返回:
            True = 测试成功并还原，False = 失败
        """
        cap_info = self.capabilities.get(cap_key)
        if not cap_info or not cap_info.get("supported"):
            LOG.log("warning", f"能力不支持: {cap_key}")
            return False

        cap_def = CAPABILITIES.get(cap_key)
        if not cap_def:
            return False

        mode = cap_def.get("mode", "numeric")
        original_xml = self._original_values.get(cap_key, "")
        if not original_xml:
            LOG.log("warning", f"无原始值可还原: {cap_key}")
            return False

        endpoint = cap_info["endpoint"]
        LOG.log("info", f"测试能力: {cap_def['label']}")

        if mode == "read_only":
            LOG.log("done", f"  → {cap_def['label']} 为 read_only，跳过 PUT 测试")
            return True

        # PUT 测试值
        test_values = cap_def.get("test_values")
        test_val = test_value if test_value is not None else cap_def.get("test_val")

        if test_values:
            # style_switch / toggle / action_switch: 测试多个值
            all_ok = True
            for val in test_values:
                xml_body = self._build_xml_from_template(original_xml, cap_def, val)
                result = self.client.put(endpoint, xml_body)
                if result.status_code != 200:
                    all_ok = False
                    LOG.log("warning", f"  → PUT {val} 失败 (HTTP {result.status_code})")
            if all_ok:
                LOG.log("done", f"  → {cap_def['label']} 所有模式测试通过")
        else:
            # numeric / shutter / multi_field: 测试单个值
            if isinstance(test_val, str) and "/" in test_val:
                xml_body = self._build_xml_from_template(original_xml, cap_def, test_val)
            else:
                xml_body = self._build_xml_from_template(original_xml, cap_def, test_val)
            result = self.client.put(endpoint, xml_body)
            if result.status_code == 200:
                LOG.log("done", f"  → {cap_def['label']} 测试通过")
            else:
                LOG.log("warning", f"  → {cap_def['label']} 测试失败 (HTTP {result.status_code})")
                return False

        # 还原原始值
        put_result = self.client.put(endpoint, original_xml)
        if put_result.status_code == 200:
            LOG.log("done", f"  → {cap_def['label']} 已还原")
            return True
        else:
            LOG.log("warning", f"  → {cap_def['label']} 还原失败 (HTTP {put_result.status_code})")
            return False

    def _build_xml_from_template(self, original_xml: str, cap_def: dict, value) -> str:
        """基于原始 XML 模板，修改指定字段后返回新 XML。"""
        try:
            root = ET.fromstring(original_xml)

            if "test_keys" in cap_def:
                # 多字段模式 (如 whiteBalance)
                for k, v in cap_def["test_keys"].items():
                    for elem in root.iter():
                        local_name = elem.tag.split("}")[-1].lower()
                        if local_name == k.lower():
                            elem.text = str(v)
                            break
            else:
                key = cap_def.get("test_key", "")
                for elem in root.iter():
                    local_name = elem.tag.split("}")[-1].lower()
                    if local_name == key.lower():
                        elem.text = str(value)
                        break

            return ET.tostring(root, encoding="unicode", xml_declaration=False)
        except ET.ParseError:
            return original_xml

    def restore_all(self) -> bool:
        """还原所有能力原始值 (P4.21)。

        返回:
            True = 全部还原成功
        """
        LOG.log("info", "=== 开始还原所有设备参数 ===")

        all_restored = True
        for cap_key, original_xml in self._original_values.items():
            cap_info = self.capabilities.get(cap_key)
            if not cap_info:
                continue

            result = self.client.put(cap_info["endpoint"], original_xml)
            if result.status_code == 200:
                LOG.log("done", f"  → {cap_info['label']} 已还原")
            else:
                LOG.log("warning", f"  → {cap_info['label']} 还原失败 (HTTP {result.status_code})")
                all_restored = False

        if all_restored:
            LOG.log("done", "所有设备参数已还原")
        else:
            LOG.log("warning", "部分设备参数还原失败")

        return all_restored
