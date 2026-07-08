"""
PTZ_ASTRO v1.1 - SADP 设备发现模块
通过 SADP 多播广播发现 Hikvision 设备，10 秒超时，返回 MAC/IP/型号/SN/激活状态。

SADP 协议：
- 目标地址: 239.255.255.250:37020
- 发送 XML 探测报文（Probe）
- 设备返回 XML 响应包含设备信息

Author: 雅痞张@南方天文
"""

import os
import platform
import shutil
import socket
import struct
import subprocess
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from src.ptz.core.logger import LOG
from src.ptz.constants import (
    SADP_MULTICAST_ADDR,
    SADP_PORT,
    SADP_TIMEOUT_MS,
    HIKVISION_MAC_OUI,
)


@dataclass
class SADPDevice:
    """SADP 发现的设备信息。"""
    mac: str = ""
    ip: str = ""
    subnet_mask: str = ""
    gateway: str = ""
    model: str = ""
    serial_number: str = ""
    device_name: str = ""
    firmware_version: str = ""
    activated: bool = False
    is_hikvision: bool = False

    def display_name(self) -> str:
        return f"{self.model} ({self.mac}) - {'已激活' if self.activated else '未激活'}"


def _generate_uuid() -> str:
    """生成 UUID 用于 SADP 探测报文。"""
    return uuid.uuid4().hex


def _build_probe_xml(uuid_str: str) -> bytes:
    """构建 SADP Probe XML 报文。"""
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Probe>
  <Uuid>{uuid_str}</Uuid>
  <Types>inquiry</Types>
</Probe>"""
    return xml.encode("utf-8")


def _is_hikvision_mac(mac: str) -> bool:
    """检查 MAC 地址是否为 Hikvision OUI。"""
    normalized = mac.replace("-", ":").upper()
    prefix = normalized[:8]  # "AA:BB:CC"
    return prefix in HIKVISION_MAC_OUI


# ============================================================
# DLL Alias Resolution for Sadp.dll (Error 2045 Fix)
# ============================================================

def _ensure_ssl_dll_aliases(dll_dir: str) -> None:
    """自动创建 OpenSSL DLL 别名 (解决 Sadp.dll 内部 LoadLibrary 查找).

    根因: Sadp.dll 内部通过 LoadLibrary 加载 libcrypto-1_1.dll 和 libssl-1_1.dll
    (不带 -x64 后缀), 同时 fallback 到 libeay32.dll/ssleay32.dll.
    我们只提供带 -x64 后缀的版本, 导致 AES 加密失败 (错误 2045).

    方案: 在加载 Sadp.dll 前, 自动复制 -x64 版本到无后缀别名.
    """
    aliases = [
        ("libcrypto-1_1-x64.dll", "libcrypto-1_1.dll"),
        ("libssl-1_1-x64.dll",     "libssl-1_1.dll"),
    ]

    for src_name, dst_name in aliases:
        src_path = os.path.join(dll_dir, src_name)
        dst_path = os.path.join(dll_dir, dst_name)

        if not os.path.exists(src_path):
            print(f"[SADP] [DLL Alias] 跳过 {src_name}: 源文件不存在")
            continue

        if os.path.exists(dst_path):
            src_size = os.path.getsize(src_path)
            dst_size = os.path.getsize(dst_path)
            if src_size == dst_size:
                print(f"[SADP] [DLL Alias] {dst_name} 已存在且大小一致 ({dst_size} bytes)")
                continue
            # 大小不同, 覆盖
            print(f"[SADP] [DLL Alias] {dst_name} 大小不同 ({dst_size} vs {src_size}), 覆盖中...")

        try:
            shutil.copy2(src_path, dst_path)
            print(f"[SADP] [DLL Alias] {src_name} → {dst_name} ({os.path.getsize(dst_path)} bytes)")
        except Exception as e:
            print(f"[SADP] [DLL Alias] 复制 {src_name} → {dst_name} 失败: {e}")


def _ensure_libeay32_dll(dll_dir: str) -> bool:
    """检查/获取 libeay32.dll (OpenSSL 0.9.x fallback).

    Sadp.dll 会 fallback 到 libeay32.dll / ssleay32.dll.
    优先路径: 本地已有 > C:\\Program Files\\astap\\ > 跳过.

    Returns:
        True 如果 libeay32.dll 可用 (已有或复制成功).
    """
    dst_path = os.path.join(dll_dir, "libeay32.dll")

    # 已有: 跳过
    if os.path.exists(dst_path):
        size = os.path.getsize(dst_path)
        print(f"[SADP] [DLL Alias] libeay32.dll 已存在 ({size} bytes)")
        return True

    # 尝试从 astap 复制
    fallback_sources = [
        r"C:\Program Files\astap\libeay32.dll",
        r"C:\Program Files (x86)\astap\libeay32.dll",
    ]

    for src in fallback_sources:
        if os.path.exists(src):
            try:
                shutil.copy2(src, dst_path)
                size = os.path.getsize(dst_path)
                print(f"[SADP] [DLL Alias] libeay32.dll 已从 {src} 复制 ({size} bytes)")
                return True
            except Exception as e:
                print(f"[SADP] [DLL Alias] 复制 libeay32.dll 失败: {e}")

    print(f"[SADP] [DLL Alias] libeay32.dll 不可用, 跳过")
    return False


def _report_openssl_dlls(dll_dir: str) -> None:
    """诊断日志: 报告当前目录下的 OpenSSL DLL 状态."""
    ssl_dlls = [
        "libcrypto-1_1.dll",
        "libcrypto-1_1-x64.dll",
        "libssl-1_1.dll",
        "libssl-1_1-x64.dll",
        "libeay32.dll",
        "ssleay32.dll",
    ]

    found = []
    for dll_name in ssl_dlls:
        dll_path = os.path.join(dll_dir, dll_name)
        if os.path.exists(dll_path):
            size = os.path.getsize(dll_path)
            found.append(f"{dll_name} ({size} bytes)")
        else:
            found.append(f"{dll_name} (缺失)")

    print(f"[SADP] [OpenSSL] DLL 状态: {', '.join(found)}")


def _parse_sadp_response(data: bytes) -> SADPDevice | None:
    """解析 SADP 响应 XML。"""
    try:
        # 移除可能的 BOM 或前导垃圾字节
        text = data.decode("utf-8", errors="ignore")

        # 找到 XML 起始标记
        xml_start = text.find("<DeviceProbe>")
        if xml_start < 0:
            xml_start = text.find("<?xml")
        if xml_start < 0:
            return None

        xml_str = text[xml_start:]
        root = ET.fromstring(xml_str)

        device = SADPDevice()

        # 提取字段（SADP v2/v3 格式兼容）
        def find_text(tag: str, default: str = "") -> str:
            elem = root.find(tag)
            if elem is not None and elem.text:
                return elem.text.strip()
            # 尝试不带命名空间
            elem = root.find(f".//{{*}}{tag}")
            return elem.text.strip() if elem is not None and elem.text else default

        device.mac = find_text("MACAddress") or find_text("macAddress") or ""
        device.ip = find_text("IPv4Address") or find_text("ipv4Address") or find_text("IPAddress") or ""
        device.subnet_mask = find_text("IPv4SubnetMask") or find_text("ipv4SubnetMask") or ""
        device.gateway = find_text("IPv4Gateway") or find_text("ipv4Gateway") or ""
        device.model = find_text("deviceType") or find_text("model") or find_text("DeviceType") or ""
        device.serial_number = find_text("serialNumber") or find_text("SerialNumber") or ""
        device.device_name = find_text("deviceName") or find_text("DeviceName") or ""
        device.firmware_version = find_text("firmwareVersion") or find_text("FirmwareVersion") or ""

        # 激活状态判断
        activated_str = (find_text("activated") or find_text("Activated") or "").lower()
        if activated_str in ("true", "1", "yes"):
            device.activated = True
        elif activated_str in ("false", "0", "no"):
            device.activated = False
        else:
            # 如果没有激活状态字段，通过是否有 IP 判断
            device.activated = bool(device.ip and device.ip != "0.0.0.0")

        # Hikvision MAC 验证
        device.is_hikvision = _is_hikvision_mac(device.mac)

        return device
    except ET.ParseError as e:
        LOG.log("warning", f"SADP XML 解析失败: {e}")
        return None
    except Exception as e:
        LOG.log("warning", f"SADP 响应解析异常: {e}")
        return None


def scan_for_devices(bind_ip: str = "0.0.0.0") -> list[SADPDevice]:
    """扫描 SADP 设备，10 秒超时。

    参数:
        bind_ip: 绑定的本地网卡 IP（用于指定网卡发送多播）

    返回:
        发现的设备列表
    """
    LOG.log("info", f"开始 SADP 设备扫描，超时 {SADP_TIMEOUT_MS}ms...")
    LOG.log("info", f"多播地址: {SADP_MULTICAST_ADDR}:{SADP_PORT}")

    devices: list[SADPDevice] = []
    seen_macs: set[str] = set()
    lock = threading.Lock()

    uuid_str = _generate_uuid()
    probe = _build_probe_xml(uuid_str)

    # ---- 接收线程 ----
    def receiver():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", SADP_PORT))

            # 加入多播组
            sock.setsockopt(
                socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                struct.inet_aton(SADP_MULTICAST_ADDR) + struct.inet_aton(bind_ip)
            )
            sock.settimeout(1.0)

            timeout_at = time.time() + (SADP_TIMEOUT_MS / 1000.0)
            while time.time() < timeout_at:
                try:
                    data, addr = sock.recvfrom(65535)
                    device = _parse_sadp_response(data)
                    if device and device.mac and device.mac not in seen_macs:
                        with lock:
                            seen_macs.add(device.mac)
                            devices.append(device)
                        LOG.log("done", f"发现设备: {device.display_name()} IP={device.ip}")
                except socket.timeout:
                    continue
        except Exception as e:
            LOG.log("error", f"SADP 接收异常: {e}")
        finally:
            sock.close()

    # ---- 发送探测报文 ----
    def sender():
        try:
            send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            send_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            if bind_ip and bind_ip != "0.0.0.0":
                send_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, struct.inet_aton(bind_ip))

            # 发送 3 次探测（间隔 1 秒）
            for i in range(3):
                send_sock.sendto(probe, (SADP_MULTICAST_ADDR, SADP_PORT))
                LOG.log("info", f"SADP 探测报文已发送 (#{i+1})")
                if i < 2:
                    time.sleep(1)
        except Exception as e:
            LOG.log("error", f"SADP 发送异常: {e}")
        finally:
            try:
                send_sock.close()
            except Exception:
                pass

    # 启动接收线程
    recv_thread = threading.Thread(target=receiver, daemon=True)
    recv_thread.start()

    # 主线程发送
    sender()

    # 等待接收线程完成
    recv_thread.join(timeout=(SADP_TIMEOUT_MS / 1000.0) + 2)

    # 过滤 Hikvision 设备
    hikvision_devices = [d for d in devices if d.is_hikvision]
    if hikvision_devices:
        LOG.log("done", f"SADP 扫描完成，发现 {len(hikvision_devices)} 台 Hikvision 设备")
        return hikvision_devices

    # 如果没有 Hikvision OUI 匹配的设备，返回所有设备并警告
    if devices:
        LOG.log("warning", f"发现 {len(devices)} 台设备但无 Hikvision OUI 匹配，仍返回全部")
        return devices

    LOG.log("failed", f"SADP 扫描超时，未发现设备")
    return []


def display_devices(devices: list[SADPDevice]) -> SADPDevice | None:
    """显示设备列表并让用户选择。

    返回:
        选中的设备，或 None
    """
    if not devices:
        return None

    from ptz.core.ui import select_from_list

    item_list = []
    for i, dev in enumerate(devices, 1):
        gw = dev.gateway or "无"
        item_list.append(f"[{i}] {dev.model} | MAC={dev.mac} | IP={dev.ip} | 网关={gw} | {'已激活' if dev.activated else '未激活'}")

    idx = select_from_list(item_list, title="发现设备列表")
    if idx is None:
        return None

    selected = devices[idx - 1]
    LOG.log("done", f"用户选择设备: {selected.display_name()}")
    return selected


def check_device_recorded(mac: str, config_manager) -> dict | None:
    """检查设备是否已记录在 PTZ_config.json 中。

    返回:
        已记录的设备信息，或 None
    """
    from ptz.core.config import _normalize_mac

    norm_mac = _normalize_mac(mac)
    device = config_manager.get_device_by_mac(norm_mac)
    if device:
        LOG.log("info", f"设备已记录: {norm_mac} - {device.get('model', 'Unknown')}")
    else:
        LOG.log("info", f"设备未记录: {norm_mac}")
    return device


# ============================================================
# IP Management
# ============================================================

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
