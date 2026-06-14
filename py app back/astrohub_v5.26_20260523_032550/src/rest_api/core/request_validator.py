"""
M7 REST API v1.0 - 请求校验器

实现:
- MAC 地址格式校验
- 请求体字段校验
- Path 参数校验
- 查询参数校验

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import re

from rest_api.constants import MAC_PATTERN, ErrorCode, ERROR_CODE_DESCRIPTION


# ------------------------------------------------------------------ #
#  MAC 地址校验
# ------------------------------------------------------------------ #

_MAC_RE = re.compile(MAC_PATTERN)


def validate_mac(mac: str) -> tuple[bool, dict | None]:
    """校验 MAC 地址格式。

    支持格式:
        - XX:XX:XX:XX:XX:XX (冒号分隔)
        - XX-XX-XX-XX-XX-XX (短横线分隔)

    Args:
        mac: MAC 地址字符串

    Returns:
        (是否有效, 错误信息 dict 或 None)

    Examples:
        >>> validate_mac("28:57:BE:00:11:22")
        (True, None)
        >>> validate_mac("invalid")
        (False, {"error": {...}})
    """
    mac_normalized = mac.replace("-", ":").upper()
    if _MAC_RE.match(mac_normalized):
        return True, None

    return False, _validation_error(
        code=ErrorCode.VALIDATION_ERROR,
        field="mac",
        message=f"MAC 地址格式无效: {mac}。预期格式: XX:XX:XX:XX:XX:XX",
    )


def normalize_mac(mac: str) -> str:
    """标准化 MAC 地址为 XX:XX:XX:XX:XX:XX 大写格式。

    Args:
        mac: 原始 MAC 地址字符串

    Returns:
        标准化后的 MAC 地址
    """
    return mac.replace("-", ":").upper()


# ------------------------------------------------------------------ #
#  字段校验
# ------------------------------------------------------------------ #

def validate_required_fields(data: dict, required: list[str]) -> tuple[bool, dict | None]:
    """校验请求体中是否包含所有必需字段。

    Args:
        data: 请求体 dict
        required: 必需字段名列表

    Returns:
        (是否通过, 错误信息 dict 或 None)
    """
    missing = [f for f in required if f not in data or data[f] is None]
    if not missing:
        return True, None

    return False, _validation_error(
        code=ErrorCode.VALIDATION_ERROR,
        field="body",
        message=f"缺少必需字段: {', '.join(missing)}",
    )


def validate_string_field(
    data: dict,
    field: str,
    min_length: int = 1,
    max_length: int = 255,
) -> tuple[bool, dict | None]:
    """校验字符串字段的长度限制。

    Args:
        data: 请求体 dict
        field: 字段名
        min_length: 最小长度 (包含)
        max_length: 最大长度 (包含)

    Returns:
        (是否通过, 错误信息 dict 或 None)
    """
    value = data.get(field)
    if value is None:
        return True, None  # 可选字段, 跳过

    if not isinstance(value, str):
        return False, _validation_error(
            code=ErrorCode.VALIDATION_ERROR,
            field=field,
            message=f"字段 '{field}' 必须是字符串",
        )

    if len(value) < min_length:
        return False, _validation_error(
            code=ErrorCode.VALIDATION_ERROR,
            field=field,
            message=f"字段 '{field}' 长度不能少于 {min_length} 字符",
        )

    if len(value) > max_length:
        return False, _validation_error(
            code=ErrorCode.VALIDATION_ERROR,
            field=field,
            message=f"字段 '{field}' 长度不能超过 {max_length} 字符",
        )

    return True, None


def validate_integer_field(
    data: dict,
    field: str,
    min_value: int | None = None,
    max_value: int | None = None,
) -> tuple[bool, dict | None]:
    """校验整数字段的范围限制。

    Args:
        data: 请求体 dict
        field: 字段名
        min_value: 最小值 (包含), None 表示不限制
        max_value: 最大值 (包含), None 表示不限制

    Returns:
        (是否通过, 错误信息 dict 或 None)
    """
    value = data.get(field)
    if value is None:
        return True, None

    if not isinstance(value, int) or isinstance(value, bool):
        return False, _validation_error(
            code=ErrorCode.VALIDATION_ERROR,
            field=field,
            message=f"字段 '{field}' 必须是整数",
        )

    if min_value is not None and value < min_value:
        return False, _validation_error(
            code=ErrorCode.VALIDATION_ERROR,
            field=field,
            message=f"字段 '{field}' 不能小于 {min_value}",
        )

    if max_value is not None and value > max_value:
        return False, _validation_error(
            code=ErrorCode.VALIDATION_ERROR,
            field=field,
            message=f"字段 '{field}' 不能大于 {max_value}",
        )

    return True, None


def validate_enum_field(
    data: dict,
    field: str,
    allowed_values: list[str],
) -> tuple[bool, dict | None]:
    """校验枚举字段的值是否在允许列表中。

    Args:
        data: 请求体 dict
        field: 字段名
        allowed_values: 允许的值的列表

    Returns:
        (是否通过, 错误信息 dict 或 None)
    """
    value = data.get(field)
    if value is None:
        return True, None

    if value not in allowed_values:
        return False, _validation_error(
            code=ErrorCode.VALIDATION_ERROR,
            field=field,
            message=f"字段 '{field}' 的值无效, 允许的值为: {', '.join(allowed_values)}",
        )

    return True, None


# ------------------------------------------------------------------ #
#  工具函数
# ------------------------------------------------------------------ #

def _validation_error(code: ErrorCode, field: str, message: str) -> dict:
    """构造参数校验错误的标准响应。"""
    return {
        "error": {
            "code": code.value,
            "message": ERROR_CODE_DESCRIPTION.get(code, "参数校验失败"),
            "details": {"field": field, "reason": message},
        }
    }
