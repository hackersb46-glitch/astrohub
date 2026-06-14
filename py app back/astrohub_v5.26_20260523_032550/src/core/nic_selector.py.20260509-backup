"""
src/core/nic_selector.py - P1 物理网卡检测与选择模块

功能:
  - 列出所有物理网卡 (排除虚拟/隧道/回环)
  - 显示网卡 IP、子网、网关、类型、速度、连接状态
  - 唯一物理有线网卡自动选择
  - 多个物理网卡时提供选择接口
  - 禁止禁用/启用网卡、禁止修改网卡 IP/网关

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import platform
import socket
import subprocess
from dataclasses import dataclass, field
from typing import Optional

import psutil

# ============================================================
# 虚拟网卡过滤关键词
# ============================================================

VIRTUAL_KEYWORDS = [
    "veth", "docker", "br-", "virbr", "vmnet", "virtualbox",
    "wsl", "hyper-v", "loopback", "tun", "tap", "wg",
    "openvpn", "wireguard", "bluetooth", "pan",
]

# ============================================================
# 网卡类型关键词
# ============================================================

WIRED_KEYWORDS = [
    "ethernet", "eth", "enp", "ens", "enx", "local area",
    "realtek", "intel(r) ethernet", "broadcom",
]

WIRELESS_KEYWORDS = [
    "wi-fi", "wifi", "wlan", "wlp", "wireless", "airport",
    "intel(r) wi-fi", "realtek wireless",
]


@dataclass
class NICInfo:
    """单块网卡信息."""
    name: str = ""
    index: int = 0
    ips: list[str] = field(default_factory=list)
    netmask: str = ""
    gateway: str = ""
    is_up: bool = False
    is_loopback: bool = False
    is_virtual: bool = False
    nic_type: str = "unknown"  # "wired", "wireless", "virtual", "unknown"
    speed: str = "N/A"
    mac_address: str = ""

    def is_physical_connected(self) -> bool:
        """物理网卡且已连接 (UP 且非回环)."""
        return self.is_up and not self.is_loopback and not self.is_virtual

    def display_name(self) -> str:
        ip_str = ", ".join(self.ips) if self.ips else "无 IP"
        return f"{self.name} | {ip_str} | {self.gateway or '无网关'} | {self.nic_type}"


def _is_virtual_nic(name: str) -> bool:
    """判断是否为虚拟网卡."""
    lower = name.lower()
    return any(kw in lower for kw in VIRTUAL_KEYWORDS)


def _detect_nic_type(name: str) -> str:
    """检测网卡类型."""
    lower = name.lower()
    if any(kw in lower for kw in WIRED_KEYWORDS):
        return "wired"
    if any(kw in lower for kw in WIRELESS_KEYWORDS):
        return "wireless"
    return "unknown"


def _get_gateway_windows() -> Optional[str]:
    """Windows 下获取默认网关."""
    try:
        result = subprocess.run(
            ["route", "print", "0.0.0.0"],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("0.0.0.0") and "0.0.0.0" in line:
                parts = line.split()
                if len(parts) >= 3:
                    gw = parts[2]
                    try:
                        import ipaddress
                        ipaddress.ip_address(gw)
                        return gw
                    except ValueError:
                        pass
    except Exception:
        pass
    return None


def _get_gateways_by_interface() -> dict[int, str]:
    """获取每个接口索引对应的网关 (Windows)."""
    gateways: dict[int, str] = {}
    try:
        result = subprocess.run(
            ["route", "print"],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        in_ipv4_routes = False
        default_routes: list[tuple[int, str, int]] = []  # (iface, gateway, metric)
        for line in result.stdout.splitlines():
            line = line.strip()
            # 检测 IPv4 路由表开始
            if "IPv4 Route Table" in line:
                in_ipv4_routes = True
                continue
            if in_ipv4_routes:
                # 检测路由表结束 (空行或新标题行)
                if line.startswith("=") or (line == "" and default_routes):
                    break
                if line.startswith("0.0.0.0"):
                    parts = line.split()
                    if len(parts) >= 5:
                        try:
                            metric = int(parts[4])
                            gw = parts[2]
                            iface = parts[3]
                            default_routes.append((int(iface), gw, metric))
                        except (ValueError, IndexError):
                            pass
        # 取最低 metric 的路由
        if default_routes:
            default_routes.sort(key=lambda x: x[2])
            for iface_idx, gw, _ in default_routes:
                if iface_idx not in gateways:
                    gateways[iface_idx] = gw
    except Exception:
        pass
    return gateways


def _get_link_speed_windows(if_index: int) -> str:
    """获取网卡连接速度 (Windows, PowerShell)."""
    try:
        ps_cmd = (
            f"(Get-NetAdapter -InterfaceIndex {if_index} -ErrorAction SilentlyContinue)"
            f" | Select-Object -ExpandProperty LinkSpeed"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return "N/A"


def _get_mac_address_windows(if_index: int) -> str:
    """获取网卡 MAC 地址 (Windows)."""
    try:
        ps_cmd = (
            f"(Get-NetAdapter -InterfaceIndex {if_index} -ErrorAction SilentlyContinue)"
            f" | Select-Object -ExpandProperty MacAddress"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().replace("-", ":")
    except Exception:
        pass
    return ""


def list_all_nics() -> list[NICInfo]:
    """列出系统所有网卡 (含虚拟/回环), 返回 NICInfo 列表."""
    addresses = psutil.net_if_addrs()
    stats = psutil.net_if_stats()

    # 构建 if_index 到名称的映射
    name_to_index: dict[str, int] = {}
    try:
        ps_cmd = (
            "Get-NetAdapter | Select-Object Name, ifIndex | "
            "ConvertTo-Json"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            import json
            data = json.loads(result.stdout.strip())
            if isinstance(data, list):
                for item in data:
                    name_to_index[item.get("Name", "")] = item.get("ifIndex", 0)
            elif isinstance(data, dict):
                name_to_index[data.get("Name", "")] = data.get("ifIndex", 0)
    except Exception:
        pass

    # 网关映射
    gateways = _get_gateways_by_interface() if platform.system() == "Windows" else {}

    result = []
    for name, addrs in addresses.items():
        ipv4_list = []
        netmask = ""
        for addr in addrs:
            if addr.family == socket.AF_INET:
                ipv4_list.append(addr.address)
                netmask = addr.netmask or ""

        nic_stat = stats.get(name)
        is_loopback = "loopback" in name.lower() if not nic_stat else nic_stat.isloopback if hasattr(nic_stat, 'isloopback') else False
        is_virtual = _is_virtual_nic(name)
        nic_type = "virtual" if is_virtual else _detect_nic_type(name)

        if_index = name_to_index.get(name, 0)
        gateway = gateways.get(if_index, "") if if_index else ""

        info = NICInfo(
            name=name,
            index=if_index,
            ips=ipv4_list,
            netmask=netmask,
            gateway=gateway,
            is_up=nic_stat.isup if nic_stat else False,
            is_loopback=is_loopback,
            is_virtual=is_virtual,
            nic_type=nic_type,
        )

        # 补充 Windows 特化信息
        if if_index:
            info.speed = _get_link_speed_windows(if_index)
            info.mac_address = _get_mac_address_windows(if_index)

        result.append(info)

    return result


def list_physical_nics() -> list[NICInfo]:
    """列出所有物理网卡 (UP 状态, 排除虚拟/回环), 按优先级排序.
    
    排序规则: 有线 > 无线, 有默认网关优先.
    """
    all_nics = list_all_nics()
    physical = [nic for nic in all_nics if nic.is_physical_connected()]

    # 优先级排序: 有线 > 无线
    def nic_priority(nic: NICInfo) -> int:
        if nic.nic_type == "wired":
            return 0
        elif nic.nic_type == "wireless":
            return 1
        return 2

    # 有网关的优先 (同类型内)
    physical.sort(key=lambda n: (nic_priority(n), 0 if n.gateway else 1))

    return physical


def get_physical_nic_display(nic: NICInfo) -> str:
    """格式化网卡信息以供显示."""
    ip_str = ", ".join(nic.ips) if nic.ips else "无 IP"
    type_cn = {"wired": "有线", "wireless": "无线", "unknown": "未知"}.get(nic.nic_type, nic.nic_type)
    speed_str = f" | {nic.speed}" if nic.speed != "N/A" else ""
    mac_str = f" | MAC={nic.mac_address}" if nic.mac_address else ""
    gw_str = f" | 网关={nic.gateway}" if nic.gateway else " | 无网关"
    return f"IP: {ip_str} | 类型: {type_cn}{gw_str}{speed_str}{mac_str}"


def select_nic(interactive: bool = True, selected_index: int | None = None) -> Optional[NICInfo]:
    """选择物理网卡.
    
    Args:
        interactive: 是否使用交互模式 (多网卡时需要)
        selected_index: 预选择索引 (跳过交互)
    
    Returns:
        选中的 NICInfo, 无可用网卡返回 None.
    """
    physical = list_physical_nics()

    if not physical:
        return None

    # 只有一个物理网卡 -> 自动选择
    if len(physical) == 1:
        return physical[0]

    # 预选择了索引
    if selected_index is not None and 0 <= selected_index < len(physical):
        return physical[selected_index]

    # 多网卡, 非交互模式 -> 返回第一个
    if not interactive:
        return physical[0]

    # 交互模式: 让用户选择
    print("\n" + "=" * 60)
    print("检测到多个物理网卡，请选择使用的网卡:")
    print("=" * 60)
    for i, nic in enumerate(physical):
        print(f"  [{i+1}] {nic.name}")
        print(f"      {get_physical_nic_display(nic)}")
        print()

    print("[Q] 退出程序")
    print("默认选择 [1] (按 Enter 确认)")

    while True:
        choice = input("\n请选择网卡序号 [1]: ").strip()
        if choice.upper() == 'Q':
            return None
        if choice == "":
            choice = "1"
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(physical):
                return physical[idx]
            print(f"无效序号，请输入 1-{len(physical)}")
        except ValueError:
            print("无效输入，请输入数字或 Q 退出")


def get_selected_nic_info(selected_nic: NICInfo) -> dict:
    """获取选中网卡的完整信息字典 (供 P2/P3 流程使用).
    
    Returns:
        {
            "nic_name": 网卡名称,
            "local_ip": 本机 IP,
            "subnet_mask": 子网掩码,
            "gateway": 网关,
            "nic_type": "wired"/"wireless",
        }
    """
    return {
        "nic_name": selected_nic.name,
        "local_ip": selected_nic.ips[0] if selected_nic.ips else "0.0.0.0",
        "subnet_mask": selected_nic.netmask,
        "gateway": selected_nic.gateway,
        "nic_type": selected_nic.nic_type,
        "index": selected_nic.index,
        "speed": selected_nic.speed,
        "mac_address": selected_nic.mac_address,
    }
