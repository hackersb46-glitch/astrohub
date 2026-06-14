"""
M2 Device Manager v1.0 - ISAPI 配置管理

设备配置文件的读写(P2.1、P2.2)。
通过ISAPI接口读取/写入设备配置，支持写入失败自动回滚。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from device.constants import HTTP_STATUS_DESCRIPTION
from device.core.logger import LOG
from device.isapi.client import ISAPIClient


def _strip_ns(tag: str) -> str:
    """Remove XML namespace from tag, e.g. '{http://foo}bar' -> 'bar'."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


class ConfigManager:
    """ISAPI 配置管理器，支持读取、写入(含回滚)设备配置。

    Args:
        client: ISAPIClient 实例
    """

    def __init__(self, client: ISAPIClient) -> None:
        self._client = client

    # ------------------------------------------------------------------ #
    #  P2.1 - 读取配置
    # ------------------------------------------------------------------ #
    def read_config(self) -> dict:
        """读取设备当前配置。

        Returns:
            dict 包含 success, config(或error), response_time_ms
        """
        result = self._client.get("/System/configuration")

        if result.status_code == 200:
            config = self._xml_to_dict(result.xml)
            LOG.done("配置读取成功")
            return {
                "success": True,
                "config": config,
                "response_time_ms": result.response_time_ms,
            }

        desc = HTTP_STATUS_DESCRIPTION.get(
            result.status_code, f"HTTP {result.status_code}"
        )
        return {
            "success": False,
            "error": f"读取配置失败: {desc}",
            "status_code": result.status_code,
            "response_time_ms": result.response_time_ms,
        }

    # ------------------------------------------------------------------ #
    #  P2.2 - 写入配置(带回滚)
    # ------------------------------------------------------------------ #
    def write_config(self, config: dict) -> dict:
        """写入设备配置，写入失败自动回滚。

        Args:
            config: 配置字典

        Returns:
            dict 包含 success, (可选error/status_code), response_time_ms
        """
        # Step 1: Save current config for rollback
        previous = self._client.get("/System/configuration")
        previous_xml = previous.xml if previous.status_code == 200 else None

        # Step 2: Write new config
        xml_body = self._dict_to_xml(config)
        result = self._client.put("/System/configuration", xml_body)

        # Step 3: Verify
        if self._verify_config(config):
            LOG.done("配置写入并验证成功")
            return {
                "success": True,
                "response_time_ms": result.response_time_ms,
            }

        # Step 4: Rollback on failure
        verify_result = self._client.get("/System/configuration")
        if previous_xml is not None:
            self._client.put("/System/configuration", previous_xml)
            LOG.warning("配置写入失败，已回滚到上一版本")

        return {
            "success": False,
            "error": "配置写入后验证失败，已回滚",
            "status_code": verify_result.status_code,
            "response_time_ms": result.response_time_ms,
        }

    # ------------------------------------------------------------------ #
    #  XML <-> dict 转换
    # ------------------------------------------------------------------ #
    @staticmethod
    def _xml_to_dict(xml_str: str) -> dict:
        """将 XML 字符串解析为嵌套字典。

        Args:
            xml_str: XML 字符串

        Returns:
            嵌套字典
        """
        root = ET.fromstring(xml_str)

        def parse_element(element: ET.Element) -> Any:
            children = list(element)
            tag = _strip_ns(element.tag)

            if not children:
                # Leaf node - return text value
                text = (element.text or "").strip()
                return text if text else ""

            # Node with children - build dict
            result: dict[str, Any] = {}
            for child in children:
                child_tag = _strip_ns(child.tag)
                child_value = parse_element(child)

                # Handle repeated elements as lists
                if child_tag in result:
                    existing = result[child_tag]
                    if not isinstance(existing, list):
                        result[child_tag] = [existing]
                    result[child_tag].append(child_value)
                else:
                    result[child_tag] = child_value

            return result

        root_tag = _strip_ns(root.tag)
        return {root_tag: parse_element(root)}

    @staticmethod
    def _dict_to_xml(config: dict, root_tag: str = "cfg") -> str:
        """将嵌套字典序列化为 XML 字符串。

        Args:
            config: 配置字典
            root_tag: 根元素标签

        Returns:
            XML 字符串(含UTF-8声明)
        """

        def build_element(parent: ET.Element, data: Any) -> None:
            if isinstance(data, dict):
                for key, value in data.items():
                    child = ET.SubElement(parent, key)
                    build_element(child, value)
            elif isinstance(data, list):
                for item in data:
                    # Use parent tag for repeated items
                    child = ET.SubElement(parent, parent.tag)
                    build_element(child, item)
            else:
                parent.text = str(data) if data is not None else ""

        root = ET.Element(root_tag)
        # If config has a single top-level key, use it as root_tag
        if isinstance(config, dict) and len(config) == 1:
            root_tag = list(config.keys())[0]
            root = ET.Element(root_tag)
            build_element(root, config[root_tag])
        elif isinstance(config, dict):
            build_element(root, config)

        xml_str = ET.tostring(root, encoding="unicode", xml_declaration=True)
        # ET.tostring with encoding="unicode" doesn't add declaration
        # So we prepend it manually
        if not xml_str.startswith("<?xml"):
            xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str
        return xml_str

    # ------------------------------------------------------------------ #
    #  配置验证
    # ------------------------------------------------------------------ #
    def _verify_config(self, expected_config: dict) -> bool:
        """验证设备当前配置是否与期望配置一致。

        Args:
            expected_config: 期望的配置字典

        Returns:
            True 如果配置匹配
        """
        result = self._client.get("/System/configuration")
        if result.status_code != 200:
            return False

        current = self._xml_to_dict(result.xml)
        expected_normalized = self._normalize_config(expected_config)

        return self._dicts_equal(current, expected_normalized)

    @staticmethod
    def _normalize_config(config: dict) -> dict:
        """Normalize config dict for comparison.

        If config is like {"Cfg": {...}}, extract and use as-is.
        Otherwise wrap in a common structure.
        """
        if isinstance(config, dict) and len(config) == 1:
            return config
        # Wrap in a generic root tag for consistent comparison
        return {"cfg": config}

    @staticmethod
    def _dicts_equal(d1: Any, d2: Any) -> bool:
        """递归比较两个字典(或值)是否相等。

        Handles dicts, lists, and leaf values.
        """
        if type(d1) is not type(d2):
            # Both None should be equal
            if d1 is None and d2 is None:
                return True
            return False

        if isinstance(d1, dict):
            if set(d1.keys()) != set(d2.keys()):
                return False
            return all(ConfigManager._dicts_equal(d1[k], d2[k]) for k in d1)

        if isinstance(d1, list):
            if len(d1) != len(d2):
                return False
            return all(ConfigManager._dicts_equal(a, b) for a, b in zip(d1, d2))

        return d1 == d2
