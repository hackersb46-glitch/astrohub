"""
src/core/ptz_manager.py - PTZ/设备控制管理器 (M1 迁移)

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
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout + 5)
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
# Logger
# ============================================================

_ACCEPTED_LEVELS = {"info", "warning", "error", "done", "failed"}

class Logger:
    """全局日志器。"""
    def __init__(self, log_dir: Path | None = None) -> None:
        from src.config_paths import LOG_DIR as _LOG_DIR
        self.log_dir = log_dir or _LOG_DIR
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self._create_log_file()

    def _create_log_file(self) -> Path:
        today = datetime.now().strftime("%Y%m%d")
        existing = list(self.log_dir.glob(f"log_{today}-*.md"))
        max_seq = 0
        for f in existing:
            stem = f.stem
            parts = stem.rsplit("-", 1)
            if len(parts) == 2:
                try:
                    seq = int(parts[1])
                    if seq > max_seq:
                        max_seq = seq
                except ValueError:
                    continue
        seq = max_seq + 1
        return self.log_dir / f"log_{today}-{seq:03d}.md"

    def log(self, level: str, message: str) -> None:
        level_lower = level.lower()
        if level_lower not in _ACCEPTED_LEVELS:
            raise ValueError(f"未知日志级别 '{level}'")
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S.%f")[:19]
        line = f"[{level_lower}] {timestamp} - {message}"
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        print(line)

LOG = Logger()

# ============================================================
# ConfigManager
# ============================================================

def _normalize_mac(mac: str) -> str:
    """统一 MAC 格式：转大写，横杠置换为冒号。"""
    return mac.strip().replace("-", ":").upper()

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
    """本地配置 + 设备配置管理器，支持原子写入与 MAC 查找。"""

    def __init__(self, local_path: Path, ptz_path: Path) -> None:
        self.local_path = local_path.resolve()
        self.ptz_path = ptz_path.resolve()
        LOG.log("info", f"初始化 ConfigManager: local={self.local_path}, ptz={self.ptz_path}")
        self.create_defaults()

    def create_defaults(self) -> None:
        if not self.local_path.exists():
            _atomic_write(self.local_path, {
                "hostname": "", "cpu_model": "", "ram_gb": 0, "gpu_count": 0,
                "vram_gb": 0, "gpu_names": [],
                "selected_nic": {"name": "", "ip": "", "netmask": "", "gateway": ""},
            })
            LOG.log("done", f"创建本地配置文件: {self.local_path}")
        if not self.ptz_path.exists():
            _atomic_write(self.ptz_path, {"devices": {}})
            LOG.log("done", f"创建设备配置文件: {self.ptz_path}")

    def load_local(self) -> dict:
        with open(self.local_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_local(self, data: dict) -> None:
        _atomic_write(self.local_path, data)

    def load_ptz_config(self) -> dict:
        with open(self.ptz_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_ptz_config(self, data: dict) -> None:
        _atomic_write(self.ptz_path, data)

    def get_device_by_mac(self, mac: str) -> dict | None:
        norm_mac = _normalize_mac(mac)
        config = self.load_ptz_config()
        return config.get("devices", {}).get(norm_mac)

    def upsert_device(self, mac: str, info: dict) -> None:
        norm_mac = _normalize_mac(mac)
        config = self.load_ptz_config()
        devices = config.setdefault("devices", {})

        # 如果设备已存在，合并 capabilities/limits/speed/home 字段（不覆盖）
        existing = devices.get(norm_mac, {})
        for merge_key in ("capabilities", "limits", "speed", "home"):
            if merge_key in existing and merge_key not in info:
                info[merge_key] = existing[merge_key]
            elif merge_key in existing and merge_key in info:
                # 深度合并子字典
                merged = dict(existing[merge_key])
                if isinstance(info[merge_key], dict):
                    merged.update(info[merge_key])
                else:
                    merged = info[merge_key]
                info[merge_key] = merged

        info["mac"] = norm_mac
        info["last_updated"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        devices[norm_mac] = info
        self.save_ptz_config(config)

    def remove_device(self, mac: str) -> bool:
        norm_mac = _normalize_mac(mac)
        config = self.load_ptz_config()
        devices = config.get("devices", {})
        if norm_mac not in devices:
            return False
        del devices[norm_mac]
        config["devices"] = devices
        self.save_ptz_config(config)
        return True

# ============================================================
# CSVRecorder
# ============================================================

class CSVRecorder:
    """CSV 位置记录器：按操作类型生成独立 CSV 文件，0.1s 间隔采样。"""

    def __init__(self, record_dir: Path | None = None) -> None:
        from src.config_paths import RECORD_DIR as _RECORD_DIR
        self.record_dir = record_dir or _RECORD_DIR
        self.record_dir.mkdir(parents=True, exist_ok=True)
        self.csv_path: Path | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._callback = None
        self._seq = 0
        self._today = datetime.now().strftime("%Y%m%d")
        self._find_max_seq()

    def _find_max_seq(self) -> None:
        existing = list(self.record_dir.glob(f"record_*_{self._today}-*.csv"))
        max_seq = 0
        for f in existing:
            stem = f.stem
            parts = stem.rsplit("-", 1)
            if len(parts) == 2:
                try:
                    seq = int(parts[1])
                    if seq > max_seq:
                        max_seq = seq
                except ValueError:
                    continue
        self._seq = max_seq

    def _next_filename(self, operation: str) -> Path:
        self._seq += 1
        return self.record_dir / f"record_{operation}_{self._today}-{self._seq:03d}.csv"

    def start(self, operation: str, callback=None) -> Path:
        with self._lock:
            if self._running:
                self.stop()
            self.csv_path = self._next_filename(operation)
            self._callback = callback
            self._running = True
            with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "pan", "tilt", "zoom"])
            LOG.log("done", f"CSV 录制启动: {self.csv_path}")
            if callback:
                self._thread = threading.Thread(target=self._record_loop, daemon=True)
                self._thread.start()
            return self.csv_path

    def _record_loop(self) -> None:
        while self._running:
            try:
                row = self._callback()
                if row:
                    self.write_row(row.get("pan", 0), row.get("tilt", 0), row.get("zoom", 0))
            except Exception as e:
                LOG.log("warning", f"CSV 采样异常: {e}")
            time.sleep(0.1)

    def write_row(self, pan: float, tilt: float, zoom: float) -> None:
        if not self._running or not self.csv_path:
            return
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S.%f")[:23]
        with self._lock:
            with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([timestamp, pan, tilt, zoom])

    def stop(self) -> None:
        with self._lock:
            self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
            self._thread = None
        if self.csv_path:
            LOG.log("done", f"CSV 录制停止: {self.csv_path}")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def current_path(self) -> Path | None:
        return self.csv_path

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
# ISAPI Client
# ============================================================

@dataclass
class ISAPIResponse:
    """ISAPI 响应封装。"""
    status_code: int
    xml: str = ""
    error_code: int = 0
    error_string: str = ""
    sub_status_code: str = ""

class ISAPIClient:
    """ISAPI HTTP 客户端，使用 Digest Auth。"""

    def __init__(self, ip: str, username: str, password: str, port: int = 80) -> None:
        self.ip = ip
        self.username = username
        self.password = password
        self.port = port
        self.base_url = f"http://{ip}:{port}/ISAPI"
        self.session = requests.Session()
        self.session.auth = HTTPDigestAuth(username, password)
        self.session.headers.update({"Content-Type": "application/xml; charset=UTF-8"})
        self.authenticated = False

    def _parse_error_response(self, response_text: str) -> tuple[int, str, str]:
        try:
            root = ET.fromstring(response_text)
            def find_text(tag: str) -> str:
                for child in root.iter():
                    if child.tag.endswith(tag):
                        return (child.text or "").strip()
                return ""
            code_str = find_text("statusCode")
            string_val = find_text("statusString")
            sub_code = find_text("subStatusCode")
            try:
                code = int(code_str)
            except (ValueError, TypeError):
                code = 0
            return code, string_val, sub_code
        except ET.ParseError:
            return 0, "", ""

    def get(self, endpoint: str) -> ISAPIResponse:
        url = f"{self.base_url}{endpoint}"
        LOG.log("info", f"ISAPI GET: {endpoint}")
        try:
            response = self.session.get(url, timeout=15)
            result = ISAPIResponse(status_code=response.status_code)
            if response.status_code == 200:
                result.xml = response.text
            else:
                result.error_code, result.error_string, result.sub_status_code = \
                    self._parse_error_response(response.text)
            return result
        except requests.exceptions.Timeout:
            return ISAPIResponse(status_code=0, error_string="Timeout")
        except requests.exceptions.ConnectionError as e:
            return ISAPIResponse(status_code=0, error_string=str(e))
        except Exception as e:
            return ISAPIResponse(status_code=0, error_string=str(e))

    def put(self, endpoint: str, xml_body: str) -> ISAPIResponse:
        url = f"{self.base_url}{endpoint}"
        LOG.log("info", f"ISAPI PUT: {endpoint}")
        try:
            response = self.session.put(url, data=xml_body.encode("utf-8"),
                                        headers={"Content-Type": "application/xml; charset=UTF-8"},
                                        timeout=15)
            result = ISAPIResponse(status_code=response.status_code)
            if response.status_code == 200:
                result.xml = response.text
            else:
                result.error_code, result.error_string, result.sub_status_code = \
                    self._parse_error_response(response.text)
            return result
        except requests.exceptions.Timeout:
            return ISAPIResponse(status_code=0, error_string="Timeout")
        except requests.exceptions.ConnectionError as e:
            return ISAPIResponse(status_code=0, error_string=str(e))
        except Exception as e:
            return ISAPIResponse(status_code=0, error_string=str(e))

    def post(self, endpoint: str, xml_body: str) -> ISAPIResponse:
        """HTTP POST to ISAPI endpoint with XML body."""
        url = f"{self.base_url}{endpoint}"
        LOG.log("info", f"ISAPI POST: {endpoint}")
        try:
            response = self.session.post(
                url,
                data=xml_body.encode("utf-8"),
                headers={"Content-Type": "application/xml; charset=UTF-8"},
                timeout=30,
            )
            result = ISAPIResponse(status_code=response.status_code)
            if response.status_code == 200:
                result.xml = response.text
            else:
                result.error_code, result.error_string, result.sub_status_code = \
                    self._parse_error_response(response.text)
            return result
        except requests.exceptions.Timeout:
            return ISAPIResponse(status_code=0, error_string="Timeout")
        except requests.exceptions.ConnectionError as e:
            return ISAPIResponse(status_code=0, error_string=str(e))
        except Exception as e:
            return ISAPIResponse(status_code=0, error_string=str(e))

    def post_binary(self, endpoint: str, xml_body: str, timeout: int = 300) -> bytes | None:
        """从 ISAPI 端点获取二进制响应（用于录像下载等大数据流）。"""
        url = f"{self.base_url}{endpoint}"
        LOG.log("info", f"ISAPI BINARY POST: {endpoint}")
        try:
            response = self.session.post(
                url,
                data=xml_body.encode("utf-8"),
                headers={"Content-Type": "application/xml; charset=UTF-8"},
                stream=True,
                timeout=timeout,
            )
            if response.status_code == 200:
                binary_data = b""
                for chunk in response.iter_content(chunk_size=8192):
                    binary_data += chunk
                return binary_data
            LOG.log("error", f"ISAPI binary POST failed: {endpoint} (status={response.status_code})")
            return None
        except requests.exceptions.Timeout:
            LOG.log("error", f"ISAPI binary POST timeout: {endpoint}")
            return None
        except Exception as e:
            LOG.log("error", f"ISAPI binary POST error: {endpoint}: {e}")
            return None

    def verify_credentials(self) -> bool:
        """验证账号密码是否正确 (P3.2)。

        多端点 GET 验证账号密码是否正确。
        尝试的端点（按顺序）：
          1. /ISAPI/System/deviceInfo        (标准路径)
          2. /ISAPI/System/DeviceInfo        (PascalCase 变体)
          3. /ISAPI/System/status/deviceInfo (带 status 前缀)
          4. /ISAPI/System/capabilities      (设备能力端点)
          5. /ISAPI/DeviceManagement/DeviceInfo (ISAPI v2.0)
          6. /ISAPI/System/network/interfaces   (网络设备信息端点)

        返回: True = 认证成功，False = 认证失败
        """
        # 清除代理环境变量
        for key in list(os.environ.keys()):
            if "proxy" in key.lower():
                del os.environ[key]

        auth_session = requests.Session()
        auth_session.trust_env = False
        auth_session.headers.update({"Content-Type": "application/xml; charset=UTF-8"})

        endpoints = [
            "/System/deviceInfo",
            "/System/DeviceInfo",
            "/System/status/deviceInfo",
            "/System/capabilities",
            "/DeviceManagement/DeviceInfo",
            "/System/network/interfaces",
        ]

        LOG.log("info", f"验证 ISAPI 凭证: {self.username}@{self.ip}:{self.port}")

        for endpoint in endpoints:
            url = f"{self.base_url}{endpoint}"
            auth_session.auth = HTTPDigestAuth(self.username, self.password)
            try:
                response = auth_session.get(url, timeout=5)
                if response.status_code == 200:
                    self.authenticated = True
                    LOG.log("done", f"ISAPI 认证成功 (端点: {endpoint})")
                    auth_session.close()
                    return True
                elif response.status_code == 401:
                    LOG.log("failed", "ISAPI 认证失败 (HTTP 401) - 密码错误")
                    auth_session.close()
                    return False
                # 404 或其他状态继续尝试
                LOG.log("info", f"端点 {endpoint} 返回 {response.status_code}, 继续尝试...")
            except requests.exceptions.Timeout:
                LOG.log("info", f"端点 {endpoint} 超时, 继续尝试...")
                continue
            except requests.exceptions.ConnectionError:
                LOG.log("info", f"端点 {endpoint} 连接失败, 继续尝试...")
                continue
            except Exception as e:
                LOG.log("info", f"端点 {endpoint} 异常: {e}, 继续尝试...")
                continue

        LOG.log("failed", "ISAPI 凭证验证失败: 所有端点均失败")
        auth_session.close()
        return False

    def get_xml_text(self, root: ET.Element, tag: str, default: str = "") -> str:
        for child in root.iter():
            if child.tag.endswith(tag):
                return (child.text or default).strip()
        return default

    def get_xml_int(self, root: ET.Element, tag: str, default: int = 0) -> int:
        text = self.get_xml_text(root, tag, str(default))
        try:
            return int(text)
        except (ValueError, TypeError):
            return default

    def get_xml_float(self, root: ET.Element, tag: str, default: float = 0.0) -> float:
        text = self.get_xml_text(root, tag, str(default))
        try:
            return float(text)
        except (ValueError, TypeError):
            return default

    # ================================================================
    #  二进制响应（截图 / 录像下载）
    # ================================================================

    def _get_binary(self, endpoint: str) -> bytes | None:
        """从 ISAPI 端点获取二进制响应（用于图片 / 视频文件）。"""
        url = f"{self.base_url}{endpoint}"
        LOG.log("info", f"ISAPI BINARY GET: {endpoint}")
        try:
            response = self.session.get(url, timeout=15)
            if response.status_code == 200:
                return response.content
            LOG.log("error", f"ISAPI binary GET 失败: {endpoint} (status={response.status_code})")
            return None
        except requests.exceptions.Timeout:
            LOG.log("error", f"ISAPI binary GET 超时: {endpoint}")
            return None
        except Exception as e:
            LOG.log("error", f"ISAPI binary GET 错误: {endpoint}: {e}")
            return None

    def capture_picture(self, channel: int = ISAPI_CHANNEL) -> bytes | None:
        """通过 ISAPI 直接从摄像头抓取 JPEG 图片。

        使用: GET /Streaming/Channels/{channel}/picture
        """
        endpoint = f"/Streaming/Channels/{channel}/picture"
        return self._get_binary(endpoint)

# ============================================================
# PTZ Controller
# ============================================================

class PTZController:
    """ISAPI PTZ 控制器。"""

    def __init__(self, client: ISAPIClient) -> None:
        self.client = client
        self.channel = ISAPI_CHANNEL
        self.home_preset = DEFAULT_PTZ_PRESET
        self.home_coords = HOME_COORDS

    def _ptz_base(self) -> str:
        return f"/PTZCtrl/channels/{self.channel}"

    def get_position(self) -> dict:
        LOG.log("info", "ISAPI 获取 PTZ 位置")
        result = self.client.get(f"{self._ptz_base()}/status")
        if result.status_code != 200:
            return {}
        try:
            elem = ET.fromstring(result.xml)
            pan = self.client.get_xml_float(elem, "azimuth", 0)
            tilt = self.client.get_xml_float(elem, "elevation", 0)
            zoom = self.client.get_xml_float(elem, "absoluteZoom", 0)
            return {"pan": pan, "tilt": tilt, "zoom": zoom}
        except Exception as e:
            LOG.log("warning", f"解析 PTZ 位置异常: {e}")
            return {}

    def goto_preset(self, preset_id: int) -> bool:
        LOG.log("info", f"ISAPI 移动到预置点: {preset_id}")
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<PTZData version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <presetIndex>{preset_id}</presetIndex>
</PTZData>"""
        result = self.client.put(f"{self._ptz_base()}/presets/{preset_id}/goto", xml)
        return result.status_code == 200

    def set_preset(self, preset_id: int) -> bool:
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<PTZData version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <presetIndex>{preset_id}</presetIndex>
</PTZData>"""
        result = self.client.put(f"{self._ptz_base()}/presets/{preset_id}", xml)
        return result.status_code == 200

    def goto_home(self) -> bool:
        """Move to HOME preset, verify with 20-point strict sampling.

        流程:
        1. goto_preset(10) → 发送移动指令
        2. 等待移动完成 (sleep 2s)
        3. 持续采样20点 (每 0.1s 一次)
        4. 20点全部严格等于预置点10设定值 (P=1800, T=450, Z=10)
        5. 全部匹配 → True，任一不匹配 → False
        """
        import time

        if not self.goto_preset(self.home_preset):
            LOG.log("error", "goto_home: failed to goto preset")
            return False

        time.sleep(2)  # Wait for movement to complete

        # 持续采样20点，每0.1s一次
        expected = self.home_coords
        samples = []
        for i in range(20):
            pos = self.get_position()
            if not pos:
                LOG.log("error", f"goto_home: failed to get position at sample {i+1}/20")
                return False
            samples.append(pos)
            time.sleep(0.1)

        # 20点全部严格等于预置点设定值
        for i, pos in enumerate(samples):
            pan_ok = pos.get("pan", 0) == expected["pan"]
            tilt_ok = pos.get("tilt", 0) == expected["tilt"]
            zoom_ok = pos.get("zoom", 0) == expected["zoom"]
            if not (pan_ok and tilt_ok and zoom_ok):
                LOG.log("warning",
                    f"goto_home: sample {i+1}/20 mismatch. "
                    f"Expected {expected}, got pan={pos.get('pan')}, tilt={pos.get('tilt')}, zoom={pos.get('zoom')}"
                )
                return False

        LOG.log("done", f"goto_home verified: 20/20 samples match {expected}")
        return True

    def wait_stable(self, samples: int = 20, interval: float = 0.1, tolerance: float = 10.0) -> bool:
        """等待 PTZ 位置稳定。读取位置直到连续 samples 次变化小于 tolerance。"""
        import time as _time
        readings = []
        for _ in range(samples):
            pos = self.get_position()
            if pos:
                readings.append(pos)
            _time.sleep(interval)
        if len(readings) < samples:
            return False
        pan_vals = [r["pan"] for r in readings]
        tilt_vals = [r["tilt"] for r in readings]
        zoom_vals = [r["zoom"] for r in readings]
        pan_dev = max(pan_vals) - min(pan_vals)
        tilt_dev = max(tilt_vals) - min(tilt_vals)
        zoom_dev = max(zoom_vals) - min(zoom_vals)
        return pan_dev <= tolerance and tilt_dev <= tolerance and zoom_dev <= 1

    def continuous_move(self, pan: float = 0, tilt: float = 0, zoom: float = 0) -> bool:
        """连续移动 PTZ。

        ISAPI 2.0 格式: panSpeed/tiltSpeed 范围 -10(left/down) 到 10(right/up),
        zoomSpeed -10(out) 到 10(in), 0 = stop.
        """
        # 将 0-100 范围映射到 -10..10 (ISAPI 2.0 规范, panSpeed/tiltSpeed/zoomSpeed ∈ [-10, 10])
        pan_speed = round(pan / 10.0)
        tilt_speed = round(tilt / 10.0)
        zoom_speed = round(zoom / 10.0)

        # 停止移动：使用 /continuous 端点速度全0（设备不支持 /stop 端点）
        if pan_speed == 0 and tilt_speed == 0 and zoom_speed == 0:
            xml = '<?xml version="1.0" encoding="UTF-8"?>'
            xml += '<PTZData version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">'
            xml += '<ptzSpeed>'
            xml += '<pan>0</pan><tilt>0</tilt><zoom>0</zoom>'
            xml += '</ptzSpeed></PTZData>'
            result = self.client.put(f"{self._ptz_base()}/continuous", xml)
            return result.status_code == 200

        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<PTZData version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <ptzSpeed>
    <pan>{pan_speed}</pan>
    <tilt>{tilt_speed}</tilt>
    <zoom>{zoom_speed}</zoom>
  </ptzSpeed>
</PTZData>"""
        result = self.client.put(f"{self._ptz_base()}/continuous", xml)
        return result.status_code == 200

    def stop_move(self) -> bool:
        """停止连续移动。"""
        return self.continuous_move(0, 0, 0)

    def continuous_move_duration(self, pan: float, tilt: float, duration: float) -> list[dict]:
        positions = []
        if not self.continuous_move(pan=pan, tilt=tilt):
            return positions
        start = time.time()
        while time.time() - start < duration:
            pos = self.get_position()
            if pos:
                positions.append(pos)
            time.sleep(SAMPLE_INTERVAL)
        self.stop_move()
        return positions

    def absolute_move(self, pan: float, tilt: float, zoom: float | None = None, speed: int = 50) -> bool:
        zoom_val = f"<absoluteZoom>{zoom}</absoluteZoom>" if zoom is not None else ""
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<PTZData version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <AbsoluteHigh>
    <azimuth>{pan}</azimuth><elevation>{tilt}</elevation>
    {zoom_val}<speed>{speed}</speed>
  </AbsoluteHigh>
</PTZData>"""
        result = self.client.put(f"{self._ptz_base()}/absolute", xml)
        return result.status_code == 200

    def relative_move(self, pan: float, tilt: float, zoom: float = 0) -> bool:
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<PTZData version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <Relative><positionX>{pan}</positionX><positionY>{tilt}</positionY>
  <relativeZoom>{zoom}</relativeZoom></Relative>
</PTZData>"""
        result = self.client.put(f"{self._ptz_base()}/relative", xml)
        return result.status_code == 200

    def zoom_in(self, speed: int = 50) -> bool:
        return self.continuous_move(0, 0, speed)

    def zoom_out(self, speed: int = 50) -> bool:
        return self.continuous_move(0, 0, -speed)

    def zoom_range_test(self) -> dict:
        LOG.log("info", "ZOOM 范围测试")
        result = {"zoom_min": 0, "zoom_max": 0, "supported": False}
        initial_pos = self.get_position()
        if not initial_pos:
            return result
        initial_zoom = initial_pos.get("zoom", 0)
        result["zoom_min"] = initial_zoom
        result["zoom_max"] = initial_zoom
        self.goto_home()
        time.sleep(STABILIZATION_SECONDS)

        self.zoom_in(speed=50)
        time.sleep(2)
        self.stop_move()
        time.sleep(1)
        max_pos = self.get_position()
        if max_pos:
            result["zoom_max"] = max_pos.get("zoom", 0)

        self.zoom_out(speed=50)
        time.sleep(2)
        self.stop_move()
        time.sleep(1)
        min_pos = self.get_position()
        if min_pos:
            result["zoom_min"] = min_pos.get("zoom", 0)

        result["supported"] = True
        self.goto_home()
        return result

# ============================================================
# Motion Tester
# ============================================================

class MotionTester:
    """PTZ 运动测试器。"""

    def __init__(self, ptz: PTZController, recorder: CSVRecorder) -> None:
        self.ptz = ptz
        self.recorder = recorder
        self.results: dict = {}

    def _go_home_and_stabilize(self) -> bool:
        if not self.ptz.goto_home():
            return False
        time.sleep(STABILIZATION_SECONDS)
        return True

    def _sample_position(self) -> dict:
        return self.ptz.get_position()

    def test_continuous_move(self) -> dict:
        result = {"success": False, "positions": [], "home_returned": False}
        if not self._go_home_and_stabilize():
            return result
        self.recorder.start("continuousMove", callback=self._sample_position)
        positions = self.ptz.continuous_move_duration(pan=50, tilt=50, duration=2.0)
        result["positions"] = positions
        self.recorder.stop()
        result["home_returned"] = self.ptz.goto_home()
        if result["home_returned"]:
            result["success"] = True
        return result

    def test_absolute_move(self) -> dict:
        result = {"success": False, "positions": [], "home_returned": False}
        if not self._go_home_and_stabilize():
            return result
        initial_pos = self.ptz.get_position()
        if not initial_pos:
            return result
        target_pan = initial_pos.get("pan", 0) + 10
        self.recorder.start("absoluteMove", callback=self._sample_position)
        success = self.ptz.absolute_move(pan=target_pan, tilt=initial_pos.get("tilt", 0))
        time.sleep(2)
        pos_after = self.ptz.get_position()
        result["positions"].append({"before": initial_pos, "after": pos_after})
        self.recorder.stop()
        if success:
            result["home_returned"] = self.ptz.goto_home()
            if result["home_returned"]:
                result["success"] = True
        return result

    def restore_device(self) -> bool:
        self.recorder.stop()
        self.ptz.stop_move()
        return self.ptz.goto_home()


# ============================================================
# PTZManager - 高层管理器包装
# ============================================================

class PTZManager:
    """PTZ 设备管理器（高层包装）。

    整合 SADP 发现、ISAPI 连接、PTZ 控制能力。
    """

    # 方向映射: 前端 direction -> (pan, tilt) values
    DIRECTION_MAP = {
        "up":       (0, 100),
        "down":     (0, -100),
        "left":     (-100, 0),
        "right":    (100, 0),
        "up-left":  (-100, 100),
        "up-right": (100, 100),
        "down-left": (-100, -100),
        "down-right": (100, -100),
    }

    def __init__(self) -> None:
        LOG.log("info", "PTZManager 初始化完成")
        from src.config_paths import CONFIG_DIR as _CONFIG_DIR
        self.config = ConfigManager(
            local_path=_CONFIG_DIR / "local.json",
            ptz_path=_CONFIG_DIR / "ptz_config.json",
        )
        self.recorder = CSVRecorder()
        self._clients: dict[str, ISAPIClient] = {}
        self._controllers: dict[str, PTZController] = {}
        # {ip: {"username": ..., "password": ..., "port": ...}}
        self._credentials: dict[str, dict[str, str | int]] = {}
        # {mac: device_info_dict} - SADP 发现缓存
        self._discovered: dict[str, SADPDevice] = {}
        # {ip: {"track_id": int, "started_at": float, "started_at_iso": str, "channel": int}} - ISAPI 录像状态
        self._recording_state: dict[str, dict[str, int | float | str]] = {}
        self._credentials = {}
        self._load_saved_credentials()
        self._ftp_config: dict = {}

    def get_config(self) -> ConfigManager:
        return self.config

    # ================================================================
    #  SADP 发现 & 设备管理
    # ================================================================

    def discover_devices(self, bind_ip: str = "0.0.0.0") -> list[dict]:
        """执行 SADP 发现并返回设备列表（dict 格式）。

        优先级：
        1. 官方 SADP SDK (Sadp.dll ctypes)
        2. 纯 Python 多播 (回退方案)
        """
        # ---- 优先使用官方 SDK ----
        if SADP_DLL_AVAILABLE:
            LOG.log("info", "使用官方 SADP SDK 进行设备发现...")
            mgr = SADPManagerDLL()
            sdk_devices = mgr.discover_devices(timeout=3)
            if sdk_devices:
                LOG.log("done", f"SADP SDK 发现 {len(sdk_devices)} 台设备")
                result = []
                for dev_dict in sdk_devices:
                    # 转换为 SADPDevice dataclass 以保持向后兼容
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
                    result.append(self._sadp_to_dict(dev))
                return result

        # ---- 回退: 纯 Python 多播 ----
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
            "source": "sadp",
        }

    # ================================================================
    #  凭据管理
    # ================================================================

    def save_credentials(self, ip: str, username: str, password: str,
                         port: int = 80, mac: str = "", model: str = "",
                         name: str = "") -> None:
        """保存设备凭据到内存 + 配置文件。"""
        self._credentials[ip] = {
            "username": username,
            "password": password,
            "port": port,
        }
        self.config.upsert_device(mac or ip, {
            "ip": ip,
            "username": username,
            "password": password,
            "port": port,
            "model": model,
            "name": name,
            "mac": mac or ip,
            "connected": False,
        })

    def get_credentials(self, ip: str) -> dict | None:
        """获取设备凭据。"""
        return self._credentials.get(ip)

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
                "port": info.get("port", 80),
                "connected": is_connected,
                "online": is_connected,
                "source": "manual",
            }
            if sadp_info:
                entry.update(self._sadp_to_dict(sadp_info))
                entry["source"] = "sadp"
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
                    for _elem in _root.iter():
                        _tag = _elem.tag.split("}")[-1] if "}" in _elem.tag else _elem.tag
                        if _tag == "macAddress" and not mac:
                            mac = (_elem.text or "").strip().replace("-", ":").upper()
                        elif _tag == "model" and not model:
                            model = (_elem.text or "").strip()
                        elif _tag == "serialNumber" and not serial_number:
                            serial_number = (_elem.text or "").strip()
                        elif _tag == "firmwareVersion" and not firmware_version:
                            firmware_version = (_elem.text or "").strip()
                    _session.close()
            except Exception:
                pass

            self.config.upsert_device(mac or ip, {
                "ip": ip,
                "username": username,
                "password": password,
                "port": port,
                "model": model,
                "mac": mac or ip,
                "serial_number": serial_number,
                "firmware_version": firmware_version,
                "name": "",
                "connected": True,
            })
            LOG.log("done", f"PTZ 设备已连接: {ip}")
            return {"success": True, "message": "连接成功", "ip": ip}
        LOG.log("failed", f"PTZ 设备认证失败: {ip}")
        return {"success": False, "message": "认证失败，请检查凭据"}

    def disconnect_device(self, ip: str) -> None:
        self._controllers.pop(ip, None)
        client = self._clients.pop(ip, None)
        if client:
            try:
                client.session.close()
            except Exception:
                pass
        # 更新配置
        ptz_cfg = self.config.load_ptz_config()
        for key, dev in ptz_cfg.get("devices", {}).items():
            if dev.get("ip") == ip:
                dev["connected"] = False
                self.config.save_ptz_config(ptz_cfg)
                break

    def list_controllers(self) -> list[str]:
        return list(self._controllers.keys())

    def is_device_connected(self, ip: str) -> bool:
        return ip in self._controllers

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
        """获取 PTZController。必须先调用 connect_device 建立连接。"""
        if ip not in self._controllers:
            return None, "设备未连接（请先在设备管理页面点击连接）"

        ctrl = self._controllers[ip]
        return ctrl, ""

    def ptz_move(self, ip: str, direction: str, speed: int = 50) -> dict:
        """PTZ 移动控制。

        Args:
            ip: 设备 IP
            direction: up|down|left|right|up-left|up-right|down-left|down-right
            speed: 1-100
        """
        LOG.log("info", f"PTZ 移动: device={ip} direction={direction} speed={speed}")
        ctrl, err = self._get_controller(ip)
        if err:
            LOG.log("failed", f"PTZ 移动失败: device={ip} reason={err}")
            return {"success": False, "message": err}

        if direction not in self.DIRECTION_MAP:
            LOG.log("warning", f"PTZ 移动: 未知方向 {direction}")
            return {"success": False, "message": f"未知方向: {direction}"}

        # speed 1-100 直接传给设备
        pan_val, tilt_val = self.DIRECTION_MAP[direction]
        pan = int(round(pan_val * speed / 100.0))
        tilt = int(round(tilt_val * speed / 100.0))

        success = ctrl.continuous_move(pan=pan, tilt=tilt)
        if success:
            LOG.log("done", f"PTZ 移动成功: device={ip} direction={direction} speed={speed}")
        else:
            LOG.log("failed", f"PTZ 移动失败: device={ip} direction={direction}")
        return {
            "success": success,
            "message": f"PTZ 移动: {direction} (speed={speed})",
            "direction": direction,
            "speed": speed,
        }

    def ptz_home(self, ip: str) -> dict:
        ctrl, err = self._get_controller(ip)
        if err:
            return {"success": False, "message": err}

        success = ctrl.goto_home()
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

    def set_preset(self, ip: str, preset_id: int) -> dict:
        """设置当前位置为预置点。

        路由: POST /api/v1/ptz/{device_id}/preset/{preset_id}/set
        """
        ctrl, err = self._get_controller(ip)
        if err:
            return {"success": False, "message": err}

        success = ctrl.set_preset(preset_id)
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
    #  录像控制：FFmpeg 拉取 RTSP 流 → 本地 record/ 目录
    #  方案说明：
    #    1. 设备端录制需要 HDD/NAS/SD，不适用
    #    2. AstroHub 通过 FFmpeg 主动拉取 RTSP 流，录制到本地 record/ 目录
    #    3. 停止录制后可选通过 FTP 上传到远端服务器（AstroHub 主动连接 FTP）
    #    4. 录制状态使用 _recording_state 跟踪 FFmpeg 进程
    # ================================================================

    def start_recording(self, ip: str, channel: int = ISAPI_CHANNEL, target_name: str = "") -> dict:
        """通过 FFmpeg 录制 RTSP 流到本地 record/ 目录。"""
        from src.config_paths import RECORD_DIR
        from src.stream.constants import RTSP_DEFAULT_PORT
        creds = self.get_credentials(ip)
        if not creds:
            return {"success": False, "message": f"设备 {ip} 未保存凭据，请先连接设备"}

        username = creds.get("username", "admin")
        password = creds.get("password", "")
        rtsp_port = creds.get("rtsp_port", RTSP_DEFAULT_PORT)
        rtsp_url = f"rtsp://{username}:{password}@{ip}:{rtsp_port}/Streaming/Channels/101"

        RECORD_DIR.mkdir(parents=True, exist_ok=True)
        filename = generate_filename(device_ip=ip, extension='.mp4')
        filepath = RECORD_DIR / filename

        cmd = [
            "ffmpeg", "-y",
            "-rtsp_transport", "tcp",
            "-timeout", "5000000",
            "-i", rtsp_url,
            "-c", "copy",
            "-an",  # 去掉音频（pcm_alaw 不支持 MP4）
            "-f", "mp4",
            "-movflags", "+frag_keyframe+empty_moov",
            str(filepath),
        ]

        try:
            # Check if already recording
            if ip in self._recording_state:
                return {"success": False, "message": f"设备 {ip} 已在录制中"}

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Health check: wait 2 seconds to ensure FFmpeg doesn't crash immediately
            time.sleep(2)
            if proc.poll() is not None:
                exit_code = proc.poll()
                LOG.log("failed", f"FFmpeg 启动后立即退出: {ip}, exit_code={exit_code}")
                return {"success": False, "message": f"FFmpeg 启动失败 (exit={exit_code})，请检查 RTSP 流是否可达"}

            start_time = time.time()
            self._recording_state[ip] = {
                "pid": proc.pid,
                "process": proc,
                "started_at": start_time,
                "filepath": str(filepath),
            }
            LOG.log("done", f"录像已启动: {ip} PID={proc.pid} → {filepath}")
            return {
                "success": True,
                "message": f"录像已启动: {ip}",
                "data": {
                    "pid": proc.pid,
                    "filepath": str(filepath),
                    "filename": filename,
                    "started_at": start_time,
                },
            }
        except Exception as e:
            LOG.log("failed", f"启动 FFmpeg 失败: {e}")
            return {"success": False, "message": f"启动录像失败: {e}"}

    def stop_recording(self, ip: str) -> dict:
        """停止 FFmpeg 录制进程，可选上传到 FTP 服务器。"""
        if ip not in self._recording_state:
            return {"success": False, "message": f"设备 {ip} 当前未在录制"}

        state = self._recording_state[ip]
        proc = state.get("process")
        started_at = state.get("started_at", time.time())
        filepath = state.get("filepath", "")

        if not proc:
            del self._recording_state[ip]
            return {"success": False, "message": "录制进程不存在"}

        # 终止 FFmpeg 进程
        try:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        except Exception as e:
            LOG.log("warning", f"终止 FFmpeg 进程异常: {e}")
            try:
                proc.kill()
            except Exception:
                pass

        if proc.returncode is not None:
            LOG.log("info", f"FFmpeg 进程退出码: {proc.returncode}")

        duration = round(time.time() - started_at, 1)
        file_size = 0
        if filepath and os.path.exists(filepath):
            file_size = os.path.getsize(filepath)

        del self._recording_state[ip]

        # FTP 上传（如果配置了）
        ftp_result = None
        if getattr(self, '_ftp_config', None) and self._ftp_config.get("enabled"):
            ftp_result = self._upload_to_ftp(filepath)

        filename_out = os.path.basename(filepath) if filepath else ""
        result = {
            "success": True,
            "message": f"录像已停止: {ip}",
            "data": {
                "filepath": filepath,
                "filename": filename_out,
                "size": file_size,
                "duration_seconds": duration,
            },
        }
        if ftp_result:
            result["data"]["ftp"] = ftp_result

        if filepath and file_size > 0:
            LOG.log("done", f"录像文件: {filepath} ({file_size} bytes, {duration}s)")

        return result

    # ================================================================
    #  FTP 录像上传（AstroHub 主动连接 FTP 服务器）
    # ================================================================

    def configure_ftp(self, host: str, port: int = 21, username: str = "",
                      password: str = "", remote_dir: str = "/recordings",
                      enabled: bool = True) -> dict:
        """配置 FTP 服务器连接信息。"""
        self._ftp_config = {
            "enabled": enabled,
            "host": host,
            "port": port,
            "username": username,
            "password": password,
            "remote_dir": remote_dir,
        }
        LOG.log("info", f"FTP 已配置: {host}:{port}/{remote_dir}")
        return {"success": True, "message": f"FTP 已配置: {host}:{port}"}

    def _upload_to_ftp(self, filepath: str) -> dict:
        """上传录像文件到 FTP 服务器。"""
        if not filepath or not os.path.exists(filepath):
            return {"success": False, "message": "文件不存在"}

        if not getattr(self, '_ftp_config', None) or not self._ftp_config.get("enabled"):
            return {"success": False, "message": "FTP 未启用"}

        from ftplib import FTP

        config = self._ftp_config
        try:
            ftp = FTP()
            ftp.connect(config["host"], config["port"], timeout=30)
            ftp.login(config.get("username", ""), config.get("password", ""))

            remote_dir = config.get("remote_dir", "/recordings")
            try:
                ftp.cwd(remote_dir)
            except Exception:
                # 目录不存在则创建
                dirs = remote_dir.strip("/").split("/")
                current = ""
                for d in dirs:
                    current += "/" + d
                    try:
                        ftp.cwd(current)
                    except Exception:
                        ftp.mkd(current)
                ftp.cwd(remote_dir)

            filename = os.path.basename(filepath)
            with open(filepath, "rb") as f:
                ftp.storbinary(f"STOR {filename}", f)

            file_size = os.path.getsize(filepath)
            ftp.quit()

            LOG.log("done", f"FTP 上传成功: {filename} ({file_size} bytes)")
            return {
                "success": True,
                "message": f"FTP 上传成功: {filename}",
                "remote_path": f"{remote_dir}/{filename}",
                "size": file_size,
            }
        except Exception as e:
            LOG.log("failed", f"FTP 上传失败: {e}")
            return {"success": False, "message": f"FTP 上传失败: {e}"}
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




