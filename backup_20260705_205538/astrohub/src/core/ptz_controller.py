"""
src/core/ptz_controller.py - PTZ/设备控制管理器 (M1 迁移)

SADP发现 / ISAPI通信 / PTZ控制 / 运动控制

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import csv
import json
import os
import platform
import socket
import struct
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import xml.etree.ElementTree as ET

from src.core.net_detector import find_available_ip, suggest_target_ip
from src.core.file_naming import generate_filename
from src.ptz.isapi.ptz import PTZController
from src.ptz.isapi.client import ISAPIClient, ISAPIResponse

try:
    import requests
    from requests.auth import HTTPDigestAuth
except ImportError:
    pass

# ============================================================
# Constants (from M1)
# ============================================================

SADP_MULTICAST_ADDR = "239.255.255.250"
SADP_PORT = 37020
SADP_TIMEOUT_MS = 3000
ISAPI_CHANNEL = 1
DEFAULT_PTZ_PRESET = 10
HOME_COORDS = {"pan": 1800, "tilt": 450, "zoom": 10}
PTZ_MAX_SPEED = 100
PTZ_MIN_SPEED = 1
STABILIZATION_SECONDS = 2
STABLE_POINTS_REQUIRED = 20
STABLE_POINT_DEVIATION = 0
SAMPLE_INTERVAL = 0.1
DEFAULT_USERNAME = "admin"

HIKVISION_MAC_OUI = {
    "28:57:BE", "4C:BD:8F", "54:C4:15", "C0:56:E3", "E0:50:8B",
}

def check_reachable(ip: str, timeout: int = 3) -> bool:
    """通过 PING 检测 IP 可达性。"""
    system = platform.system()
    if system == "Windows":
        cmd = f"ping -n 1 -w {timeout * 1000} {ip}"
    else:
        cmd = f"ping -c 1 -W {timeout} {ip}"
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout + 5,
                                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
        # Windows: 不通的IP也会返回自身IP的回复(returncode=0)，需要检查输出
        if system == "Windows":
            output = result.stdout.lower()
            # 这些关键字说明 ping 实际不通
            unreachable_markers = ['unreachable', '无法访问', 'destination host', 'ttl expired', 'general failure', 'transmit failed']
            for marker in unreachable_markers:
                if marker in output:
                    return False
            # 有正常回复且有 TTL = 真正可达
            return result.returncode == 0 and 'ttl=' in output
        return result.returncode == 0
    except Exception:
        return False

# ============================================================
# Logger — 复用 src/ptz/core/logger.py (PTZLogger)
# ============================================================
from src.ptz.core.logger import LOG  # noqa: E402

# ============================================================
# ConfigManager
# ============================================================

def _normalize_mac(mac: str) -> str:
    """统一 MAC 格式：无分隔符小写。"""
    return mac.strip().replace(":", "").replace("-", "").lower()

def _atomic_write(path: Path, data: dict) -> None:
    """通过 tempfile + os.replace() 安全写入 JSON 文件，保证原子性。"""
    path = path.resolve()
    dir_ = path.parent
    dir_.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

class ConfigManager:
    """本地配置 + 设备配置管理器。
    
    v6.10: 统一使用 data/devices/{mac}/ 目录。
    """

    def __init__(self, local_path: Path, ptz_path: Path) -> None:
        self.local_path = local_path.resolve()
        self.ptz_path = ptz_path.resolve()
        from src.config_paths import DEVICES_DIR, REGISTRY_FILE
        self._devices_dir = DEVICES_DIR
        self._registry_file = REGISTRY_FILE
        LOG.log("info", f"初始化 ConfigManager: devices_dir={self._devices_dir}")
        self.create_defaults()

    def create_defaults(self) -> None:
        self._devices_dir.mkdir(parents=True, exist_ok=True)
        if not self.local_path.exists():
            _atomic_write(self.local_path, {
                "hostname": "", "cpu_model": "", "ram_gb": 0, "gpu_count": 0,
                "vram_gb": 0, "gpu_names": [],
                "selected_nic": {"name": "", "ip": "", "netmask": "", "gateway": ""},
            })
            LOG.log("done", f"创建本地配置文件: {self.local_path}")

    def load_local(self) -> dict:
        with open(self.local_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_local(self, data: dict) -> None:
        _atomic_write(self.local_path, data)

    def load_ptz_config(self) -> dict:
        """加载设备配置。v6.10: 只读取 devices/{mac}/info.json。"""
        devices = {}
        if self._devices_dir.exists():
            for info_file in self._devices_dir.rglob("info.json"):
                try:
                    with open(info_file, "r", encoding="utf-8") as f:
                        info = json.load(f)
                        mac = info.get("mac", "")
                        if mac:
                            norm_mac = _normalize_mac(mac)
                            devices[norm_mac] = info
                except Exception:
                    continue
        return {"devices": devices}

    def save_ptz_config(self, data: dict) -> None:
        """保存设备配置。v6.10: 写入 devices/{mac}/info.json + registry.json。"""
        devices = data.get("devices", {})
        for mac, info in devices.items():
            norm_mac = _normalize_mac(mac)
            device_dir = self._devices_dir / norm_mac
            device_dir.mkdir(parents=True, exist_ok=True)
            info_path = device_dir / "info.json"
            info["mac"] = norm_mac
            info["last_updated"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
            _atomic_write(info_path, info)
        # v6.30: 更新 registry.json - 同时设置 active_device 和 last_connected
        registry = {"devices": {}, "active_device": "", "last_connected": ""}
        for mac, info in devices.items():
            registry["devices"][mac] = {
                "name": info.get("name", ""),
                "model": info.get("model", ""),
                "ip": info.get("ip", ""),
                "last_seen": info.get("last_updated", ""),
            }
        if devices:
            first_mac = list(devices.keys())[0]
            registry["active_device"] = first_mac
            registry["last_connected"] = first_mac
        _atomic_write(self._registry_file, registry)

    def get_device_by_mac(self, mac: str) -> dict | None:
        """v6.10: 读取 devices/{mac}/info.json。"""
        norm_mac = _normalize_mac(mac)
        info_path = self._devices_dir / norm_mac / "info.json"
        if info_path.exists():
            try:
                with open(info_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def upsert_device(self, mac: str, info: dict) -> None:
        """v6.10: 写入 devices/{mac}/info.json + registry.json。"""
        norm_mac = _normalize_mac(mac)
        device_dir = self._devices_dir / norm_mac
        device_dir.mkdir(parents=True, exist_ok=True)
        info_path = device_dir / "info.json"

        # 如果设备已存在，合并字段
        existing = {}
        if info_path.exists():
            try:
                with open(info_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                pass

        for merge_key in ("capabilities", "limits", "speed", "home"):
            if merge_key in existing and merge_key not in info:
                info[merge_key] = existing[merge_key]
            elif merge_key in existing and merge_key in info:
                merged = dict(existing[merge_key])
                if isinstance(info[merge_key], dict):
                    merged.update(info[merge_key])
                else:
                    merged = info[merge_key]
                info[merge_key] = merged

        info["mac"] = norm_mac
        info["last_updated"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        if not info.get("first_seen"):
            info["first_seen"] = info["last_updated"]
        _atomic_write(info_path, info)

        # v6.30: 更新 registry.json - 同时设置 active_device 和 last_connected
        registry = {"devices": {}, "active_device": norm_mac, "last_connected": norm_mac}
        if self._registry_file.exists():
            try:
                with open(self._registry_file, "r", encoding="utf-8") as f:
                    registry = json.load(f)
            except Exception:
                pass
        registry["devices"][norm_mac] = {
            "name": info.get("name", ""),
            "model": info.get("model", ""),
            "ip": info.get("ip", ""),
            "last_seen": info["last_updated"],
        }
        registry["active_device"] = norm_mac
        registry["last_connected"] = norm_mac
        _atomic_write(self._registry_file, registry)

    def remove_device(self, mac: str) -> bool:
        """v6.10: 删除 devices/{mac}/ 目录 + 更新 registry.json。"""
        norm_mac = _normalize_mac(mac)
        device_dir = self._devices_dir / norm_mac
        if device_dir.exists():
            import shutil
            shutil.rmtree(device_dir)
        # v6.30: 更新 registry.json - 清除 active_device 和 last_connected
        if self._registry_file.exists():
            try:
                with open(self._registry_file, "r", encoding="utf-8") as f:
                    registry = json.load(f)
                if norm_mac in registry.get("devices", {}):
                    del registry["devices"][norm_mac]
                if registry.get("active_device") == norm_mac:
                    registry["active_device"] = ""
                if registry.get("last_connected") == norm_mac:
                    registry["last_connected"] = ""
                _atomic_write(self._registry_file, registry)
            except Exception:
                pass
        return True

# ============================================================
# SADP Discovery (官方 DLL 封装优先，纯 Python 多播为备用方案)
# ============================================================

SADP_DLL_AVAILABLE = False
try:
    from src.core.sadp_discovery import SADPManager as SADPManagerDLL
    SADP_DLL_AVAILABLE = True
except ImportError as e:
    LOG.log("warning", f"Sadp.dll 封装不可用: {e}，使用纯 Python 多播备用")

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

def _is_hikvision_mac(mac: str) -> bool:
    normalized = mac.replace("-", ":").upper()
    return normalized[:8] in HIKVISION_MAC_OUI

def _parse_sadp_response(data: bytes) -> SADPDevice | None:
    """解析 SADP 响应 XML。

    SADP 响应格式可能是：
    1. 纯 XML: <?xml...?><DeviceProbe>...</DeviceProbe>
    2. Binary header + XML: 4或8字节 header + XML
       - v2: \x00\x00\x00\x00 或 \xFF\xFF\xFF\xFF + 4字节大端长度 + XML
       - v3: "usdp" + 4字节大端长度 + XML
    """
    try:
        text = None
        xml_str = None

        # ---- 策略1：尝试直接作为 XML ----
        raw_text = data.decode("utf-8", errors="ignore")
        if "<DeviceProbe>" in raw_text or "<sadpDeviceInfo>" in raw_text or "<?xml" in raw_text:
            text = raw_text

        # ---- 策略2：尝试跳过 binary header ----
        if text is None and len(data) > 8:
            # 检查是否有 known magic bytes
            has_magic = False
            if data[:4] == b"usdp":
                has_magic = True
            elif data[:4] in (b"\x00\x00\x00\x00", b"\xff\xff\xff\xff"):
                has_magic = True
            elif data[:4] in (b"\x00\x00\x00\x01",):
                has_magic = True

            if has_magic:
                # 尝试从 binary data 中提取 XML
                # 跳过 header (4或8字节)，找 XML
                for start_offset in [4, 8, 10, 12]:
                    if start_offset < len(data):
                        chunk = data[start_offset:].decode("utf-8", errors="ignore")
                        if "<?xml" in chunk or "<Device" in chunk or "<sadp" in chunk:
                            text = chunk
                            break

        if text is None:
            LOG.log("warning", f"SADP 响应不含 XML, 前100B hex: {data[:100].hex()}")
            return None

        # 找到 XML 起始位置
        xml_start = text.find("<DeviceProbe>")
        if xml_start < 0:
            xml_start = text.find("<sadpDeviceInfo>")
        if xml_start < 0:
            xml_start = text.find("<?xml")
        if xml_start < 0:
            LOG.log("warning", f"SADP 响应不含 XML: {repr(text[:200])}")
            return None

        xml_str = text[xml_start:]
        LOG.log("info", f"SADP XML 前100字符: {xml_str[:100]}")

        root = ET.fromstring(xml_str)
        device = SADPDevice()

        def find_text(tag: str, default: str = "") -> str:
            elem = root.find(tag)
            if elem is not None and elem.text:
                return elem.text.strip()
            elem = root.find(f".//{{*}}{tag}")
            if elem is not None and elem.text:
                return elem.text.strip()
            for prefix in ("ipv4", "IPv4", "ip", "IP"):
                elem = root.find(f".//{{*}}{prefix}{tag}")
                if elem is not None and elem.text:
                    return elem.text.strip()
                elem = root.find(f"{prefix}{tag}")
                if elem is not None and elem.text:
                    return elem.text.strip()
            return default

        def find_text_ns(tag: str, default: str = "") -> str:
            """在子树中递归查找（处理嵌套命名空间）。"""
            for elem in root.iter():
                local_name = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                if local_name == tag and elem.text:
                    return elem.text.strip()
            return default

        # 提取字段
        device.mac = (
            find_text("MACAddress") or find_text_ns("MACAddress")
            or find_text("macAddress") or find_text_ns("macAddress") or ""
        )
        device.ip = (
            find_text("IPv4Address") or find_text_ns("IPv4Address")
            or find_text("ipv4Address") or find_text_ns("ipv4Address")
            or find_text("IPAddress") or find_text_ns("IPAddress") or ""
        )
        device.subnet_mask = (
            find_text("IPv4SubnetMask") or find_text_ns("IPv4SubnetMask")
            or find_text("ipv4SubnetMask") or find_text_ns("ipv4SubnetMask") or ""
        )
        device.gateway = (
            find_text("IPv4Gateway") or find_text_ns("IPv4Gateway")
            or find_text("ipv4Gateway") or find_text_ns("ipv4Gateway") or ""
        )
        device.model = (
            find_text("deviceType") or find_text_ns("deviceType")
            or find_text("model") or find_text_ns("model")
            or find_text("DeviceType") or ""
        )
        device.serial_number = (
            find_text("serialNumber") or find_text_ns("serialNumber")
            or find_text("SerialNumber") or ""
        )
        device.device_name = (
            find_text("deviceName") or find_text_ns("deviceName")
            or find_text("DeviceName") or ""
        )
        device.firmware_version = (
            find_text("firmwareVersion") or find_text_ns("firmwareVersion")
            or find_text("FirmwareVersion") or ""
        )

        activated_str = (find_text("activated") or find_text_ns("activated") or "").lower()
        if activated_str in ("true", "1", "yes"):
            device.activated = True
        elif activated_str in ("false", "0", "no"):
            device.activated = False
        else:
            device.activated = bool(device.ip and device.ip != "0.0.0.0")

        device.is_hikvision = _is_hikvision_mac(device.mac)
        if device.mac:
            LOG.log("info", f"SADP 解析完成: MAC={device.mac} IP={device.ip} 型号={device.model}")
        return device
    except ET.ParseError as e:
        LOG.log("warning", f"SADP XML 解析失败: {e}")
        return None
    except Exception as e:
        import traceback
        LOG.log("warning", f"SADP 响应解析异常: {e}")
        LOG.log("warning", f"解析堆栈: {traceback.format_exc()}")
        return None

def _get_local_ip() -> str:
    """获取本机网卡的真实 IP 地址（用于 SADP 多播）。"""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "127.0.0.1"

def scan_for_devices(bind_ip: str = "0.0.0.0") -> list[SADPDevice]:
    """扫描 SADP 设备。

    优先级：
    1. 官方 Sadp.dll (如果可用)
    2. 纯 Python 多播 (备用方案)
    """
    if SADP_DLL_AVAILABLE:
        LOG.log("info", "使用官方 Sadp.dll 进行设备扫描")
        return _scan_via_sadp_dll()
    LOG.log("warning", "Sadp.dll 不可用，使用纯 Python 多播备用方案")
    return _scan_via_multicast(bind_ip)


def _scan_via_sadp_dll() -> list[SADPDevice]:
    """通过官方 Sadp.dll 进行设备发现."""
    try:
        mgr = SADPManagerDLL()
        devices_raw = mgr.discover_devices(timeout=6)
        result = []
        for d in devices_raw:
            device = SADPDevice()
            device.mac = d.get("mac", "").replace("-", ":")
            device.ip = d.get("ip", "")
            device.subnet_mask = d.get("subnet_mask", "")
            device.gateway = d.get("gateway", "")
            device.model = d.get("model", "")
            device.serial_number = d.get("serial_number", "")
            device.device_name = d.get("device_name", "")
            device.firmware_version = d.get("firmware_version", "")
            device.activated = d.get("activated", False)
            device.is_hikvision = d.get("is_hikvision", False)
            if device.mac:
                result.append(device)
                LOG.log("done", f"SADP DLL 发现设备: {device.display_name()} IP={device.ip}")

        if result:
            LOG.log("info", f"SADP DLL 扫描结束: 发现 {len(result)} 台设备")
        else:
            LOG.log("warning", "SADP DLL 扫描: 未发现设备")
        return result
    except Exception as e:
        LOG.log("error", f"SADP DLL 扫描异常: {e}")
        LOG.log("warning", "回退到纯 Python 多播...")
        return _scan_via_multicast(bind_ip="0.0.0.0")


def _scan_via_multicast(bind_ip: str = "0.0.0.0") -> list[SADPDevice]:
    """纯 Python 多播备用方案."""
    actual_ip = _get_local_ip()  # 获取本机真实 IP 用于多播接口绑定
    devices: list[SADPDevice] = []
    seen_macs: set[str] = set()
    uuid_str = uuid.uuid4().hex
    probe = f"""<?xml version="1.0" encoding="UTF-8"?>
<Probe><Uuid>{uuid_str}</Uuid><Types>inquiry</Types></Probe>""".encode("utf-8")

    # 关键：单个 socket 绑定到 SADP_PORT，既发送又接收
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # Windows SO_REUSEPORT
    if platform.system() == "Windows":
        try:
            sock.setsockopt(socket.SOL_SOCKET, 0x18, 1)
        except Exception:
            pass

    try:
        sock.bind(("", SADP_PORT))
        LOG.log("info", f"Socket 已绑定到 0.0.0.0:{SADP_PORT}")
    except OSError as e:
        LOG.log("warning", f"绑定 0.0.0.0:{SADP_PORT} 失败: {e}, 尝试备用方案...")
        sock.close()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", SADP_PORT))
        LOG.log("info", f"备用方案绑定成功: 0.0.0.0:{SADP_PORT}")

    # 加入多播组
    try:
        mreq = struct.pack("4s4s", socket.inet_aton(SADP_MULTICAST_ADDR), socket.inet_aton(actual_ip))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        LOG.log("info", f"已加入多播组 {SADP_MULTICAST_ADDR} via {actual_ip}")
    except Exception as e:
        LOG.log("warning", f"加入多播组失败: {e}")

    try:
        # ---- 发送探测报文（关键：绑定到 SADP_PORT 让设备 unicast 回这个端口）----
        send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if platform.system() == "Windows":
                try:
                    send_sock.setsockopt(socket.SOL_SOCKET, 0x18, 1)
                except Exception:
                    pass
            send_sock.bind(("", SADP_PORT))
            send_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            send_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(actual_ip))
            LOG.log("info", f"发送 socket 绑定到 :{SADP_PORT}, 发送接口: {actual_ip}")
            for i in range(3):
                send_sock.sendto(probe, (SADP_MULTICAST_ADDR, SADP_PORT))
                LOG.log("info", f"SADP probe #{i+1} 已发送 to {SADP_MULTICAST_ADDR}:{SADP_PORT}")
                time.sleep(1)
        except Exception as e:
            import traceback
            LOG.log("error", f"SADP 发送异常: {e}")
            LOG.log("error", f"发送堆栈: {traceback.format_exc()}")
        finally:
            send_sock.close()
            LOG.log("info", "发送 socket 已关闭")

        # ---- 接收响应 ----
        LOG.log("info", "开始接收响应...")
        sock.settimeout(0.5)
        timeout_at = time.time() + (SADP_TIMEOUT_MS / 1000.0)
        while time.time() < timeout_at:
            try:
                data, addr = sock.recvfrom(65535)
                LOG.log("info", f"收到 [{len(data)}B] from {addr[0]}:{addr[1]}")
                try:
                    raw = data.decode("utf-8", errors="ignore")[:400]
                    LOG.log("info", f"原始数据: {raw}")
                except Exception:
                    LOG.log("info", f"十六进制: {data[:200].hex()}")
                device = _parse_sadp_response(data)
                if device:
                    LOG.log("info", f"解析成功: MAC={device.mac} IP={device.ip} model={device.model}")
                if device and device.mac and device.mac not in seen_macs:
                    seen_macs.add(device.mac)
                    devices.append(device)
                    LOG.log("done", f"发现设备: {device.display_name()} IP={device.ip}")
            except socket.timeout:
                continue

    finally:
        try:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP,
                            struct.pack("4s4s", socket.inet_aton(SADP_MULTICAST_ADDR), socket.inet_aton(actual_ip)))
        except Exception:
            pass
        sock.close()
        LOG.log("info", "接收 socket 已关闭")

    LOG.log("info", f"SADP 扫描结束: 发现 {len(devices)} 台设备")
    for d in devices:
        LOG.log("info", f"  MAC={d.mac} IP={d.ip} model={d.model} 激活={d.activated}")

    hikvision_devices = [d for d in devices if d.is_hikvision]
    if hikvision_devices:
        return hikvision_devices
    if devices:
        LOG.log("warning", f"发现 {len(devices)} 台设备但无 Hikvision OUI 匹配，仍返回全部")
    return devices


# ============================================================
class PTZDeviceController:
    """PTZ 设备管理器（高层包装）。

    整合 SADP 发现、ISAPI 连接、PTZ 控制能力。
    """

    # 方向映射: 前端 direction -> (pan, tilt) values
    DIRECTION_MAP = {
        "up":       (0, 1),
        "down":     (0, -1),
        "left":     (-1, 0),
        "right":    (1, 0),
        "up-left":  (-1, 1),
        "up-right": (1, 1),
        "down-left": (-1, -1),
        "down-right": (1, -1),
    }

    def __init__(self) -> None:
        LOG.log("info", "PTZDeviceController 初始化完成")
        from src.config_paths import CONFIG_DIR as _CONFIG_DIR
        self.config = ConfigManager(
            local_path=_CONFIG_DIR / "local.json",
            ptz_path=_CONFIG_DIR / "ptz_config.json",
        )
        self._clients: dict[str, ISAPIClient] = {}
        self._controllers: dict[str, PTZController] = {}
        # {ip: {"username": ..., "password": ..., "port": ...}}
        self._credentials: dict[str, dict[str, str | int]] = {}
        # {mac: device_info_dict} - SADP 发现缓存
        self._discovered: dict[str, SADPDevice] = {}
        self._credentials = {}
        # 持久化 SADP 实例（后台持续运行，即时返回）
        self._sadp_mgr = None
        if SADP_DLL_AVAILABLE:
            try:
                self._sadp_mgr = SADPManagerDLL()
                self._sadp_mgr.start_discovery()
                self._sadp_mgr.send_inquiry()
                LOG.log("done", "SADP 后台发现已启动")
            except Exception as e:
                LOG.log("warning", f"SADP 启动失败: {e}")
        self._load_saved_credentials()

    def get_config(self) -> ConfigManager:
        return self.config

    # ================================================================
    #  SADP 发现 & 设备管理
    # ================================================================

    def discover_devices(self, bind_ip: str = "0.0.0.0") -> list[dict]:
        """返回已发现的设备列表（即时返回，不等待）。
        
        v7.117: 使用持久化 SADP 实例，后台持续运行，点击即时返回。
        """
        if self._sadp_mgr:
            # 发送 inquiry 触发设备广播
            self._sadp_mgr.send_inquiry()
            sdk_devices = self._sadp_mgr.discover_devices()
            if sdk_devices:
                for dev_dict in sdk_devices:
                    dev = SADPDevice()
                    dev.mac = _normalize_mac(dev_dict.get("mac", ""))
                    dev.ip = dev_dict.get("ip", "")
                    dev.subnet_mask = dev_dict.get("subnet_mask", "")
                    dev.gateway = dev_dict.get("gateway", "")
                    dev.model = dev_dict.get("model", "")
                    dev.serial_number = dev_dict.get("serial_number", "")
                    dev.device_name = dev_dict.get("device_name", "")
                    dev.firmware_version = dev_dict.get("firmware_version", "")
                    dev.activated = dev_dict.get("activated", False)
                    dev.is_hikvision = dev_dict.get("is_hikvision", False)
                    self._discovered[dev.mac] = dev
                return [self._sadp_to_dict(d) for d in self._discovered.values()]

        # 回退: 纯 Python 多播
        LOG.log("warning", "SADP SDK 不可用，使用纯 Python 多播发现...")
        devices = scan_for_devices(bind_ip=bind_ip)
        result = []
        for d in devices:
            d.mac = _normalize_mac(d.mac)
            self._discovered[d.mac] = d
            result.append(self._sadp_to_dict(d))
        return result

    def get_discovered_devices(self) -> list[dict]:
        """返回已缓存的发现设备列表。"""
        return [self._sadp_to_dict(d) for d in self._discovered.values()]

    def _sadp_to_dict(self, d: SADPDevice) -> dict:
        return {
            "mac": d.mac,
            "ip": d.ip,
            "subnet_mask": d.subnet_mask,
            "gateway": d.gateway,
            "model": d.model,
            "serial_number": d.serial_number,
            "device_name": d.device_name,
            "firmware_version": d.firmware_version,
            "activated": d.activated,
            "is_hikvision": d.is_hikvision,
        }

    # ================================================================
    #  凭据管理
    # ================================================================

    def save_credentials(self, ip: str, username: str, password: str,
                         port: int = 80, mac: str = "", model: str = "",
                         name: str = "") -> None:
        """保存设备凭据到内存 + 配置文件。
        
        v7.17: 必须有真实 MAC 地址才能保存。
        """
        if not mac or mac == ip:
            LOG.log("warning", f"拒绝保存无效 MAC: {mac} (IP: {ip})")
            return
        
        self._credentials[ip] = {
            "username": username,
            "password": password,
            "port": port,
        }
        self.config.upsert_device(mac, {  # v7.17: 只用真实 MAC 作为 key
            "ip": ip,
            "username": username,
            "password": password,
            "port": port,
            "model": model,
            "name": name,
            "mac": mac,  # v7.17: 真实 MAC
            "connected": False,
        })

    def get_credentials(self, ip: str) -> dict | None:
        """获取设备凭据（含设备名称）。
        
        v7.105: 优先从内存读取，回退文件，含 device_name 字段。
        """
        # 1. 内存优先
        creds = self._credentials.get(ip)
        if creds:
            return creds
        
        # 2. 内存无，从文件回退读取
        try:
            config = self.config.load_ptz_config()
            devices = config.get("devices", {})
            for mac, dev in devices.items():
                if dev.get("ip") == ip:
                    username = dev.get("username")
                    password = dev.get("password")
                    if username and password is not None:
                        creds = {
                            "username": username,
                            "password": password,
                            "port": dev.get("port", 80),
                            "mac": mac,
                            "model": dev.get("model", ""),
                            "device_name": dev.get("name", "") or dev.get("device_name", ""),
                        }
                        self._credentials[ip] = creds
                        return creds
        except Exception:
            pass
        
        return None

    def remove_credentials(self, ip: str) -> bool:
        """移除设备凭据。"""
        self._credentials.pop(ip, None)
        # 从配置中也移除
        config = self.config.load_ptz_config()
        devices = config.get("devices", {})
        # 通过 IP 或 MAC 查找
        for key, dev in list(devices.items()):
            if dev.get("ip") == ip or key == ip:
                return self.config.remove_device(key)
        return False

    def _load_saved_credentials(self) -> None:
        """启动时从配置文件加载已保存的凭据."""
        try:
            config = self.config.load_ptz_config()
            devices = config.get("devices", {})
            for key, dev in devices.items():
                ip = dev.get("ip", key)
                if ip and "username" in dev and "password" in dev:
                    self._credentials[ip] = {
                        "username": dev["username"],
                        "password": dev["password"],
                        "port": dev.get("port", 80),
                        "mac": dev.get("mac", ""),
                        "model": dev.get("model", ""),
                        "name": dev.get("name", ""),
                        "serial_number": dev.get("serial_number", ""),
                        "firmware_version": dev.get("firmware_version", ""),
                    }
                    LOG.log("info", f"已加载凭据: {ip} ({dev.get('model', '')})")
            if self._credentials:
                LOG.log("done", f"已加载 {len(self._credentials)} 个设备凭据")
        except Exception as e:
            LOG.log("warning", f"加载凭据失败: {e}")

    def list_stored_devices(self) -> list[dict]:
        """列出所有已保存的设备（手动添加的）。"""
        config = self.config.load_ptz_config()
        devices = config.get("devices", {})
        result = []
        for mac, info in devices.items():
            ip = info.get("ip", "")
            is_connected = ip in self._controllers
            sadp_info = self._discovered.get(mac)
            entry = {
                "mac": mac,
                "ip": ip,
                "name": info.get("name", ""),
                "model": info.get("model", ""),
                "gateway": info.get("gateway", ""),  # v6.02
                "subnet_mask": info.get("subnet_mask", ""),  # v6.02
                "port": info.get("port", 80),
                "connected": is_connected,
                "online": is_connected,
            }
            if sadp_info:
                # 合并 SADP 信息，但不覆盖 name
                sadp_dict = self._sadp_to_dict(sadp_info)
                sadp_dict.pop("name", None)  # 移除可能的 name 字段
                entry.update(sadp_dict)
            result.append(entry)
        return result

    # ================================================================
    #  设备认证连接
    # ================================================================

    def connect_device(self, ip: str, username: str, password: str,
                        port: int = 80) -> dict | None:
        """连接设备，返回连接结果 dict（含成功/失败信息）。

        返回值:
            {"success": True/False, "message": ..., "device_info": ...}
        """
        if ip in self._controllers:
            # 已连接，更新状态
            ptz_cfg = self.config.load_ptz_config()
            for key, dev in ptz_cfg.get("devices", {}).items():
                if dev.get("ip") == ip:
                    dev["connected"] = True
                    self.config.save_ptz_config(ptz_cfg)
                    break
            return {"success": True, "message": "设备已连接"}

        client = ISAPIClient(ip=ip, username=username, password=password, port=port)
        if client.verify_credentials():
            self._clients[ip] = client
            controller = PTZController(client)
            self._controllers[ip] = controller
            self._credentials[ip] = {
                "username": username,
                "password": password,
                "port": port,
            }
            # 保存凭据到配置文件
            mac = ""
            model = ""
            serial_number = ""
            firmware_version = ""
            # 尝试从发现缓存获取
            for sadp_dev in self._discovered.values():
                if sadp_dev.ip == ip:
                    mac = sadp_dev.mac
                    model = sadp_dev.model
                    serial_number = sadp_dev.serial_number
                    firmware_version = sadp_dev.firmware_version
                    break

            # 尝试从 ISAPI 获取设备详细信息
            try:
                import xml.etree.ElementTree as ET
                import requests
                from requests.auth import HTTPDigestAuth

                _session = requests.Session()
                _session.auth = HTTPDigestAuth(username, password)
                _resp = _session.get(f"http://{ip}:{port}/ISAPI/System/deviceInfo", timeout=3)
                if _resp.status_code == 200:
                    _root = ET.fromstring(_resp.text)
                    device_name = ""
                    for _elem in _root.iter():
                        _tag = _elem.tag.split("}")[-1] if "}" in _elem.tag else _elem.tag
                        if _tag == "macAddress" and not mac:
                            mac = (_elem.text or "").strip().replace(":", "-").upper()
                        elif _tag == "model" and not model:
                            model = (_elem.text or "").strip()
                        elif _tag == "deviceName" and not device_name:
                            device_name = (_elem.text or "").strip()
                        elif _tag == "serialNumber" and not serial_number:
                            serial_number = (_elem.text or "").strip()
                        elif _tag == "firmwareVersion" and not firmware_version:
                            firmware_version = (_elem.text or "").strip()
                    _session.close()
            except Exception:
                device_name = ""

            self.config.upsert_device(mac or ip, {
                "ip": ip,
                "username": username,
                "password": password,
                "port": port,
                "model": model,
                "mac": mac or ip,
                "serial_number": serial_number,
                "firmware_version": firmware_version,
                "name": device_name,
                "connected": True,
            })
            
            # v6.51: 更新 registry.json 的 active_device
            norm_mac = mac.replace(":", "").replace("-", "").lower() if mac else ""
            if norm_mac:
                try:
                    registry_file = self.config._registry_file
                    registry = {}
                    if registry_file.exists():
                        registry = json.loads(registry_file.read_text(encoding='utf-8'))
                    registry["active_device"] = norm_mac
                    registry["last_connected"] = norm_mac
                    _atomic_write(registry_file, registry)
                except Exception:
                    pass
            
            LOG.log("done", f"PTZ 设备已连接: {ip}")
            # v6.01: 返回设备名称和详细步骤
            device_display = device_name or model or ip
            return {
                "success": True, 
                "message": f"设备 [{device_display}] 连接成功",
                "steps": [
                    {"step": "ISAPI 认证", "status": "success"},
                ],
                "ip": ip,
                "name": device_name,
                "model": model,
            }
        LOG.log("failed", f"PTZ 设备认证失败: {ip}")
        return {"success": False, "message": "认证失败，请检查凭据"}

    def disconnect_device(self, ip: str) -> None:
        """v6.30: 断开设备连接。清除 active_device，保留 last_connected 用于下次快速连接。"""
        self._controllers.pop(ip, None)
        client = self._clients.pop(ip, None)
        if client:
            try:
                client.session.close()
            except Exception:
                pass
        
        # 更新设备状态
        ptz_cfg = self.config.load_ptz_config()
        disconnected_mac = None
        for key, dev in ptz_cfg.get("devices", {}).items():
            if dev.get("ip") == ip:
                dev["connected"] = False
                disconnected_mac = key
                self.config.save_ptz_config(ptz_cfg)
                break
        
        # v6.31: 清除 active_device，保留 last_connected
        if disconnected_mac:
            try:
                registry_file = self.config._registry_file
                if registry_file.exists():
                    registry = json.loads(registry_file.read_text(encoding='utf-8'))
                    if registry.get('active_device') == disconnected_mac:
                        registry['active_device'] = ""
                        # last_connected 保留不变
                        _atomic_write(registry_file, registry)
                        LOG.log("info", f"registry.json active_device cleared for {disconnected_mac}, last_connected preserved")
            except Exception as e:
                LOG.log("warning", f"更新 registry.json 失败: {e}")

    def list_controllers(self) -> list[str]:
        return list(self._controllers.keys())

    def is_device_connected(self, ip: str) -> bool:
        return ip in self._controllers

    def get_connected_device(self) -> dict | None:
        """v7.10: 返回 last_connected 设备信息（用于快速连接）。
        
        注意：此方法返回的是"上次连接的设备"，不一定是"当前连接的设备"。
        前端应该通过检查 IP 是否在 _controllers 中判断是否实际连接。
        """
        import json
        from src.config_paths import REGISTRY_FILE, DEVICES_DIR
        
        try:
            # v7.10: 读取 last_connected（用于快速连接）
            if REGISTRY_FILE.exists():
                registry = json.loads(REGISTRY_FILE.read_text(encoding='utf-8'))
                last_mac = registry.get('last_connected', '').strip()
                
                # last_connected 为空表示从未连接过
                if not last_mac:
                    return None
                
                # 从 devices/{mac}/info.json 读取设备详情
                info_file = DEVICES_DIR / last_mac / 'info.json'
                if info_file.exists():
                    info = json.loads(info_file.read_text(encoding='utf-8'))
                    creds = info.get('credentials', {})
                    return {
                        'ip': info.get('ip'),
                        'mac': last_mac,
                        'name': info.get('name'),
                        'model': info.get('model'),
                        'username': creds.get('username') or info.get('username'),
                        'password': creds.get('password') or info.get('password'),
                        'port': info.get('port', 80),
                        'device_name': info.get('device_name'),
                    }
        except Exception as e:
            print(f'[PTZDeviceController] get_connected_device error: {e}')
        
        return None

    # ================================================================
    #  设备信息获取
    # ================================================================

    def get_device_info(self, ip: str) -> dict:
        """通过 ISAPI 获取设备详细信息。"""
        if ip not in self._clients:
            # 尝试自动连接
            creds = self.get_credentials(ip)
            if creds:
                client = ISAPIClient(ip=ip, username=creds["username"],
                                     password=creds["password"], port=creds.get("port", 80))
                if not client.verify_credentials():
                    return {"error": "认证失败"}
                self._clients[ip] = client
                self._controllers[ip] = PTZController(client)
            else:
                return {"error": "设备未连接且无凭据"}

        client = self._clients[ip]
        info = {}

        # 系统信息
        result = client.get("/System/deviceInfo")
        if result.status_code == 200:
            try:
                root = ET.fromstring(result.xml)
                info["device_name"] = client.get_xml_text(root, "deviceName", "")
                info["model"] = client.get_xml_text(root, "model", "")
                info["serial_number"] = client.get_xml_text(root, "serialNumber", "")
                info["firmware_version"] = client.get_xml_text(root, "firmwareVersion", "")
                info["mac_address"] = client.get_xml_text(root, "macAddress", "")
            except Exception as e:
                LOG.log("warning", f"解析设备信息异常: {e}")

        # 网络配置
        net_result = client.get("/Network/interfaces/1")
        if net_result.status_code == 200:
            try:
                root = ET.fromstring(net_result.xml)
                info["network"] = {
                    "ip": client.get_xml_text(root, "ipAddress", ""),
                    "subnet_mask": client.get_xml_text(root, "subnetMask", ""),
                    "gateway": client.get_xml_text(root, "defaultGateway", ""),
                }
            except Exception:
                pass

        # PTZ 位置
        if ip in self._controllers:
            info["ptz_position"] = self._controllers[ip].get_position()

        return info

    # ================================================================
    #  IP 修改
    # ================================================================

    def modify_device_network(self, ip: str, new_ip: str, subnet_mask: str,
                               gateway: str) -> dict:
        """修改设备网络配置。

        优先级：
        1. ISAPI（已连接设备）- 可靠
        2. SADP（发现未连接设备）- 需要密码，可能失败
        """
        # 方案1：通过 ISAPI 修改（设备已连接时）
        if ip in self._controllers:
            client = self._clients[ip]
            LOG.log("info", f"通过 ISAPI 修改网络: {ip} -> {new_ip}")
            # ISAPI 网络配置 endpoint
            xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Network xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <isDHCP>false</isDHCP>
  <IPAddress>{new_ip}</IPAddress>
  <SubnetMask>{subnet_mask}</SubnetMask>
  <DefaultGateway>{gateway}</DefaultGateway>
</Network>"""
            result = client.put("/Network/channels/1/Network", xml)
            if result.status_code == 200:
                time.sleep(3)
                if check_reachable(new_ip, timeout=3):
                    return {"success": True, "message": f"IP 修改成功: {ip} -> {new_ip}",
                            "new_ip": new_ip, "method": "ISAPI"}

        # 方案2：SADP 修改（需要设备密码）
        cred = self._credentials.get(ip)
        password = cred["password"] if cred else None

        sadp_dev = None
        for d in self._discovered.values():
            if d.ip == ip:
                sadp_dev = d
                break

        if not sadp_dev:
            return {"success": False, "message": "设备未发现且未连接"}

        if not password:
            return {"success": False, "message": "需要设备密码才能修改 IP"}

        return self._modify_ip_via_sadp(sadp_dev, new_ip, subnet_mask, gateway, password)

    def _modify_ip_via_sadp(self, sadp_dev, new_ip: str, subnet_mask: str,
                             gateway: str, password: str) -> dict:
        """通过 SADP V40 DLL 修改 IP（官方 API，不绕开 DLL）。

        流程:
        1. 检测 IP 是否被占用 (PING)
        2. 调用 SADP V40 DLL SADP_ModifyDeviceNetParam_V40
        3. 查询错误码含义
        4. 修改后等待 5 秒，验证新 IP 可达
        """
        # P2.5: 判断 IP 是否被占用
        if check_reachable(new_ip, timeout=2):
            LOG.log("warning", f"目标 IP {new_ip} 已被占用，需更换 IP")
            return {
                "success": False,
                "message": f"目标 IP {new_ip} 已被占用，请更换",
                "error_code": "IP_CONFLICT",
            }

        # 通过 SADP SDK DLL 修改网络参数（官方 API）
        if SADP_DLL_AVAILABLE:
            LOG.log("info", f"SADP DLL 修改 IP: MAC={sadp_dev.mac} -> {new_ip}")
            try:
                mgr = SADPManagerDLL()
                result = mgr.modify_device_network(
                    mac=sadp_dev.mac,
                    password=password,
                    new_ip=new_ip,
                    subnet_mask=subnet_mask,
                    gateway=gateway,
                    http_port=getattr(sadp_dev, 'http_port', 80),
                )
                if result.get("success"):
                    # 等待设备应用新 IP (P2.5: 10秒)
                    LOG.log("info", "等待 10 秒让设备应用新 IP...")
                    time.sleep(3)
                    if check_reachable(new_ip, timeout=3):
                        sadp_dev.ip = new_ip
                        sadp_dev.gateway = gateway
                        sadp_dev.subnet_mask = subnet_mask
                        self.config.upsert_device(sadp_dev.mac, {
                            "ip": new_ip,
                            "model": sadp_dev.model,
                            "mac": sadp_dev.mac,
                        })
                        return {
                            "success": True,
                            "message": f"IP 修改成功: {sadp_dev.ip} -> {new_ip}",
                            "new_ip": new_ip,
                            "method": "SADP_DLL",
                        }
                    return {"success": False, "message": f"IP 修改成功但 {new_ip} 不可达"}
                # DLL 返回错误
                error_msg = result.get("message", "修改失败")
                LOG.log("error", f"SADP DLL 修改失败: {error_msg}")
                return {
                    "success": False,
                    "message": error_msg,
                    "method": "SADP_DLL",
                }
            except Exception as e:
                LOG.log("error", f"SADP DLL 修改 IP 异常: {e}")
                LOG.log("warning", "回退到备用方案（不可用）")

        # 回退方案: DLL 不可用时返回错误而非使用裸 socket
        return {
            "success": False,
            "message": "SADP DLL 不可用，无法修改 IP。请复制 Sadp.dll 到项目目录。",
        }

    def modify_reachable_with_retry(
        self,
        mac: str,
        password: str,
        original_ip: str,
        target_ip: str | None = None,
        subnet_mask: str = "255.255.255.0",
        gateway: str = "",
        max_retries: int = 3,
    ) -> dict:
        """IP 修改循环验证流程（P2.4 → P2.5 完整流程）。

        P2.4: 判断设备 IP 可达性
          - 可达 → 跳过 P2.5，直接进入后续步骤
          - 不可达 → 进入 P2.5 修改 IP

        P2.5: 修改设备 IP
          - 目标 IP 被占用 → 自动找可用 IP（从 .64 开始扫描）
          - 修改后等待 10s → 重新 SADP 扫描确认
          - 最多 max_retries 次循环

        如果未传入 target_ip，自动调用 suggest_target_ip() 获取（同网段 .64）。
        如果 target_ip 被占用，调用 find_available_ip() 找可用 IP。
        """
        # ---- P2.4: IP 可达性判断 ----
        if check_reachable(original_ip, timeout=3):
            LOG.log("info", f"P2.4: 设备 IP {original_ip} 已可达，继续 P2.5 修改 IP")
        else:
            LOG.log("info", f"P2.4: 设备 IP {original_ip} 不可达，继续 P2.5 修改 IP")

        LOG.log("info", f"P2.4: 设备 IP {original_ip} 不可达，进入 P2.5 修改 IP")

        # ---- P2.5: 修改设备 IP ----
        # 自动获取目标 IP（同网段 .64）
        if not target_ip:
            target_ip = suggest_target_ip()
            if not target_ip:
                return {
                    "success": False,
                    "message": "无法自动获取目标 IP，请手动指定或检查网络配置",
                }
            LOG.log("info", f"自动获取目标 IP: {target_ip}（同网段 .64）")
        else:
            LOG.log("info", f"使用用户指定目标 IP: {target_ip}")

        # 自动获取网关（本地网卡网关）
        if not gateway:
            from src.core.net_detector import get_local_subnet
            _, gw_mask, gw = get_local_subnet()
            if gw:
                gateway = gw
                LOG.log("info", f"自动获取网关: {gateway}")
            # subnet_mask 也从本地获取
            if subnet_mask == "255.255.255.0" and gw_mask:
                subnet_mask = gw_mask

        LOG.log("info", f"P2.5: 开始 IP 修改循环: {original_ip} -> {target_ip} (最多{max_retries}次)")

        for attempt in range(1, max_retries + 1):
            LOG.log("info", f"  第 {attempt}/{max_retries} 次尝试")

            # 检测 IP 占用，如果被占用则寻找可用 IP
            if check_reachable(target_ip, timeout=2):
                LOG.log("warning", f"目标 IP {target_ip} 已被占用，寻找可用 IP...")
                available_ip = find_available_ip()
                if not available_ip:
                    return {
                        "success": False,
                        "message": f"目标 IP {target_ip} 已被占用，且无可用 IP",
                    }
                target_ip = available_ip
                LOG.log("info", f"使用可用 IP: {target_ip}")

            # 找到设备的 SADP 信息 (MAC 格式兼容: 统一转大写+冒号)
            sadp_dev = None
            norm_mac_target = _normalize_mac(mac)
            for d in self._discovered.values():
                if _normalize_mac(d.mac) == norm_mac_target:
                    sadp_dev = d
                    break

            # 如果 SADP 缓存中没有，重新扫描
            if not sadp_dev:
                LOG.log("info", f"SADP 缓存中无设备 {mac}，重新扫描...")
                self.discover_devices()
                for d in self._discovered.values():
                    if _normalize_mac(d.mac) == norm_mac_target:
                        sadp_dev = d
                        break
                if not sadp_dev:
                    if attempt < max_retries:
                        LOG.log("info", f"重新扫描未找到设备，等待 5 秒后再试...")
                        time.sleep(5)
                        continue
                    return {
                        "success": False,
                        "message": f"SADP 扫描未找到设备 MAC={mac}",
                    }

            # 执行修改
            result = self._modify_ip_via_sadp(
                sadp_dev, target_ip, subnet_mask, gateway, password
            )

            if not result.get("success"):
                LOG.log("warning", f"IP 修改失败: {result.get('message')}")
                if attempt < max_retries:
                    LOG.log("info", "等待 10 秒后重试...")
                    time.sleep(3)
                    # 重新扫描后再试
                    self.discover_devices()
                    continue
                return self._wrap_modify_failure(result)

            # 修改成功，等待设备应用新 IP
            LOG.log("info", f"IP 修改请求已发送，等待 10 秒让设备应用新 IP...")
            time.sleep(3)

            # ---- 重新 SADP 扫描确认 ----
            LOG.log("info", "重新 SADP 扫描确认设备...")
            self.discover_devices()

            # 检查设备是否以新 IP 出现
            found_new_ip = False
            for d in self._discovered.values():
                if _normalize_mac(d.mac) == norm_mac_target and d.ip == target_ip:
                    found_new_ip = True
                    sadp_dev = d
                    break

            if found_new_ip:
                LOG.log("done", f"确认设备 {mac} 已出现在新 IP {target_ip}")
                sadp_dev.ip = target_ip
                sadp_dev.gateway = gateway
                sadp_dev.subnet_mask = subnet_mask

                # 保存到 PTZ_config.json (P2.6) — 包含完整凭据信息
                device_model = sadp_dev.model or ""
                self.config.upsert_device(mac, {
                    "ip": target_ip,
                    "model": device_model,
                    "mac": mac,
                    "username": DEFAULT_USERNAME,
                    "password": password,
                    "name": sadp_dev.device_name or "",
                    "serial_number": sadp_dev.serial_number or "",
                    "activated": sadp_dev.activated,
                })

                return {
                    "success": True,
                    "message": f"IP 修改并确认成功: {target_ip}",
                    "new_ip": target_ip,
                    "attempts": attempt,
                    "method": result.get("method", "SADP_DLL"),
                }
            else:
                LOG.log("warning", f"重新扫描未确认新 IP {target_ip}")
                # 直接 PING 验证
                if check_reachable(target_ip, timeout=3):
                    LOG.log("done", f"PING 确认 {target_ip} 可达")
                    sadp_dev.ip = target_ip
                    sadp_dev.gateway = gateway
                    sadp_dev.subnet_mask = subnet_mask

                    self.config.upsert_device(mac, {
                        "ip": target_ip,
                        "model": sadp_dev.model or "",
                        "mac": mac,
                    })
                    return {
                        "success": True,
                        "message": f"IP 修改并 PING 确认成功: {target_ip}",
                        "new_ip": target_ip,
                        "attempts": attempt,
                        "method": result.get("method", "SADP_DLL"),
                    }

                if attempt < max_retries:
                    LOG.log("info", "等待 5 秒后重试...")
                    time.sleep(5)
                else:
                    return {
                        "success": False,
                        "message": f"多次尝试后仍未确认新 IP {target_ip}",
                    }

        return {
            "success": False,
            "message": f"IP 修改失败，已尝试 {max_retries} 次",
        }

    def auto_reconnect_known_devices(
        self,
        bind_ip: str = "0.0.0.0",
        target_ip: str | None = None,
    ) -> dict:
        """P2.7: 已知设备自动重连。

        流程:
        1. SADP 扫描发现设备
        2. 以 MAC 匹配已保存设备
        3. Ping 验证 IP 是否可达
        4. IP 不可达时用已保存凭据修改 IP
        5. 修改成功后 time.sleep(3) -> 重新扫描确认

        Args:
            bind_ip: SADP 绑定的网卡 IP (默认 "0.0.0.0" = 全部网卡)
            target_ip: 指定目标 IP (默认同网段.64)

        Returns:
            处理结果字典
        """
        LOG.log("info", "P2.7: 开始已知设备自动重连流程...")

        # Step 1: SADP 扫描
        discovered = self.discover_devices(bind_ip=bind_ip)
        if not discovered:
            return {"success": False, "message": "SADP 扫描未发现任何设备"}

        LOG.log("info", f"SADP 扫描发现 {len(discovered)} 台设备")

        # Step 2: 加载已保存设备列表
        config = self.config.load_ptz_config()
        saved_devices = config.get("devices", {})

        if not saved_devices:
            return {"success": True, "message": "无已保存设备，跳过 P2.7", "processed": 0}

        # Step 3: 匹配 + 处理
        results = []
        processed_count = 0

        for dev in discovered:
            dev_mac = dev.get("mac", "").strip()
            if not dev_mac:
                continue

            # 统一 MAC 格式进行匹配
            norm_discovered = _normalize_mac(dev_mac)

            # 尝试匹配已保存设备
            saved = None
            saved_mac_key = None
            for mac_key, saved_info in saved_devices.items():
                norm_saved = _normalize_mac(mac_key)
                if norm_discovered == norm_saved:
                    saved = saved_info
                    saved_mac_key = mac_key
                    break

            if not saved:
                continue  # 不是已知设备，跳过

            device_name = saved.get("name", dev.get("device_name", ""))
            device_model = saved.get("model", dev.get("model", ""))
            saved_password = saved.get("password", "")

            if not saved_password:
                LOG.log("warning", f"已知设备 {norm_discovered} ({device_name}) 无保存密码，跳过")
                results.append({
                    "mac": norm_discovered,
                    "model": device_model,
                    "status": "skipped",
                    "reason": "no_password",
                })
                continue

            dev_ip = dev.get("ip", "")
            LOG.log("info", f"P2.7: 发现已知设备 {norm_discovered} ({device_model}), IP={dev_ip}")

            # P2.4: Ping 验证可达性
            if dev_ip and check_reachable(dev_ip, timeout=3):
                LOG.log("done", f"P2.7: 设备 {norm_discovered} IP {dev_ip} 可达，无需修改")
                results.append({
                    "mac": norm_discovered,
                    "ip": dev_ip,
                    "model": device_model,
                    "status": "reachable",
                })
                processed_count += 1
                continue

            # P2.5: IP 不可达，使用已保存凭据修改
            LOG.log("info", f"P2.7: 设备 {norm_discovered} IP {dev_ip} 不可达，执行 IP 修改...")

            subnet_mask = dev.get("subnet_mask", "255.255.255.0")
            gateway = dev.get("gateway", "")

            # 获取目标 IP
            eff_target_ip = target_ip
            if not eff_target_ip:
                eff_target_ip = suggest_target_ip()
                if not eff_target_ip:
                    results.append({
                        "mac": norm_discovered,
                        "status": "failed",
                        "reason": "no_target_ip",
                    })
                    continue

            if check_reachable(eff_target_ip, timeout=2):
                LOG.log("warning", f"目标 IP {eff_target_ip} 已被占用")
                results.append({
                    "mac": norm_discovered,
                    "status": "failed",
                    "reason": "target_ip_occupied",
                })
                continue

            result = self._modify_ip_via_sadp(
                SADPDevice(
                    mac=norm_discovered.replace(":", "-").lower(),
                    ip=dev_ip,
                    subnet_mask=subnet_mask,
                    gateway=gateway,
                    model=device_model,
                ),
                eff_target_ip, subnet_mask, gateway, saved_password
            )

            if result.get("success"):
                # 等待设备应用新 IP
                time.sleep(3)
                self.discover_devices()  # 重新扫描确认

                # 更新配置
                self.config.upsert_device(norm_discovered, {
                    "ip": eff_target_ip,
                    "model": device_model,
                    "mac": norm_discovered,
                    "name": device_name,
                    "username": DEFAULT_USERNAME,
                    "password": saved_password,
                    "activated": dev.get("activated", False),
                })
                LOG.log("done", f"P2.7: 设备 {norm_discovered} IP 修改确认成功: {eff_target_ip}")
                results.append({
                    "mac": norm_discovered,
                    "old_ip": dev_ip,
                    "new_ip": eff_target_ip,
                    "model": device_model,
                    "status": "modified",
                })
            else:
                LOG.log("error", f"P2.7: 设备 {norm_discovered} IP 修改失败: {result.get('message')}")
                results.append({
                    "mac": norm_discovered,
                    "status": "failed",
                    "reason": result.get("message", "unknown"),
                })

            processed_count += 1

        return {
            "success": True,
            "message": f"P2.7 已知设备自动重连完成，处理 {processed_count} 台设备",
            "processed": processed_count,
            "details": results,
        }

    def _wrap_modify_failure(self, result: dict) -> dict:
        """包装修改失败结果。"""
        msg = result.get("message", "未知错误")
        error_code = result.get("error_code", "")
        detail = f" (错误码: {error_code})" if error_code else ""
        return {
            "success": False,
            "message": f"IP 修改失败: {msg}{detail}",
        }

    # ================================================================
    #  PTZ 高级控制方法
    # ================================================================

    def _get_controller(self, ip: str) -> tuple[PTZController | None, str]:
        """v6.53: 获取 PTZController。如果未连接，尝试从 active_device 自动重连。"""
        # 已连接，直接返回
        if ip in self._controllers:
            return self._controllers[ip], ""
        
        # 未连接，尝试从 active_device 自动重连
        creds = self.get_credentials(ip)
        if creds:
            try:
                client = ISAPIClient(ip=ip, username=creds["username"], password=creds["password"], port=creds.get("port", 80))
                if client.verify_credentials():
                    self._clients[ip] = client
                    controller = PTZController(client)
                    self._controllers[ip] = controller
                    LOG.log("info", f"自动重连成功: {ip}")
                    return controller, ""
            except Exception as e:
                LOG.log("warning", f"自动重连失败: {ip}, {e}")
        
        return None, "设备未连接（请先在设备管理页面点击连接）"

    def ptz_move(self, ip: str, direction: str, speed: int = 50) -> dict:
        """PTZ 移动控制。

        Args:
            ip: 设备 IP
            direction: up|down|left|right|up-left|up-right|down-left|down-right|zoom-in|zoom-out
            speed: 1-100
        """
        LOG.log("info", f"PTZ 移动: device={ip} direction={direction} speed={speed}")
        ctrl, err = self._get_controller(ip)
        if err:
            LOG.log("failed", f"PTZ 移动失败: device={ip} reason={err}")
            return {"success": False, "message": err}

        # Zoom operations - 官方档位映射
        # 档位映射: 1→14, 2→28, 3→43, 4→57, 5→71, 6→86, 7→100
        if 1 <= speed <= 7:
            speed_mapping = {1: 14, 2: 28, 3: 43, 4: 57, 5: 71, 6: 86, 7: 100}
            isapi_speed = speed_mapping.get(speed, 57)
        else:
            isapi_speed = min(max(speed, 0), 100)
        
        if direction == "zoom-in":
            success = ctrl.continuous_move(pan=0, tilt=0, zoom=isapi_speed)
            return {"success": success, "message": f"PTZ zoom-in (档位={speed})", "isapi_speed": isapi_speed}
        elif direction == "zoom-out":
            success = ctrl.continuous_move(pan=0, tilt=0, zoom=-isapi_speed)
            return {"success": success, "message": f"PTZ zoom-out (档位={speed})", "isapi_speed": isapi_speed}
        elif direction == "focus-near":
            success = ctrl.focus_move_continuous('near', speed)
            return {"success": success, "message": f"PTZ focus-near (speed={speed})"}
        elif direction == "focus-far":
            success = ctrl.focus_move_continuous('far', speed)
            return {"success": success, "message": f"PTZ focus-far (speed={speed})"}
        elif direction == "focus-auto":
            success = ctrl.set_focus_mode("auto")
            return {"success": success, "message": "PTZ focus-auto"}

        if direction not in self.DIRECTION_MAP:
            LOG.log("warning", f"PTZ 移动: 未知方向 {direction}")
            return {"success": False, "message": f"未知方向: {direction}"}

        # Pan/Tilt operations - 官方档位映射
        # 官方 web 端: 1-7 档，默认 4 档
        # ISAPI 速度值: 档位7=ISAPI 100 (最快)
        # 档位映射: 1→14, 2→28, 3→43, 4→57, 5→71, 6→86, 7→100
        pan_val, tilt_val = self.DIRECTION_MAP[direction]
        
        if 1 <= speed <= 7:
            speed_mapping = {1: 14, 2: 28, 3: 43, 4: 57, 5: 71, 6: 86, 7: 100}
            isapi_speed = speed_mapping.get(speed, 57)
        else:
            isapi_speed = min(max(speed, 0), 100)
        
        pan = int(pan_val * isapi_speed)
        tilt = int(tilt_val * isapi_speed)

        success = ctrl.continuous_move(pan=pan, tilt=tilt)
        if success:
            LOG.log("done", f"PTZ 移动成功: device={ip} direction={direction} speed={speed}(档位)→isapi={isapi_speed}")
        else:
            LOG.log("failed", f"PTZ 移动失败: device={ip} direction={direction}")
        return {
            "success": success,
            "message": f"PTZ 移动: {direction} (档位={speed})",
            "direction": direction,
            "speed": speed,
            "isapi_speed": isapi_speed,
        }

    def ptz_home(self, ip: str) -> dict:
        ctrl, err = self._get_controller(ip)
        if err:
            return {"success": False, "message": err}

        success = ctrl.goto_preset(10)  # 直接调用 goto_preset(10)
        return {
            "success": success,
            "message": "归位成功" if success else "归位失败",
        }

    def ptz_stop(self, ip: str) -> dict:
        ctrl, err = self._get_controller(ip)
        if err:
            return {"success": False, "message": err}

        success = ctrl.stop_move()
        return {
            "success": success,
            "message": "停止成功" if success else "停止失败",
        }

    def ptz_preset(self, ip: str, preset_id: int) -> dict:
        ctrl, err = self._get_controller(ip)
        if err:
            return {"success": False, "message": err}

        success = ctrl.goto_preset(preset_id)
        return {
            "success": success,
            "message": f"预置位 {preset_id} {'成功' if success else '失败'}",
            "preset_id": preset_id,
        }

    def set_preset(self, ip: str, preset_id: int, name: str = "") -> dict:
        """设置当前位置为预置点。

        路由: POST /api/v1/ptz/{device_id}/preset/{preset_id}/set
        """
        ctrl, err = self._get_controller(ip)
        if err:
            return {"success": False, "message": err}

        success = ctrl.set_preset(preset_id, name=name)
        return {
            "success": success,
            "message": f"预置位 {preset_id} 设置{'成功' if success else '失败'}",
            "preset_id": preset_id,
        }

    def ptz_list_presets(self, ip: str) -> dict:
        """获取设备预置点列表。

        路由: GET /api/v1/ptz/{device_id}/presets
        """
        ctrl, err = self._get_controller(ip)
        if err:
            return {"success": False, "message": err}

        presets = ctrl.list_presets()
        return {
            "success": True,
            "presets": presets,
            "count": len(presets),
        }

    def ptz_absolute(self, ip: str, pan: float, tilt: float,
                     zoom: float | None = None, speed: int = 50) -> dict:
        ctrl, err = self._get_controller(ip)
        if err:
            return {"success": False, "message": err}

        success = ctrl.absolute_move(pan=pan, tilt=tilt, zoom=zoom, speed=speed)
        return {
            "success": success,
            "message": "绝对移动成功" if success else "绝对移动失败",
        }

    def ptz_get_position(self, ip: str) -> dict:
        ctrl, err = self._get_controller(ip)
        if err:
            return {"success": False, "message": err, "data": {}}

        pos = ctrl.get_position()
        return {
            "success": bool(pos),
            "message": "获取位置成功" if pos else "获取位置失败",
            "data": pos,
        }

    # ================================================================
    #  录像管理（ISAPI 原生方法）
    #
    #  架构说明：
    #  之前的 /ContentMgmt/Storage/control 端点返回 404，不适用于 iDS-2DF8C832IXS-A 球机。
    #  正确使用:
    #    PUT /ISAPI/ContentMgmt/record/control/manual/start/tracks/{trackID} — 启动录像
    #    PUT /ISAPI/ContentMgmt/record/control/manual/stop/tracks/{trackID}  — 停止录像
    #    POST /ISAPI/ContentMgmt/search — 搜索设备端录像
    #    POST /ISAPI/ContentMgmt/download — 下载录像到本地
    #  Track ID = channel * 100 + 1（101=通道1主码流）
    #  设备需要配置存储介质（NAS/SD卡），无内置硬盘时 hddList 为空但仍可录像到 NAS。
    # ================================================================

    def _get_isapi_client(self, ip: str) -> ISAPIClient | None:
        """获取已连接的 ISAPIClient，或从凭据创建临时实例。"""
        if ip in self._clients:
            return self._clients[ip]
        creds = self.get_credentials(ip)
        if not creds:
            return None
        port = int(creds.get("port", 80))
        username = str(creds.get("username", "admin"))
        password = str(creds.get("password", ""))
        client = ISAPIClient(ip=ip, username=username, password=password, port=port)
        if client.verify_credentials():
            self._clients[ip] = client
            return client
        return None


    # ================================================================
    #  录像管理（ISAPI 官方方法）
    #
    #  海康官方 ISAPI 录制接口:
    #    PUT /ISAPI/ContentMgmt/record/control/manual/start/tracks/{trackID} — 启动录像
    #    PUT /ISAPI/ContentMgmt/record/control/manual/stop/tracks/{trackID}  — 停止录像
    #  Track ID = channel * 100 + 1（101=通道1主码流）
    # ================================================================

    def start_recording(self, ip: str, channel: int = ISAPI_CHANNEL, target_name: str = "") -> dict:
        """v7.107: 通过 ISAPI 官方方法启动摄像头录像."""
        client = self._get_isapi_client(ip)
        if not client:
            return {"success": False, "message": f"设备 {ip} 未连接或凭据无效"}

        track_id = channel * 100 + 1
        endpoint = f"/ContentMgmt/record/control/manual/start/tracks/{track_id}"
        
        result = client.put(endpoint, "<?xml version=\"1.0\" encoding=\"UTF-8\"?><RecordControl></RecordControl>")
        
        if result.status_code == 200:
            LOG.log("done", f"ISAPI 录像已启动: {ip} track={track_id}")
            return {"success": True, "message": f"录像已启动: {ip}", "data": {"track_id": track_id}}
        else:
            LOG.log("failed", f"ISAPI 启动录像失败: {ip} status={result.status_code}")
            return {"success": False, "message": f"启动录像失败: {result.error_string or result.status_code}"}

    def stop_recording(self, ip: str, channel: int = ISAPI_CHANNEL) -> dict:
        """v7.107: 通过 ISAPI 官方方法停止摄像头录像."""
        client = self._get_isapi_client(ip)
        if not client:
            return {"success": False, "message": f"设备 {ip} 未连接或凭据无效"}

        track_id = channel * 100 + 1
        endpoint = f"/ContentMgmt/record/control/manual/stop/tracks/{track_id}"
        
        result = client.put(endpoint, "<?xml version=\"1.0\" encoding=\"UTF-8\"?><RecordControl></RecordControl>")
        
        if result.status_code == 200:
            LOG.log("done", f"ISAPI 录像已停止: {ip} track={track_id}")
            return {"success": True, "message": f"录像已停止: {ip}", "data": {"track_id": track_id}}
        else:
            LOG.log("failed", f"ISAPI 停止录像失败: {ip} status={result.status_code}")
            return {"success": False, "message": f"停止录像失败: {result.error_string or result.status_code}"}
    def update_device_capabilities(self, mac: str, capabilities: dict) -> bool:
        """更新设备能力信息到配置文件。

        Args:
            mac: 设备 MAC 地址（如传入 IP 则当作 MAC key 使用）
            capabilities: 能力字典，如 {"gain": {"supported": True, "min_val": 1, ...}, ...}
        """
        try:
            norm_mac = _normalize_mac(mac)
            config = self.config.load_ptz_config()
            devices = config.setdefault("devices", {})

            if norm_mac not in devices:
                LOG.log("warning", f"更新 capabilities: 设备 {norm_mac} 未找到，跳过")
                return False

            existing_caps = devices[norm_mac].setdefault("capabilities", {})
            existing_caps.update(capabilities)
            self.config.save_ptz_config(config)
            LOG.log("done", f"设备 {norm_mac} capabilities 已更新: {len(capabilities)} 项")
            return True
        except Exception as e:
            LOG.log("error", f"更新 capabilities 失败: {e}")
            return False

    def update_device_limits(self, mac: str, limits: dict) -> bool:
        """更新设备限位信息到配置文件。

        Args:
            mac: 设备 MAC 地址
            limits: 限位字典，如 {"pan": {"has_limit": False, ...}, "tilt": {"has_flip": True, ...}, ...}
        """
        try:
            norm_mac = _normalize_mac(mac)
            config = self.config.load_ptz_config()
            devices = config.setdefault("devices", {})

            if norm_mac not in devices:
                LOG.log("warning", f"更新 limits: 设备 {norm_mac} 未找到，跳过")
                return False

            existing_limits = devices[norm_mac].setdefault("limits", {})
            existing_limits.update(limits)
            self.config.save_ptz_config(config)
            LOG.log("done", f"设备 {norm_mac} limits 已更新: {list(limits.keys())}")
            return True
        except Exception as e:
            LOG.log("error", f"更新 limits 失败: {e}")
            return False

    def update_device_speed(self, mac: str, speed_data: dict) -> bool:
        """更新设备速度测试数据到配置文件。

        Args:
            mac: 设备 MAC 地址
            speed_data: 速度数据字典，如 {"pan_1": {"displacement": 12.3}, ...}
        """
        try:
            norm_mac = _normalize_mac(mac)
            config = self.config.load_ptz_config()
            devices = config.setdefault("devices", {})

            if norm_mac not in devices:
                LOG.log("warning", f"更新 speed: 设备 {norm_mac} 未找到，跳过")
                return False

            existing_speed = devices[norm_mac].setdefault("speed", {})
            existing_speed.update(speed_data)
            self.config.save_ptz_config(config)
            LOG.log("done", f"设备 {norm_mac} speed 数据已更新: {len(speed_data)} 项")
            return True
        except Exception as e:
            LOG.log("error", f"更新 speed 数据失败: {e}")
            return False

    def update_device_home(self, mac: str, home_coords: dict, verified: bool = False) -> bool:
        """更新设备 HOME 位坐标到配置文件。

        Args:
            mac: 设备 MAC 地址
            home_coords: HOME 位坐标，如 {"pan": 1800, "tilt": 450, "zoom": 10}
            verified: 是否已验证
        """
        try:
            norm_mac = _normalize_mac(mac)
            config = self.config.load_ptz_config()
            devices = config.setdefault("devices", {})

            if norm_mac not in devices:
                LOG.log("warning", f"更新 home: 设备 {norm_mac} 未找到，跳过")
                return False

            devices[norm_mac]["home"] = {
                "pan": home_coords.get("pan"),
                "tilt": home_coords.get("tilt"),
                "zoom": home_coords.get("zoom"),
                "verified": verified,
            }
            self.config.save_ptz_config(config)
            LOG.log("done", f"设备 {norm_mac} home 位已更新: {home_coords}")
            return True
        except Exception as e:
            LOG.log("error", f"更新 home 位失败: {e}")
            return False

    def auto_write_advanced_results(self, mac: str, func_results: dict | None = None,
                                      limit_results: dict | None = None,
                                      speed_results: dict | None = None,
                                      home_verified: bool = False) -> dict:
        """自动写入高级功能探测/限位/速度测试结果。

        在 function/limit/speed 测试完成后调用，一次性写入所有结果到配置文件。

        Args:
            mac: 设备 MAC 地址
            func_results: function.py detect_all() 结果
            limit_results: limit.py run_all_tests() 结果
            speed_results: speed.py run_all_tests() 结果
            home_verified: HOME 位是否已验证
        """
        results = {"capabilities_updated": False, "limits_updated": False,
                    "speed_updated": False, "home_updated": False}

        # 从 FunctionDetector 提取 capabilities
        if func_results:
            capabilities = {}
            for item_key, item_result in func_results.items():
                endpoint_def = {}
                if isinstance(item_result, dict):
                    endpoint_def = {
                        "supported": item_result.get("supported", False),
                        "min_val": item_result.get("min_val", 0),
                        "max_val": item_result.get("max_val", 0),
                        "endpoint": item_result.get("endpoint", ""),
                        "test_key": item_result.get("test_key", ""),
                    }
                capabilities[item_key] = endpoint_def
            if capabilities:
                results["capabilities_updated"] = self.update_device_capabilities(mac, capabilities)

        # 从 LimitTester 提取 limits
        if limit_results:
            limits = {}
            pan_min = limit_results.get("pan_min", 0)
            pan_max = limit_results.get("pan_max", 3600)
            tilt_min = limit_results.get("tilt_min", -200)
            tilt_max = limit_results.get("tilt_max", 900)
            has_flip = limit_results.get("has_flip", False)

            limits["pan"] = {
                "has_limit": False,  # Pan 360° 无绝对限位
                "observed_min": pan_min,
                "observed_max": pan_max,
            }
            limits["tilt"] = {
                "has_flip": has_flip,
                "observed_min": tilt_min,
                "observed_max": tilt_max,
            }
            limits["zoom"] = {
                "observed_min": 0,
                "observed_max": 320,
            }
            results["limits_updated"] = self.update_device_limits(mac, limits)

        # 从 SpeedTester 提取 speed
        if speed_results:
            speed_data = {}
            results_map = speed_results.get("results", {})
            for speed_key, speed_val in results_map.items():
                if isinstance(speed_val, dict):
                    speed_data[f"pan_{speed_key}"] = {
                        "set_speed": speed_val.get("set", 0),
                        "actual_speed": speed_val.get("actual", 0),
                        "displacement": speed_val.get("displacement", 0),
                        "delta": speed_val.get("delta", 0),
                    }
            if speed_data:
                results["speed_updated"] = self.update_device_speed(mac, speed_data)

        # 更新 HOME 位
        results["home_updated"] = self.update_device_home(mac, HOME_COORDS, verified=home_verified)

        LOG.log("done", f"设备 {mac} advanced results 自动写入: {results}")
        return results




