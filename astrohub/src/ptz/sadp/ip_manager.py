"""
PTZ_ASTRO v1.1 - SADP IP 管理模块
IP 可达性检测（PING）、IP/网关修改（通过 SADP 协议），IP 冲突检测。

Author: 雅痞张@南方天文
"""

import platform
import socket
import struct
import subprocess
import time
import xml.etree.ElementTree as ET

from src.ptz.core.logger import LOG
from .discovery import SADPDevice, scan_for_devices, _build_probe_xml, _parse_sadp_response
from src.ptz.constants import SADP_MULTICAST_ADDR, SADP_PORT, SADP_TIMEOUT_MS


def check_reachable(ip: str, timeout: int = 3) -> bool:
    """通过 PING 检测 IP 可达性。
    
    返回:
        True = 可达，False = 不可达
    """
    LOG.log("info", f"检测 IP 可达性: {ip}")
    
    system = platform.system()
    if system == "Windows":
        cmd = f"ping -n 1 -w {timeout * 1000} {ip}"
    else:
        cmd = f"ping -c 1 -W {timeout} {ip}"
    
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout + 5)
        reachable = result.returncode == 0
        if reachable:
            LOG.log("done", f"IP {ip} 可达")
        else:
            LOG.log("warning", f"IP {ip} 不可达")
        return reachable
    except Exception as e:
        LOG.log("error", f"PING 检测异常: {e}")
        return False


def check_ip_conflict(ip: str, timeout: int = 2) -> bool:
    """检测 IP 是否已被占用。
    
    方法: 尝试 ARP 解析 + 短 ping
    返回:
        True = IP 冲突（已被占用），False = IP 可用
    """
    LOG.log("info", f"检测 IP 冲突: {ip}")
    
    # 使用 PING 检测
    if check_reachable(ip, timeout):
        LOG.log("warning", f"IP {ip} 已被占用")
        return True
    
    LOG.log("done", f"IP {ip} 可用")
    return False


def _build_modify_ip_xml(device_uuid: str, ip: str, subnet_mask: str, gateway: str, mac: str) -> bytes:
    """构建 SADP 修改 IP 的 XML 报文。

    SADP 修改 IP 需要发送带有设备 MAC 和新网络配置的 XML。
    """
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Probe>
  <Uuid>{device_uuid}</Uuid>
  <Types>ModifyIP</Types>
  <IPv4Address>{ip}</IPv4Address>
  <IPv4SubnetMask>{subnet_mask}</IPv4SubnetMask>
  <IPv4Gateway>{gateway}</IPv4Gateway>
  <MACAddress>{mac}</MACAddress>
</Probe>"""
    return xml.encode("utf-8")


def modify_device_ip(
    device: SADPDevice,
    new_ip: str,
    new_gateway: str,
    subnet_mask: str = "255.255.255.0",
) -> bool:
    """通过 SADP 修改设备 IP。

    参数:
        device: 目标设备
        new_ip: 新 IP 地址
        new_gateway: 新网关
        subnet_mask: 子网掩码

    返回:
        True = 修改成功，False = 失败
    """
    LOG.log("info", f"修改设备 IP: {device.ip} -> {new_ip}, 网关 -> {new_gateway}")

    # 先检测 IP 冲突
    if check_ip_conflict(new_ip):
        LOG.log("failed", f"IP {new_ip} 已被占用，请更换")
        return False

    # 发送 SADP 修改报文
    import uuid
    uuid_str = uuid.uuid4().hex
    modify_xml = _build_modify_ip_xml(uuid_str, new_ip, subnet_mask, new_gateway, device.mac)

    try:
        send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        send_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        send_sock.settimeout(5)

        # 发送到多播地址
        send_sock.sendto(modify_xml, (SADP_MULTICAST_ADDR, SADP_PORT))
        LOG.log("info", f"SADP IP 修改报文已发送")

        # 等待响应
        recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            recv_sock.bind(("", SADP_PORT))
            recv_sock.setsockopt(
                socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                struct.inet_aton(SADP_MULTICAST_ADDR) + struct.inet_aton(socket.gethostbyname(socket.gethostname()))
            )
            recv_sock.settimeout(10)

            timeout_at = time.time() + 10
            while time.time() < timeout_at:
                try:
                    data, addr = recv_sock.recvfrom(65535)
                    response = _parse_sadp_response(data)
                    if response and response.mac == device.mac:
                        # 检查响应中的 IP 是否已更新
                        if response.ip == new_ip:
                            LOG.log("done", f"IP 修改成功: {new_ip}")
                            device.ip = new_ip
                            device.gateway = new_gateway
                            recv_sock.close()
                            send_sock.close()
                            return True
                except socket.timeout:
                    continue
        finally:
            try:
                recv_sock.close()
            except Exception:
                pass
        send_sock.close()

        # 即使没有收到明确响应，也尝试验证新 IP 是否可达
        time.sleep(5)  # 等待设备应用新 IP
        if check_reachable(new_ip, timeout=3):
            LOG.log("done", f"新 IP {new_ip} 可达，修改成功")
            device.ip = new_ip
            device.gateway = new_gateway
            return True

        LOG.log("failed", f"IP 修改后 {new_ip} 不可达")
        return False

    except Exception as e:
        LOG.log("error", f"IP 修改异常: {e}")
        return False


def ip_modify_loop(
    device: SADPDevice,
    local_gateway: str,
    local_ip: str,
    config_manager=None,
) -> SADPDevice | None:
    """IP 修改交互循环。

    当设备 IP 不可达时，引导用户输入新的 IP/网关。
    修改后等待 10 秒，返回新的设备对象。

    返回:
        修改后的设备对象，或 None（用户取消）
    """
    from ptz.core.ui import input_number, confirm

    # 计算同网段默认 IP
    network_parts = local_ip.split(".")[:3]  # e.g. ["192", "168", "1"]
    default_ip = f"{'.'.join(network_parts)}.64"

    print(f"\n  设备当前 IP: {device.ip} 不可达")
    print(f"  建议 IP: {default_ip}（同网段 .64）")
    print(f"  网关: {local_gateway}")
    print()

    while True:
        # 输入 IP
        new_ip = input(f"  请输入新 IP 地址 [{default_ip}]: ").strip()
        if not new_ip:
            new_ip = default_ip

        if new_ip.upper() == "Q":
            LOG.log("info", "用户取消 IP 修改")
            return None

        if new_ip.upper() == "ESC":
            print("  已清空，请重新输入")
            continue

        # 输入网关
        new_gateway = input(f"  请输入网关 [{local_gateway}]: ").strip()
        if not new_gateway:
            new_gateway = local_gateway

        if new_gateway.upper() == "Q":
            return None

        # 确认
        if confirm(f"  确认修改 IP={new_ip}, 网关={new_gateway}？(Enter=确认, Q=重新输入)"):
            break

    # 执行修改
    if modify_device_ip(device, new_ip, new_gateway):
        LOG.log("info", "IP 修改成功，等待 10 秒后重新扫描...")
        time.sleep(10)
        return device
    else:
        LOG.log("failed", "IP 修改失败")
        # 允许重试
        return ip_modify_loop(device, local_gateway, local_ip, config_manager)
