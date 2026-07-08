"""
src/advanced/startup.py - 本机信息收集脚本

首次运行时收集本机硬件和网络信息，保存到 data/reports/localhost.json

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from datetime import datetime

from src.config_paths import DATA_DIR, REPORT_DIR
from src.ptz.core.system_info import collect_system_info
from src.logger import get_logger

logger = get_logger("startup")


def get_default_gateway() -> str:
    """获取默认网关"""
    try:
        # PowerShell 获取默认路由
        result = subprocess.run(
            ['powershell', '-NoProfile', '-Command', 
             'Get-NetRoute -DestinationPrefix 0.0.0.0/0 | Select-Object -ExpandProperty NextHop -First 1'],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        gateway = result.stdout.strip()
        if gateway and gateway != "":
            return gateway
    except Exception as e:
        logger.warning(f"获取网关失败: {e}")
    
    # Fallback: ipconfig
    try:
        result = subprocess.run(
            'ipconfig', capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        for line in result.stdout.split('\n'):
            if '默认网关' in line or 'Default Gateway' in line:
                parts = line.split(':')
                if len(parts) > 1:
                    gw = parts[-1].strip()
                    if gw and gw != "":
                        return gw
    except Exception as e:
        logger.warning(f"ipconfig 获取网关失败: {e}")
    
    return ""


def get_local_ip() -> str:
    """获取本机主要 IP 地址"""
    try:
        from src.core.net_detector import get_all_nics
        nics = get_all_nics()
        # 优先选择物理网卡（非虚拟、非回环）
        for nic in nics:
            if not nic.get('is_loopback') and nic.get('is_up'):
                name = nic.get('name', '')
                # 排除虚拟网卡
                if 'vEthernet' not in name and 'Loopback' not in name and 'Virtual' not in name:
                    ips = nic.get('ips', [])
                    if ips:
                        return ips[0]
        # 没找到就用第一个非回环的
        for nic in nics:
            if not nic.get('is_loopback') and nic.get('ips'):
                return nic['ips'][0]
    except Exception as e:
        logger.warning(f"获取本机 IP 失败: {e}")
    
    return ""


def collect_localhost_info() -> dict:
    """收集本机完整信息"""
    logger.info("=== 开始收集本机信息 ===")
    
    # 获取系统硬件信息
    system_info = collect_system_info()
    
    # 获取网络信息
    gateway = get_default_gateway()
    local_ip = get_local_ip()
    
    # 合并信息
    localhost_info = {
        "hostname": system_info.get("hostname", ""),
        "cpu_model": system_info.get("cpu_model", ""),
        "ram_gb": system_info.get("ram_gb", 0),
        "gpu_count": system_info.get("gpu_count", 0),
        "vram_gb": system_info.get("vram_gb", 0),
        "gpu_names": system_info.get("gpu_names", []),
        "gateway": gateway,
        "local_ip": local_ip,
        "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "version": "v7.15"
    }
    
    logger.info(f"本机信息: {localhost_info['hostname']} / {localhost_info['cpu_model']} / {localhost_info['ram_gb']}GB / {localhost_info['gateway']} / {localhost_info['local_ip']}")
    
    return localhost_info


def save_localhost_json(info: dict) -> Path:
    """保存本机信息到 JSON 文件"""
    # 确保目录存在
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    
    # 文件路径
    json_path = REPORT_DIR / "localhost.json"
    
    # 保存
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(info, f, indent=2, ensure_ascii=False)
    
    logger.info(f"本机信息已保存: {json_path}")
    return json_path


def run_startup() -> dict:
    """执行 startup 流程，返回本机信息"""
    info = collect_localhost_info()
    save_localhost_json(info)
    return info


def check_localhost_exists() -> bool:
    """检查 localhost.json 是否存在"""
    json_path = REPORT_DIR / "localhost.json"
    return json_path.exists()


def get_localhost_info() -> dict | None:
    """读取已保存的本机信息"""
    json_path = REPORT_DIR / "localhost.json"
    if not json_path.exists():
        return None
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"读取 localhost.json 失败: {e}")
        return None


if __name__ == "__main__":
    run_startup()