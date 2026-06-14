"""网络检测模块 - 网卡识别、子网获取、IP 发现"""

import ipaddress
import platform
import socket
import struct
import subprocess
from typing import Optional

import psutil


def get_all_nics() -> list[dict]:
    """返回所有网卡列表，包含名称、地址、状态信息。

    Returns:
        每个元素为 dict:
            - name: 网卡名称
            - ips: IPv4 地址列表
            - is_up: 是否启用
            - is_loopback: 是否回环
    """
    addresses = psutil.net_if_addrs()
    stats = psutil.net_if_stats()

    result = []
    for name, addrs in addresses.items():
        ipv4_list = [
            addr.address
            for addr in addrs
            if addr.family == socket.AF_INET
        ]
        nic_stat = stats.get(name)
        result.append({
            "name": name,
            "ips": ipv4_list,
            "is_up": nic_stat.isup if nic_stat else False,
            # psutil compatibility: isloopback removed in newer versions
            "is_loopback": getattr(nic_stat, 'isloopback', False) if nic_stat else False,
        })
    return result


def get_default_nic() -> Optional[str]:
    """过滤虚拟网卡，返回默认物理网卡。

    优先级: 有线 > 无线 > 其他

    Returns:
        网卡名称，无可用网卡时返回 None
    """
    addresses = psutil.net_if_addrs()
    stats = psutil.net_if_stats()

    wired = []
    wireless = []
    others = []

    for name, addrs in addresses.items():
        nic_stat = stats.get(name)
        if nic_stat is None:
            continue
        # 跳过回环、未启用、虚拟网卡
        # 注意: snicstats 没有 isloopback 属性，通过名称判断
        is_loopback = 'loopback' in name.lower()
        if is_loopback or not nic_stat.isup:
            continue
        # 过滤常见虚拟网卡关键词
        lower_name = name.lower()
        virtual_keywords = [
            "veth", "docker", "br-", "virbr", "vmnet",
            "virtualbox", "wsl", "hyper-v", "loopback",
        ]
        if any(kw in lower_name for kw in virtual_keywords):
            continue
        # 必须有 IPv4 地址
        has_ipv4 = any(
            addr.family == socket.AF_INET for addr in addrs
        )
        if not has_ipv4:
            continue

        # 分类: 有线 / 无线 / 其他
        # Windows: Ethernet/有线 vs Wi-Fi/无线
        # Linux: eth/enp 为有线, wlp/wlan 为无线
        wired_keywords = ["ethernet", "eth", "enp", "ens", "enx", "local area"]
        wireless_keywords = ["wi-fi", "wifi", "wlan", "wlp", "wireless", "airport"]

        if any(kw in lower_name for kw in wireless_keywords):
            wireless.append(name)
        elif any(kw in lower_name for kw in wired_keywords):
            wired.append(name)
        else:
            others.append(name)

    # 优先级: 有线 > 无线 > 其他
    for candidates in [wired, wireless, others]:
        if candidates:
            return candidates[0]

    return None


def get_local_subnet(
    nic_name: Optional[str] = None,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """返回本地子网信息。

    Args:
        nic_name: 网卡名称，None 时自动选择默认网卡

    Returns:
        (ip, mask, gateway) 三元组，任一不可用时为 None
    """
    if nic_name is None:
        nic_name = get_default_nic()
    if nic_name is None:
        return (None, None, None)

    addresses = psutil.net_if_addrs()
    nic_addrs = addresses.get(nic_name, [])

    ip_addr = None
    mask = None
    for addr in nic_addrs:
        if addr.family == socket.AF_INET:
            ip_addr = addr.address
            mask = addr.netmask
            break

    if ip_addr is None:
        return (ip_addr, mask, None)

    # 获取网关 - Windows 用 route print, Linux 用 ip route
    gateway = _get_default_gateway()
    return (ip_addr, mask, gateway)


def _get_default_gateway() -> Optional[str]:
    """获取默认网关地址。"""
    system = platform.system()

    if system == "Windows":
        return _get_gateway_windows()
    else:
        return _get_gateway_linux()


def _get_gateway_windows() -> Optional[str]:
    """Windows 下通过 route print 获取默认网关。"""
    try:
        result = subprocess.run(
            ["route", "print", "0.0.0.0"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            # 默认路由行以 0.0.0.0 开头
            if line.startswith("0.0.0.0") and "0.0.0.0" in line:
                parts = line.split()
                # route print 格式: 0.0.0.0  0.0.0.0  <gateway>  <iface>  <metric>
                if len(parts) >= 3:
                    gw = parts[2]
                    # 验证是合法 IP
                    try:
                        ipaddress.ip_address(gw)
                        return gw
                    except ValueError:
                        pass
    except Exception:
        pass
    return None


def _get_gateway_linux() -> Optional[str]:
    """Linux 下通过 ip route 获取默认网关。"""
    try:
        result = subprocess.run(
            ["ip", "route"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in result.stdout.splitlines():
            if line.startswith("default"):
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == "via" and i + 1 < len(parts):
                        return parts[i + 1]
    except Exception:
        pass
    return None


def suggest_target_ip(
    nic_name: Optional[str] = None,
    host_num: int = 64,
) -> Optional[str]:
    """基于本地子网，建议目标 IP。

    Args:
        nic_name: 网卡名称，None 时自动选择
        host_num: 目标主机号，默认 64

    Returns:
        建议的 IP 地址字符串，不可用时返回 None
    """
    ip_addr, mask, _ = get_local_subnet(nic_name)
    if ip_addr is None or mask is None:
        return None

    try:
        network = ipaddress.IPv4Network(
            f"{ip_addr}/{mask}", strict=False
        )
        # 网络地址 + host_num
        base = int(network.network_address)
        host_offset = host_num
        target_int = base + host_offset

        # 确保在子网范围内，且不是网络地址或广播地址
        if target_int <= int(network.network_address):
            target_int = int(network.network_address) + host_offset
        if target_int >= int(network.broadcast_address):
            return None

        return str(ipaddress.IPv4Address(target_int))
    except (ValueError, TypeError):
        return None


def find_available_ip(
    nic_name: Optional[str] = None,
    start: int = 64,
    max_try: int = 20,
    timeout: float = 0.5,
) -> Optional[str]:
    """从指定起始主机号开始，通过 PING 寻找可用（无响应）的 IP。

    Args:
        nic_name: 网卡名称，None 时自动选择
        start: 起始主机号，默认 64
        max_try: 最大尝试次数，默认 20
        timeout: PING 超时秒数，默认 0.5

    Returns:
        第一个无响应的 IP（可用），全部被占用时返回 None
    """
    ip_addr, mask, _ = get_local_subnet(nic_name)
    if ip_addr is None or mask is None:
        return None

    try:
        network = ipaddress.IPv4Network(
            f"{ip_addr}/{mask}", strict=False
        )
        base = int(network.network_address)
        broadcast = int(network.broadcast_address)
    except (ValueError, TypeError):
        return None

    system = platform.system()
    ping_cmd = _build_ping_command(system, timeout)

    for offset in range(start, start + max_try):
        target_int = base + offset
        if target_int >= broadcast:
            break

        target_ip = str(ipaddress.IPv4Address(target_int))

        # PING: 无响应 = IP 可用
        if not _ping_host(target_ip, ping_cmd, system):
            return target_ip

    return None


def _build_ping_command(system: str, timeout: float) -> list[str]:
    """构建 PING 命令。"""
    if system == "Windows":
        # -n 1: 只发1个包, -w: 超时毫秒
        wait_ms = int(timeout * 1000)
        return ["ping", "-n", "1", "-w", str(wait_ms)]
    else:
        # -c 1: 只发1个包, -W: 超时秒(整数, 至少1)
        wait_sec = max(1, int(timeout))
        return ["ping", "-c", "1", "-W", str(wait_sec)]


def _ping_host(ip: str, cmd: list[str], system: str) -> bool:
    """PING 目标 IP，返回 True 表示主机在线（IP 被占用）。"""
    try:
        result = subprocess.run(
            cmd + [ip],
            capture_output=True,
            text=True,
            timeout=3,
            creationflags=subprocess.CREATE_NO_WINDOW if system == "Windows" else 0,
        )
        return result.returncode == 0
    except Exception:
        # 超时或异常 = 主机无响应 = 可用
        return False
