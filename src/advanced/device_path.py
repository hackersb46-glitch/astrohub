"""
AstroHub v2.0 - 设备数据路径管理

v6.19 更新:
- 删除 config_paths 依赖，统一路径定义
- 统一路径：data/devices/{mac}/
- 带时间戳文件：data/devices/{mac}/{test_type}_{timestamp}.json
- 读取规则：永远读最新记录

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ================================================================ #
#  统一路径定义 (v6.19)
# ================================================================ #

def _get_app_dir() -> Path:
    """获取应用程序根目录。"""
    import sys
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent.parent

APP_DIR = _get_app_dir()
DATA_DIR = APP_DIR / 'data'
DEVICES_DIR = DATA_DIR / 'devices'


def get_devices_dir() -> Path:
    """v6.19: 获取设备数据根目录。"""
    return DEVICES_DIR


def get_device_info(ptz: Any) -> dict[str, str]:
    """从设备获取唯一标识信息。

    Args:
        ptz: PTZController实例

    Returns:
        dict: {mac, model, model_short, serial}
    """
    # 从PTZController获取ISAPIClient
    client = ptz.client if hasattr(ptz, 'client') else ptz

    # 获取设备信息
    resp = client.get('/System/deviceInfo')
    xml = resp.xml

    # 解析XML
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml)

    # 提取字段
    mac = ""
    model = ""
    serial = ""

    for child in root:
        tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        if tag == 'macAddress':
            mac = child.text or ""
        elif tag == 'model':
            model = child.text or ""
        elif tag == 'serialNumber':
            serial = child.text or ""

    # MAC地址去除冒号，转小写
    mac_clean = mac.replace(':', '').lower()

    # 短型号：取前缀（去掉后缀数字和字母）
    # iDS-2DF8C832IXS-A -> iDS-2DF8C
    model_short = model
    if len(model) > 8:
        model_short = model[:8]
        while model_short and model_short[-1].isdigit():
            model_short = model_short[:-1]

    return {
        'mac': mac,
        'mac_clean': mac_clean,
        'model': model,
        'model_short': model_short,
        'serial': serial
    }


def get_device_dir(mac_clean: str) -> Path:
    """v6.03: 获取设备数据目录路径。

    Args:
        mac_clean: MAC地址（无冒号，小写）

    Returns:
        Path: data/devices/{mac_clean}/
    """
    return DEVICES_DIR / mac_clean


def get_data_path_read(model_short: str | None, mac_clean: str, test_type: str) -> Path | None:
    """v6.33: 获取读取路径（优先最新时间戳文件，其次固定名称文件）。

    Args:
        model_short: 短型号（可选，v6.33 不再使用）
        mac_clean: MAC地址（无分隔符，小写）- 必须匹配设备
        test_type: 测试类型 (function/limit/speed)

    Returns:
        Path: 文件路径，如不存在返回None
    """
    device_dir = get_device_dir(mac_clean)
    if not device_dir.exists():
        return None

    # v6.33: 优先查找最新的 {test_type}_*.json 时间戳文件
    pattern = re.compile(rf'^{test_type}_(\d{{8}}_\d{{6}})\.json$')
    latest_file = None
    latest_time = None

    for f in device_dir.iterdir():
        if f.is_file():
            match = pattern.match(f.name)
            if match:
                file_time = f.stat().st_mtime
                if latest_time is None or file_time > latest_time:
                    latest_time = file_time
                    latest_file = f

    # 有时间戳文件则返回最新的
    if latest_file:
        return latest_file

    # 其次查找固定名称文件
    fixed_path = device_dir / f'{test_type}.json'
    if fixed_path.exists():
        return fixed_path

    return None


def get_data_path_write(model_short: str | None, mac_clean: str, test_type: str) -> Path:
    """v6.19: 获取写入路径（固定名称文件）。

    Args:
        model_short: 短型号（可选，v6.19 不再使用）
        mac_clean: MAC地址（无分隔符，小写）
        test_type: 测试类型 (function/limit/speed)

    Returns:
        Path: 文件路径 data/devices/{mac_clean}/{test_type}.json
    """
    device_dir = get_device_dir(mac_clean)
    device_dir.mkdir(parents=True, exist_ok=True)

    return device_dir / f'{test_type}.json'
