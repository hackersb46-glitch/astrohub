"""
M2 Device Manager v1.0 - MAC地址验证与格式化工具

提供MAC地址验证、标准化、格式化功能。
支持格式：AA:BB:CC:DD:EE:FF, AA-BB-CC-DD-EE-FF, AABBCCDDEEFF
"""

import re

from device.constants import MAC_PATTERN


def normalize_mac(mac: str) -> str:
    """标准化MAC地址为大写冒号格式。

    示例:
        aa-bb-cc-dd-ee-ff → AA:BB:CC:DD:EE:FF
        AABBCCDDEEFF → AA:BB:CC:DD:EE:FF
        AA:BB:CC:DD:EE:FF → AA:BB:CC:DD:EE:FF

    Args:
        mac: 原始MAC地址字符串

    Returns:
        标准化后的MAC地址 (AA:BB:CC:DD:EE:FF格式)
    """
    cleaned = mac.strip().replace("-", ":").upper()
    # 如果是12位连续十六进制（无分隔符），插入冒号
    if ":" not in cleaned and len(cleaned) == 12:
        cleaned = ":".join(cleaned[i:i+2] for i in range(0, 12, 2))
    return cleaned


def validate_mac(mac: str) -> tuple[bool, str]:
    """验证MAC地址格式是否正确。

    支持的格式:
        - AA:BB:CC:DD:EE:FF (冒号分隔)
        - AA-BB-CC-DD-EE-FF (横杠分隔)
        - AABBCCDDEEFF (无分隔符，12位十六进制)

    Args:
        mac: 待验证的MAC地址

    Returns:
        (is_valid, error_message): 验证结果和错误描述
    """
    if not mac or not mac.strip():
        return False, "MAC地址不能为空"

    mac_stripped = mac.strip()

    # 检查是否为12位纯十六进制
    if len(mac_stripped.replace("-", "").replace(":", "")) != 12:
        return False, f"MAC地址长度错误: '{mac_stripped}'，应为12位十六进制字符"

    # 使用正则匹配完整格式
    if re.match(MAC_PATTERN, mac_stripped):
        return True, ""

    # 检查是否只包含十六进制字符和允许的分隔符
    cleaned = mac_stripped.replace("-", "").replace(":", "")
    if not re.match(r"^[0-9A-Fa-f]+$", cleaned):
        return False, f"MAC地址包含非法字符: '{mac_stripped}'，仅允许十六进制字符(0-9, A-F)和分隔符(:/-)"

    return False, f"MAC地址格式错误: '{mac_stripped}'，支持格式: AA:BB:CC:DD:EE:FF 或 AA-BB-CC-DD-EE-FF 或 AABBCCDDEEFF"


def check_mac_format(mac: str) -> str:
    """检测MAC地址的当前格式类型。

    Args:
        mac: MAC地址字符串

    Returns:
        'colon' | 'dash' | 'compact' | 'unknown'
    """
    mac = mac.strip()
    if ":" in mac:
        return "colon"
    elif "-" in mac:
        return "dash"
    elif len(mac) == 12:
        return "compact"
    return "unknown"


def mac_to_raw(mac: str) -> str:
    """将MAC地址转换为纯十六进制字符串（无分隔符）。

    Args:
        mac: MAC地址

    Returns:
        纯十六进制字符串 (如: AABBCCDDEEFF)
    """
    return normalize_mac(mac).replace(":", "")
