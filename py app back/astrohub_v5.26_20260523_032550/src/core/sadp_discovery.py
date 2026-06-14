"""
src/core/sadp_discovery.py - SADP 设备发现 (官方 DLL 封装)

使用官方 Sadp.dll 进行设备发现。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import json
import socket
import subprocess
import ctypes
import ctypes.wintypes
import os
import platform
import threading
import time
from ctypes import WINFUNCTYPE, CFUNCTYPE
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import psutil

# ============================================================
# Constants
# ============================================================

SADP_ADD = 1        # 设备上线
SADP_UPDATE = 2     # 设备更新
SADP_DEC = 3        # 设备离线
SADP_RESTART = 4    # 设备重启
SADP_UPDATEFAIL = 5 # 设备更新失败

# SADP 错误码映射 (from Sadp.h)
SADP_ERROR_CODES = {
    0: "无错误",
    2001: "资源分配失败",
    2002: "SADP 未启动",
    2003: "无网卡",
    2004: "获取适配器信息失败",
    2005: "参数错误",
    2006: "打开适配器失败",
    2007: "发送数据包失败",
    2008: "系统接口调用失败",
    2009: "设备拒绝服务",
    2010: "NPF 驱动安装失败",
    2011: "设备超时",
    2012: "创建 socket 失败",
    2013: "绑定 socket 失败",
    2014: "加入组播失败",
    2015: "发送超时",
    2016: "接收超时",
    2017: "解析 XML 失败",
    2018: "设备已锁定",
    2019: "设备未激活",
    2020: "弱密码",
    2021: "设备已激活",
    2022: "加密串为空",
    2023: "导出文件过期",
    2024: "密码错误",
    2025: "安全答案太长",
    2026: "无效 GUID",
    2027: "答案错误",
    2028: "安全问题数量错误",
    2029: "安全状态错误",
    2030: "加载 Wpcap 失败",
    2031: "导出文件路径不存在",
    2032: "导入文件路径不存在",
    2033: "非法验证码",
    2034: "绑定不存在的设备",
    2035: "超过最大绑定数",
    2036: "邮箱不存在",
    2037: "邮箱格式错误",
    2038: "邮箱未设置",
    2039: "无效重置码",
    2040: "无权限（非管理员或未启动组播）",
    2041: "获取交换码失败",
    2042: "创建 RSA 公私钥失败",
    2043: "BASE64 编码失败",
    2044: "BASE64 解码失败",
    2045: "AES 加密失败",
    2046: "AES 解密失败",
    2047: "IP 地址格式错误",
    2048: "子网掩码格式错误",
    2049: "网关格式错误",
    2050: "DNS 格式错误",
    2051: "端口号错误",
    2052: "设备网络修改失败",
    2053: "设备网络修改超时",
    2054: "设备网络修改被拒绝",
    2055: "MAC 地址格式错误",
    2056: "序列号格式错误",
    2057: "用户名格式错误",
    2058: "密码格式错误",
    2059: "设备名称格式错误",
    2060: "设备能力不支持",
    2061: "设备固件版本不匹配",
    2062: "协议版本不匹配",
    2063: "设备配置冲突",
    2064: "设备资源不足",
    2065: "操作被取消",
}


def sadp_error_message(error_code: int) -> str:
    """获取 SADP 错误码的可读中文描述."""
    return SADP_ERROR_CODES.get(error_code, f"未知错误码: {error_code}")


# ============================================================
# Virtual NIC Management (for SADP Error 2006 workaround)
# ============================================================

def _detect_virtual_nics() -> list[str]:
    """检测系统上的非物理网卡 (隧道/虚拟适配器).
    
    使用 PowerShell Get-NetAdapter 获取所有网卡信息，
    筛选出 Virtual=True 且当前状态为 Up 的非物理网卡.
    
    Returns:
        虚拟网卡名称列表（仅包含已启用的，用于后续恢复）.
    """
    try:
        ps_cmd = (
            "Get-NetAdapter | Where-Object { $_.Virtual -eq $true -and "
            "$_.Status -eq 'Up' } | Select-Object -ExpandProperty Name | "
            "ConvertTo-Json"
        )
        result = subprocess.run(
            ['powershell', '-NoProfile', '-NonInteractive', '-Command', ps_cmd],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            # PowerShell returns JSON array of strings
            names = json.loads(result.stdout.strip())
            if isinstance(names, str):
                names = [names]
            # 过滤掉空名称
            return [n.strip() for n in names if n.strip()]
    except Exception as e:
        print(f"[SADP] 检测虚拟网卡异常: {e}, 跳过临时禁用")
    return []


def _disable_nic(name: str) -> bool:
    """使用 netsh 临时禁用指定网卡."""
    try:
        result = subprocess.run(
            ['netsh', 'interface', 'set', 'interface', name, 'disable'],
            capture_output=True, text=True, timeout=15, check=False,
        )
        if result.returncode == 0:
            print(f"[SADP] 已临时禁用虚拟网卡: {name}")
            return True
        else:
            stderr = result.stderr.strip()
            print(f"[SADP] 禁用网卡 '{name}' 失败: {stderr}")
    except Exception as e:
        print(f"[SADP] 禁用网卡 '{name}' 异常: {e}")
    return False


def _enable_nic(name: str) -> bool:
    """使用 netsh 重新启用指定网卡."""
    try:
        result = subprocess.run(
            ['netsh', 'interface', 'set', 'interface', name, 'enable'],
            capture_output=True, text=True, timeout=15, check=False,
        )
        if result.returncode == 0:
            print(f"[SADP] 已恢复虚拟网卡: {name}")
            return True
        else:
            stderr = result.stderr.strip()
            print(f"[SADP] 启用网卡 '{name}' 失败: {stderr}")
    except Exception as e:
        print(f"[SADP] 启用网卡 '{name}' 异常: {e}")
    return False


class _VirtualNicGuard:
    """上下文管理器: 临时禁用虚拟网卡, 退出时自动恢复.
    
    用于解决 SADP SDK 错误 2006 (打开适配器失败).
    原因: SADP 底层 NPF 驱动无法绑定没有 MAC 地址的虚拟网卡 (如 Wintun 隧道).
    方案: 在 SADP_Start_V40 前临时禁用虚拟网卡, 操作完成后恢复.
    
    保护参数: 保护指定 IP 对应的物理网卡不被禁用.
    """
    def __init__(self, protected_ip: str = ""):
        self._disabled_nics: list[str] = []
        self._protected_ip = protected_ip

    def __enter__(self):
        print(f"[SADP] 虚拟网卡守卫已启用 (protected_ip={self._protected_ip})")
        virtual_nics = _detect_virtual_nics()
        if not virtual_nics:
            return self
        
        print(f"[SADP] 检测到 {len(virtual_nics)} 个虚拟网卡，临时禁用中...")
        for nic_name in virtual_nics:
            # 保护用户选择的物理网卡
            if self._protected_ip and self._ip_matches_nic(self._protected_ip, nic_name):
                print(f"[SADP] 跳过保护网卡: {nic_name} (IP={self._protected_ip})")
                continue
            if _disable_nic(nic_name):
                self._disabled_nics.append(nic_name)
        
        if self._disabled_nics:
            time.sleep(2)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self._disabled_nics:
            return False
        print(f"[SADP] 虚拟网卡已恢复")
        for nic_name in self._disabled_nics:
            _enable_nic(nic_name)
        time.sleep(1)
        return False

    @staticmethod
    def _ip_matches_nic(ip: str, nic_name: str) -> bool:
        """检查 IP 是否与网卡名称关联."""
        try:
            addrs = psutil.net_if_addrs().get(nic_name, [])
            for addr in addrs:
                if addr.family == socket.AF_INET and addr.address == ip:
                    return True
        except Exception:
            pass
        return False  # 不抑制异常

# ============================================================
# DLL Path Resolution (Portable 规范)
# ============================================================

def _find_sadp_dll() -> str:
    """查找 Sadp.dll 路径.
    
    优先级 (从内到外):
    1. PyInstaller 打包模式: exe 同级 lib/Sadp.dll (binaries 打包)
    2. PyInstaller 打包模式: _MEIPASS/lib/Sadp.dll (datas 打包)
    3. 当前 src/core/ 目录下的 Sadp.dll (开发模式, 与代码并存)
    4. SDK 参考路径 (仅开发模式回退)
    
    禁止硬编码 C:\\sdk\\ 路径。
    """
    import sys

    # === PyInstaller 打包模式 ===
    if hasattr(sys, '_MEIPASS'):
        # 方式A: exe 同级 lib/ (binaries 放入 dist/)
        exe_parent = Path(sys.executable).parent
        exe_lib = exe_parent / 'lib' / 'Sadp.dll'
        if exe_lib.exists():
            return str(exe_lib)
        # 方式B: _MEIPASS/lib/ (datas 打包方式)
        meipass = Path(sys._MEIPASS)
        meipass_lib = meipass / 'lib' / 'Sadp.dll'
        if meipass_lib.exists():
            return str(meipass_lib)
        # 方式C: _MEIPASS 根目录
        meipass_root = meipass / 'Sadp.dll'
        if meipass_root.exists():
            return str(meipass_root)

    # === 开发模式 ===
    # 当前 src/core/ 目录下的 Sadp.dll (与代码并存)
    local_sadp = Path(__file__).resolve().parent / "Sadp.dll"
    if local_sadp.exists():
        return str(local_sadp)

    # SDK 参考路径 (仅开发模式回退)
    try:
        from src.config_paths import SDK_LIBS_DIR
        sdk_sadp = SDK_LIBS_DIR / "Sadp.dll"
        if sdk_sadp.exists():
            return str(sdk_sadp)
    except Exception:
        pass

    raise FileNotFoundError(
        f"Sadp.dll not found. Searched: "
        f"1) exe_parent/lib/Sadp.dll, "
        f"2) _MEIPASS/lib/Sadp.dll, "
        f"3) _MEIPASS/Sadp.dll, "
        f"4) src/core/Sadp.dll, "
        f"5) SDK ref/libs/Sadp.dll. "
        "Please copy SDK DLLs to src/core/ for development mode."
    )


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
    import shutil

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
    import shutil

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


# ============================================================
# ctypes Structures (matching SADP header)
# ============================================================

class SADP_DEVICE_INFO(ctypes.Structure):
    """SADP_DEVICE_INFO 对应 C 结构体 (560 bytes)."""
    _fields_ = [
        ("szSeries", ctypes.c_char * 12),
        ("szSerialNO", ctypes.c_char * 48),
        ("szMAC", ctypes.c_char * 20),
        ("szIPv4Address", ctypes.c_char * 16),
        ("szIPv4SubnetMask", ctypes.c_char * 16),
        ("dwDeviceType", ctypes.c_uint),
        ("dwPort", ctypes.c_uint),
        ("dwNumberOfEncoders", ctypes.c_uint),
        ("dwNumberOfHardDisk", ctypes.c_uint),
        ("szDeviceSoftwareVersion", ctypes.c_char * 48),
        ("szDSPVersion", ctypes.c_char * 48),
        ("szBootTime", ctypes.c_char * 48),
        ("iResult", ctypes.c_int),           # 消息类型: 1=上线, 2=更新, 3=离线, 4=重启, 5=失败
        ("szDevDesc", ctypes.c_char * 24),   # 设备描述/型号
        ("szOEMinfo", ctypes.c_char * 24),
        ("szIPv4Gateway", ctypes.c_char * 16),
        ("szIPv6Address", ctypes.c_char * 46),
        ("szIPv6Gateway", ctypes.c_char * 46),
        ("byIPv6MaskLen", ctypes.c_ubyte),
        ("bySupport", ctypes.c_ubyte),
        ("byDhcpEnabled", ctypes.c_ubyte),
        ("byDeviceAbility", ctypes.c_ubyte),
        ("wHttpPort", ctypes.c_ushort),
        ("wDigitalChannelNum", ctypes.c_ushort),
        ("szCmsIPv4", ctypes.c_char * 16),
        ("wCmsPort", ctypes.c_ushort),
        ("byOEMCode", ctypes.c_ubyte),
        ("byActivated", ctypes.c_ubyte),     # 0=已激活, 1=未激活
        ("szBaseDesc", ctypes.c_char * 24),
        ("bySupport1", ctypes.c_ubyte),
        ("byHCPlatform", ctypes.c_ubyte),
        ("byEnableHCPlatform", ctypes.c_ubyte),
        ("byEZVIZCode", ctypes.c_ubyte),
        ("dwDetailOEMCode", ctypes.c_uint),
        ("byModifyVerificationCode", ctypes.c_ubyte),
        ("byMaxBindNum", ctypes.c_ubyte),
        ("wOEMCommandPort", ctypes.c_ushort),
        ("bySupportWifiRegion", ctypes.c_ubyte),
        ("byEnableWifiEnhancement", ctypes.c_ubyte),
        ("byWifiRegion", ctypes.c_ubyte),
        ("bySupport2", ctypes.c_ubyte),
    ]


class SADP_DEVICE_INFO_V40(ctypes.Structure):
    """SADP_DEVICE_INFO_V40 对应 C 结构体.
    
    第一个字段是完整的 SADP_DEVICE_INFO 结构体.
    """
    _fields_ = [
        ("struSadpDeviceInfo", SADP_DEVICE_INFO),
        ("byLicensed", ctypes.c_ubyte),
        ("bySystemMode", ctypes.c_ubyte),
        ("byControllerType", ctypes.c_ubyte),
        ("szEhmoeVersion", ctypes.c_char * 16),
        ("bySpecificDeviceType", ctypes.c_ubyte),
        ("dwSDKOverTLSPort", ctypes.c_uint),
        ("bySecurityMode", ctypes.c_ubyte),
        ("bySDKServerStatus", ctypes.c_ubyte),
        ("bySDKOverTLSServerStatus", ctypes.c_ubyte),
        ("szUserName", ctypes.c_char * 33),  # MAX_USERNAME_LEN + 1
        ("szWifiMAC", ctypes.c_char * 20),
        ("byDataFromMulticast", ctypes.c_ubyte),
        ("bySupportEzvizUnbind", ctypes.c_ubyte),
        ("bySupportCodeEncrypt", ctypes.c_ubyte),
        ("bySupportPasswordResetType", ctypes.c_ubyte),
        ("byEZVIZBindStatus", ctypes.c_ubyte),
        ("szPhysicalAccessVerification", ctypes.c_char * 16),
        ("byRes", ctypes.c_ubyte * 411),
    ]


class SADP_DEV_NET_PARAM(ctypes.Structure):
    """SADP_DEV_NET_PARAM - 用于修改设备网络参数.
    
    注意: 不使用 _pack_=1. C 头文件使用默认结构体对齐，dwSDKOverTLSPort 
    在默认对齐下位于 offset 312。使用 _pack_=1 会导致偏移变为 310，
    DLL 读取错误数据返回 2005 参数错误。
    """
    _fields_ = [
        ("szIPv4Address", ctypes.c_char * 16),          # offset 0
        ("szIPv4SubNetMask", ctypes.c_char * 16),       # offset 16
        ("szIPv4Gateway", ctypes.c_char * 16),          # offset 32
        ("szIPv6Address", ctypes.c_char * 128),         # offset 48
        ("szIPv6Gateway", ctypes.c_char * 128),         # offset 176
        ("wPort", ctypes.c_ushort),                     # offset 304
        ("byIPv6MaskLen", ctypes.c_ubyte),              # offset 306
        ("byDhcpEnable", ctypes.c_ubyte),               # offset 307
        ("wHttpPort", ctypes.c_ushort),                 # offset 308 (2 bytes padding after this)
        ("dwSDKOverTLSPort", ctypes.c_uint),            # offset 312 (default alignment)
        ("byRes", ctypes.c_ubyte * 122),                # offset 316
    ]


class SADP_DEV_RET_NET_PARAM(ctypes.Structure):
    """SADP_DEV_RET_NET_PARAM - 修改网络后的返回参数.
    
    注意: 不使用 _pack_=1，与 C 头文件默认对齐保持一致。
    """
    _fields_ = [
        ("byRetryModifyTime", ctypes.c_ubyte),
        ("bySurplusLockTime", ctypes.c_ubyte),
        ("byRes", ctypes.c_ubyte * 126),
    ]


# ============================================================
# Callback Type
# ============================================================
# CALLBACK on Windows = __stdcall → WINFUNCTYPE 更合适，但
# SADP SDK 内部用 CFUNCTYPE 也可以 (实测都可用)
# 使用 WINFUNCTYPE 严格匹配 __stdcall

PDEVICE_FIND_CALLBACK_V40 = WINFUNCTYPE(
    None,
    ctypes.POINTER(SADP_DEVICE_INFO_V40),
    ctypes.c_void_p,
)


# ============================================================
# High-level Device Info
# ============================================================

@dataclass
class SADPDevice:
    """SADP 发现的设备信息 (和 ptz_manager.py 兼容)."""
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
    http_port: int = 80
    sdk_port: int = 8000
    dhcp_enabled: bool = False
    source: str = "sadp"

    def display_name(self) -> str:
        return f"{self.model} ({self.mac}) - {'已激活' if self.activated else '未激活'}"


# ============================================================
# SADP Manager
# ============================================================

HIKVISION_MAC_OUI = {
    # 官方已知 Hikvision OUI 前缀
    "28:57:BE", "4C:BD:8F", "54:C4:15", "C0:56:E3", "E0:50:8B",
    # 补充更多已知 Hikvision OUI
    "78:DB:2F", "A0:1A:02", "D8:9E:F3", "B8:78:2E",
    "24:0F:9B",  # 实测发现设备的 OUI
    "34:17:EB", "64:5D:80", "88:54:BB", "94:45:46",
    "B0:90:74", "C4:64:13", "DC:CF:5C", "F0:BC:78",
    "FC:7B:16", "18:59:36",
}


def _is_hikvision_mac(mac: str) -> bool:
    normalized = mac.replace("-", ":").upper()
    return normalized[:7] in HIKVISION_MAC_OUI


class SADPManager:
    """官方 Sadp.dll 封装管理器.
    
    核心职责:
    1. 加载 Sadp.dll
    2. 绑定 C 函数
    3. 设备发现 (回调方式)
    4. 设备网络参数修改
    """

    # Hikvision OUI prefixes
    
    def __init__(self, dll_path: str | None = None) -> None:
        self._dll_path = dll_path or _find_sadp_dll()
        self._dll = None
        self._started = False
        self._lock = threading.Lock()
        # 回调数据
        self._devices: dict[str, SADPDevice] = {}
        self._callback: Any = None
        self._callback_lock = threading.Lock()
        # 绑定的网卡 IP (默认不限)
        self._bound_ip: str = "0.0.0.0"

    def load(self) -> bool:
        """加载 Sadp.dll 并初始化函数绑定."""
        if self._dll is not None:
            return True

        try:
            # 确保 OpenSSL DLL 在 PATH 中
            sdk_dir = str(Path(self._dll_path).parent)
            path_dirs = [sdk_dir]

            # PyInstaller 路径处理
            try:
                import sys
                if hasattr(sys, '_MEIPASS'):
                    # _MEIPASS/lib/ (如果 DLLs 在 _MEIPASS 中)
                    meipass = str(Path(sys._MEIPASS) / 'lib')
                    path_dirs.append(meipass)
                    meipass_root = str(Path(sys._MEIPASS))
                    if meipass_root != sdk_dir:
                        path_dirs.append(meipass_root)
                    # exe 同级 lib/ (binaries 打包到 dist/)
                    if sys.executable:
                        exe_lib = str(Path(sys.executable).parent / 'lib')
                        if exe_lib not in path_dirs:
                            path_dirs.append(exe_lib)
            except Exception:
                pass

            # SDK 参考路径作为最后回退
            try:
                from src.config_paths import SDK_LIBS_DIR
                sdk_libs = str(SDK_LIBS_DIR)
                if os.path.isdir(sdk_libs) and sdk_libs not in path_dirs:
                    path_dirs.append(sdk_libs)
            except Exception:
                pass

            os.environ["PATH"] = f"{';'.join(path_dirs)};{os.environ.get('PATH', '')}"

            # 自动创建 OpenSSL DLL 别名 (解决 Sadp.dll 内部 LoadLibrary 查找失败 → 错误 2045)
            _ensure_ssl_dll_aliases(sdk_dir)
            _ensure_libeay32_dll(sdk_dir)
            _report_openssl_dlls(sdk_dir)

            # PyInstaller 路径处理: 确保别名也在 _MEIPASS 和 exe 同级 lib/ 中创建
            try:
                import sys
                if hasattr(sys, '_MEIPASS'):
                    meipass_dir = str(Path(sys._MEIPASS))
                    _ensure_ssl_dll_aliases(meipass_dir)
                    _ensure_libeay32_dll(meipass_dir)
                if sys.executable:
                    exe_lib_dir = str(Path(sys.executable).parent / 'lib')
                    if os.path.isdir(exe_lib_dir):
                        _ensure_ssl_dll_aliases(exe_lib_dir)
                        _ensure_libeay32_dll(exe_lib_dir)
            except Exception:
                pass

            # Load dependent DLLs first — search all path_dirs
            def _find_dependent_dll(name: str) -> str | None:
                for d in path_dirs:
                    p = os.path.join(d, name)
                    if os.path.exists(p):
                        return p
                return None

            libcrypto_handle = None  # Capture handle for OpenSSL init

            for dep_name in ["libcrypto-1_1-x64.dll", "libssl-1_1-x64.dll"]:
                dep_path = _find_dependent_dll(dep_name)
                if dep_path:
                    try:
                        handle = ctypes.CDLL(dep_path)
                        if dep_name.startswith("libcrypto"):
                            libcrypto_handle = handle
                        print(f"[SADP] Loaded dependent DLL: {dep_path}")
                    except Exception as e:
                        print(f"[SADP] Warning: Could not preload {dep_name}: {e}")

            # Explicitly initialize OpenSSL 1.1.x cipher registry BEFORE loading Sadp.dll.
            # When libcrypto-1_1-x64.dll is loaded via ctypes.CDLL, OPENSSL_init_crypto
            # auto-init may not register all ciphers. Sadp.dll's internal AES encryption
            # (AES-128-ECB via EVP interface) requires explicit cipher registration.
            if libcrypto_handle:
                self._init_openssl(libcrypto_handle)

            self._dll = ctypes.WinDLL(self._dll_path)
            self._bind_functions()
            return True
        except Exception as e:
            print(f"[SADP] 加载 DLL 失败: {e}")
            return False

    def _init_openssl(self, libcrypto: ctypes.CDLL) -> bool:
        """显式初始化 OpenSSL 1.1.x 密码套件注册表.
        
        当 libcrypto-1_1-x64.dll 通过 ctypes.CDLL 加载时,
        OPENSSL_init_crypto 的自动初始化可能未注册全部密码套件.
        Sadp.dll x64 版本内部使用 AES-128-ECB (通过 EVP 接口),
        必须在调用 SADP_ModifyDeviceNetParam_V40 之前确保密文引擎就绪.
        """
        try:
            # int OPENSSL_init_crypto(uint64_t opts, const OPENSSL_INIT_SETTINGS *settings)
            init_func = libcrypto.OPENSSL_init_crypto
            init_func.argtypes = [ctypes.c_uint64, ctypes.c_void_p]
            init_func.restype = ctypes.c_int

            # OPENSSL_INIT_ADD_ALL_CIPHERS (0x04) | OPENSSL_INIT_ADD_ALL_DIGESTS (0x08)
            init_flags = 0x04 | 0x08
            ret = init_func(init_flags, None)
            print(f"[SADP] OpenSSL init: OPENSSL_init_crypto(0x{init_flags:02x}) -> {ret}")

            # 验证 EVP_aes_128_ecb 可访问 (Sadp.dll 内部 AES 加密依赖于此)
            evp_func = libcrypto.EVP_aes_128_ecb
            evp_func.argtypes = []
            evp_func.restype = ctypes.c_void_p

            cipher_ptr = evp_func()
            if not cipher_ptr:
                print("[SADP] WARNING: EVP_aes_128_ecb returned NULL — AES cipher not registered!")
                return False

            print(f"[SADP] OpenSSL OK: EVP_aes_128_ecb -> 0x{cipher_ptr:x}")
            return True

        except AttributeError as e:
            print(f"[SADP] WARNING: OpenSSL init symbol not found: {e} — 跳过初始化")
            return False
        except Exception as e:
            print(f"[SADP] WARNING: OpenSSL init 异常: {e} — 跳过初始化")
            return False

    def _bind_functions(self) -> None:
        """绑定 DLL 导出函数的 argtypes/restype."""
        dll = self._dll
        if dll is None:
            raise RuntimeError("DLL not loaded")

        # SADP_Start_V40 → 开始设备发现
        # BOOL CALLBACK SADP_Start_V40(PDEVICE_FIND_CALLBACK_V40, int, void*)
        dll.SADP_Start_V40.argtypes = [
            PDEVICE_FIND_CALLBACK_V40,
            ctypes.c_int,
            ctypes.c_void_p,
        ]
        dll.SADP_Start_V40.restype = ctypes.c_int  # BOOL

        # SADP_Start_V50 → 尝试新版本 (需要 SADP_START_PARAM struct)
        # 注意: 实测 V50 在某些 DLL 版本中不稳定，优先使用 V40
        try:
            dll.SADP_Start_V50.argtypes = [ctypes.c_void_p]
            dll.SADP_Start_V50.restype = ctypes.c_int
            self._use_v50 = False  # 默认仍然使用 V40
        except AttributeError:
            self._use_v50 = False
        self._use_v50 = False  # 强制使用 V40

        # SADP_SendInquiry → 发送发现探测报文
        # BOOL CALLBACK SADP_SendInquiry(void)
        dll.SADP_SendInquiry.argtypes = []
        dll.SADP_SendInquiry.restype = ctypes.c_int

        # SADP_Stop → 停止设备发现
        # BOOL CALLBACK SADP_Stop(void)
        dll.SADP_Stop.argtypes = []
        dll.SADP_Stop.restype = ctypes.c_int

        # SADP_GetLastError → 获取错误码
        # unsigned int CALLBACK SADP_GetLastError(void)
        dll.SADP_GetLastError.argtypes = []
        dll.SADP_GetLastError.restype = ctypes.c_uint

        # SADP_GetSadpVersion → 获取 SDK 版本
        # unsigned int CALLBACK SADP_GetSadpVersion(void)
        dll.SADP_GetSadpVersion.argtypes = []
        dll.SADP_GetSadpVersion.restype = ctypes.c_uint

        # SADP_Clearup → 清理 SDK 内部状态 (必须在 SADP_Start 前或 SADP_Stop 后调用)
        # void CALLBACK SADP_Clearup(void)
        dll.SADP_Clearup.argtypes = []
        dll.SADP_Clearup.restype = None

        # SADP_SetAutoRequestInterval
        # void CALLBACK SADP_SetAutoRequestInterval(unsigned int)
        dll.SADP_SetAutoRequestInterval.argtypes = [ctypes.c_uint]
        dll.SADP_SetAutoRequestInterval.restype = None

        # SADP_SetDeviceFilterRule
        # BOOL CALLBACK SADP_SetDeviceFilterRule(unsigned int, const void*, unsigned int)
        dll.SADP_SetDeviceFilterRule.argtypes = [
            ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint,
        ]
        dll.SADP_SetDeviceFilterRule.restype = ctypes.c_int

        # SADP_ModifyDeviceNetParam_V40
        # BOOL CALLBACK SADP_ModifyDeviceNetParam_V40(
        #     const char* sMAC, const char* sPassword,
        #     const SADP_DEV_NET_PARAM *lpNetParam,
        #     SADP_DEV_RET_NET_PARAM *lpRetNetParam,
        #     unsigned int dwOutBuffSize
        # )
        dll.SADP_ModifyDeviceNetParam_V40.argtypes = [
            ctypes.c_char_p, ctypes.c_char_p,
            ctypes.POINTER(SADP_DEV_NET_PARAM),
            ctypes.POINTER(SADP_DEV_RET_NET_PARAM),
            ctypes.c_uint,  # dwOutBuffSize
        ]
        dll.SADP_ModifyDeviceNetParam_V40.restype = ctypes.c_bool

        # SADP_SetLogToFile
        try:
            dll.SADP_SetLogToFile.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
            dll.SADP_SetLogToFile.restype = ctypes.c_int
        except AttributeError:
            pass

    def _parse_devices_info(self, c_info: SADP_DEVICE_INFO) -> SADPDevice:
        """将 C 结构体转换为 SADPDevice."""

        def decode(b: bytes) -> str:
            return b.decode("utf-8", errors="ignore").strip("\x00 ").strip()

        device = SADPDevice()
        device.mac = decode(c_info.szMAC).lower().replace(":", "-")
        device.ip = decode(c_info.szIPv4Address)
        device.subnet_mask = decode(c_info.szIPv4SubnetMask)
        device.gateway = decode(c_info.szIPv4Gateway)
        device.serial_number = decode(c_info.szSerialNO)
        device.firmware_version = decode(c_info.szDeviceSoftwareVersion)
        device.http_port = c_info.wHttpPort
        device.sdk_port = c_info.dwPort
        device.dhcp_enabled = bool(c_info.byDhcpEnabled)

        # 型号: 优先用 szDevDesc，其次 szSeries
        model = decode(c_info.szDevDesc)
        if not model:
            model = decode(c_info.szSeries)
        device.model = model

        # 设备名称
        device_name = decode(c_info.szBaseDesc)
        if not device_name:
            device_name = device.model
        device.device_name = device_name

        # 激活状态: 0=已激活, 1=未激活 (注意这个反直觉的设计)
        device.activated = (c_info.byActivated == 0)

        # 是否海康
        device.is_hikvision = _is_hikvision_mac(device.mac)

        return device

    def _callback_handler(self, lp_info: ctypes.POINTER(SADP_DEVICE_INFO_V40), p_user_data: int) -> None:
        """DLL 回调处理函数.
        
        在线程安全环境下处理设备信息.
        
        BUG-011 修复: MAC key 使用小写+横杠格式，与 _normalize_mac / _parse_devices_info 保持一致。
        """
        # Track event counts for diagnostic
        if not hasattr(self, '_callback_event_counts'):
            self._callback_event_counts = {SADP_ADD: 0, SADP_UPDATE: 0, SADP_RESTART: 0, SADP_DEC: 0}
        
        try:
            info_v40 = lp_info.contents
            base_info = info_v40.struSadpDeviceInfo

            # 设备事件处理:
            # SADP_ADD(1) = 设备上线
            # SADP_UPDATE(2) = 设备信息更新
            # SADP_RESTART(4) = 设备重新出现
            # 以上都是有效事件，需要收集
            # SADP_DEC(3) = 设备离线, SADP_UPDATEFAIL(5) = 更新失败, 忽略
            i_result = base_info.iResult
            if i_result in (SADP_DEC, SADP_UPDATEFAIL, 0):
                return

            mac_raw = base_info.szMAC.decode("utf-8", errors="ignore").strip("\x00 ")
            if not mac_raw:
                return

            # BUG-011: 统一 MAC key 为小写+横杠格式
            mac = self._normalize_mac(mac_raw)

            device = self._parse_devices_info(base_info)

            # Count and log event
            ip = device.ip if device.ip else ""
            event_type_map = {SADP_ADD: "ADD", SADP_UPDATE: "UPDATE", SADP_RESTART: "RESTART", SADP_DEC: "DEC"}
            event_name = event_type_map.get(i_result, f"UNKNOWN({i_result})")
            self._callback_event_counts[i_result] = self._callback_event_counts.get(i_result, 0) + 1
            print(f"[SADP] 回调事件: {event_name}, MAC={mac}, IP={ip}")

            with self._callback_lock:
                # 更新设备 (去重)
                self._devices[mac] = device

        except Exception as e:
            print(f"[SADP] 回调异常: {e}")

    def start_discovery(self) -> bool:
        """启动 SADP 发现服务.
        
        注册回调并开始监听设备广播.
        """
        if not self.load():
            return False

        with self._lock:
            if self._started:
                return True

            with _VirtualNicGuard(self._bound_ip):
                try:
                    # Log SDK version
                    try:
                        sdk_ver = self._dll.SADP_GetSadpVersion()
                        print(f"[SADP] SDK 版本: {sdk_ver}")
                    except Exception:
                        pass

                    # 创建回调函数实例
                    self._callback = WINFUNCTYPE(
                        None,
                        ctypes.POINTER(SADP_DEVICE_INFO_V40),
                        ctypes.c_void_p,
                    )(self._callback_handler)

                    # 清理 SDK 内部残留状态 (官方 Demo 在 Start 前调用 SADP_Clearup)
                    try:
                        self._dll.SADP_Clearup()
                        print("[SADP] SADP_Clearup 已调用")
                    except Exception:
                        pass

                    # 可选: 设置日志
                    try:
                        self._dll.SADP_SetLogToFile(0, None, 1)
                    except Exception:
                        pass

                    # 设置过滤器: 显示所有设备
                    try:
                        self._dll.SADP_SetDeviceFilterRule(0, None, 0)
                        print("[SADP] 设备过滤器已设置")
                    except Exception:
                        pass

                    # 启动发现 (V40 - 已验证稳定)
                    result = self._dll.SADP_Start_V40(self._callback, 0, None)

                    if result:
                        self._started = True
                        print(f"[SADP] SADP_Start_V40 返回: {result}")
                        # 与官方 C demo 一致: Start 之后设置 0 (禁用自动请求)
                        # 设备通过 SendInquiry() 手动刷新, 与 C demo OnBtnRefresh 行为一致
                        try:
                            self._dll.SADP_SetAutoRequestInterval(0)
                        except Exception:
                            pass
                        return True
                    else:
                        err = self._dll.SADP_GetLastError()
                        print(f"[SADP] 启动失败, 错误码={err}, {sadp_error_message(err)}")
                        return False

                except Exception as e:
                    print(f"[SADP] 启动发现服务异常: {e}")
                    return False

    def send_inquiry(self) -> bool:
        """发送 SADP 发现探测报文.
        
        应在 start_discovery() 之后调用.
        """
        if not self._started or self._dll is None:
            return False

        try:
            result = self._dll.SADP_SendInquiry()
            print("[SADP] SendInquiry 已发送")
            return bool(result)
        except Exception as e:
            print(f"[SADP] 发送探测报文异常: {e}")
            return False

    def stop_discovery(self) -> bool:
        """停止 SADP 发现服务."""
        with self._lock:
            if not self._started or self._dll is None:
                return False

            try:
                result = self._dll.SADP_Stop()
                self._started = False
                return bool(result)
            except Exception as e:
                print(f"[SADP] 停止发现服务异常: {e}")
                return False

    def discover_devices(self, timeout: float = 10.0, bind_ip: str = "0.0.0.0") -> list[dict]:
        """执行完整的设备发现流程.
        
        Args:
            timeout: 等待发现的时间 (秒)
            bind_ip: 指定用于 SADP 广播的物理网卡 IP.
                     - 默认 "0.0.0.0" 表示在所有网卡上广播
                     - 指定 IP (如 "192.168.5.201") 可限制广播到选定网卡
        
        Returns:
            设备列表 (dict 格式)
        """
        start_time = time.time()
        print(f"[SADP] 开始设备发现扫描, timeout={timeout}s, bind_ip={bind_ip}")

        self._devices.clear()
        self._callback_event_counts = {SADP_ADD: 0, SADP_UPDATE: 0, SADP_RESTART: 0, SADP_DEC: 0}
        self._bound_ip = bind_ip

        discovery_result = self.start_discovery()
        print(f"[SADP] start_discovery 结果: {discovery_result}")
        if not discovery_result:
            return []

        try:
            # 发送多次探测报文以增加发现概率
            for i in range(3):
                print(f"[SADP] 发送探测报文 #{i+1}/3")
                self.send_inquiry()
                time.sleep(1)

            # 等待设备响应
            time.sleep(timeout - 3)

            # 再发一次确保收到
            self.send_inquiry()
            time.sleep(2)

        finally:
            self.stop_discovery()

        # Callback summary
        counts = self._callback_event_counts
        count_summary = ", ".join(f"{v}={counts.get(k, 0)}" for k, v in {
            "ADD": SADP_ADD, "UPDATE": SADP_UPDATE, "RESTART": SADP_RESTART, "DEC": SADP_DEC
        }.items())
        print(f"[SADP] 回调事件统计: {count_summary}")

        # 过滤海康设备
        hikvision_devices = []
        all_devices = []

        for mac, device in self._devices.items():
            dev_dict = self._device_to_dict(device)
            all_devices.append(dev_dict)
            if device.is_hikvision:
                hikvision_devices.append(dev_dict)

        hik_count = len(hikvision_devices)
        print(f"[SADP] 回调收到设备数: {len(self._devices)}, 海康设备: {hik_count}")

        elapsed = time.time() - start_time
        result_count = len(hikvision_devices) if hikvision_devices else len(all_devices)
        print(f"[SADP] 发现结束, 耗时 {elapsed:.1f}s, 返回 {result_count} 台设备")

        if hikvision_devices:
            return hikvision_devices
        return all_devices

    @staticmethod
    def _normalize_mac(mac: str) -> str:
        """规范化 MAC 地址为小写+横杠格式.

        关键发现: SDK 回调返回的 MAC 格式为 **小写+横杠** (如 "24-0f-9b-76-41-93"),
        不是冒号格式. 官方 C demo (DlgHikSadp.cpp) 中 SADP_ModifyDeviceNetParam_V40 调用:
            int bret = SADP_ModifyDeviceNetParam_V40(m_smac, m_spsw, ...);
        其中 m_smac 直接来自 SDK 回调返回的值，不做任何转换。

        此方法用于 self._devices 字典 key 匹配和 DLL 调用.

        支持的输入格式:
        - "24-0f-9b-76-41-93" (SDK 回调格式, 直接返回)
        - "24:0f:9b:76:41:93" (冒号格式, 转换为横杠)
        - "24-0F-9B-76-41-93" (大写+横杠, 转为小写)
        - "240f9b764193" (紧凑格式, 添加横杠并小写)

        BUG-016 修复: 增强 MAC 校验，拒绝假 MAC 地址（如 IP 地址填入 MAC 字段）。

        Returns:
            小写+横杠格式: "24-0f-9b-76-41-93"，无效则返回空字符串
        """
        import re
        # 移除所有分隔符, 小写
        clean = mac.replace(":", "").replace("-", "").replace(".", "").lower()
        # 必须是恰好12位十六进制，拒绝非标准格式 (如 IP 地址)
        if len(clean) != 12 or not re.match(r'^[0-9a-f]{12}$', clean):
            return ""
        return "-".join(clean[i:i+2] for i in range(0, 12, 2))

    @staticmethod
    def _mac_for_dll(mac: str) -> str:
        """将 MAC 地址转为 DLL 调用格式 (小写+横杠)。

        关键发现: SDK 回调返回的 MAC 格式实测为 **24-0f-9b-76-41-93** (小写+横杠),
        不是冒号格式. 官方 C demo (DlgHikSadp.cpp) 中 SADP_ModifyDeviceNetParam_V40 调用:
            int bret = SADP_ModifyDeviceNetParam_V40(m_smac, m_spsw, ...);
        其中 m_smac 直接来自 SDK 回调返回的值，不做任何转换。

        Args:
            mac: 任意格式的 MAC 地址


        Returns:
            小写+横杠格式: "24-0f-9b-76-41-93"
        """
        clean = mac.replace(":", "").replace("-", "").lower()
        if len(clean) == 12:
            return "-".join(clean[i:i+2] for i in range(0, 12, 2))
        return mac.lower()

    def modify_device_network(
        self,
        mac: str,
        password: str,
        new_ip: str,
        subnet_mask: str,
        gateway: str,
        http_port: int = 80,
    ) -> dict:
        """通过 SADP DLL 修改设备网络参数.

        实现规范 (严格对齐官方 C demo DlgHikSadp.cpp OnButtonSafe + sadp_ref.md):
1. SADP_Start_V40 注册回调，SendInquiry 触发设备回调
2. 设备回调出现后，从 SDK 原始数据获取 MAC（小写+横杠格式，如 `24-0f-9b-76-41-93`）
        3. 构造 SADP_DEV_NET_PARAM（memset 清零 + 按序填值）
        4. 调用 SADP_ModifyDeviceNetParam_V40
        5. SADP 保持运行（与 SADP.exe 行为一致）

        Args:
            mac: 设备 MAC 地址 (大小写/冒号/横杠均自动规范化)
            password: 设备密码
            new_ip: 新 IP 地址（字符串，如 "192.168.5.107"）
            subnet_mask: 子网掩码（字符串，如 "255.255.255.0"）
            gateway: 网关（字符串，如 "192.168.5.1"）
            http_port: HTTP 端口

        Returns:
            结果字典 - 包含 success/message/method/error_code
        """
        if not self.load():
            return {"success": False, "message": "DLL 加载失败", "error_code": "DLL_LOAD_FAIL"}

        # Step 1: 启动 SADP 发现服务（若未运行）
        if not self._started:
            self._devices.clear()
            self._dll.SADP_Clearup()  # C demo 官方做法: Start 前 Clearup 清理残留状态
            if not self.start_discovery():
                err = self._dll.SADP_GetLastError() if self._dll else 0
                return {
                    "success": False,
                    "message": f"SADP 启动失败: {sadp_error_message(err)}",
                    "error_code": err,
                }
            # Start 后立即发送 inquiry 触发设备广播（与 C demo OnBtnRefresh 一致）
            self.send_inquiry()
            print("[SADP] 已启动发现服务并发送 inquiry")

        # Step 2: 等待目标设备出现在 SDK 回调列表中
        # 规范化 MAC 用于匹配
        mac_normalized = self._normalize_mac(mac)

        found_device = False
        max_wait = 15
        print(f"[SADP] 等待设备 {mac_normalized} 出现在回调列表中 (最长 {max_wait}s)...")

        for i in range(max_wait):
            time.sleep(1)
            # 每 2 秒发送一次 inquiry 保持设备活跃（与 C demo 行为一致）
            if i > 0 and i % 2 == 0:
                self.send_inquiry()

            # 匹配设备（SDK 回调原始 MAC key 或 normalize 后匹配）
            if mac_normalized in self._devices:
                found_device = True
                break

            # 格式兼容匹配：遍历所有已发现设备的 MAC
            for dev_mac in list(self._devices.keys()):
                if self._normalize_mac(dev_mac) == mac_normalized:
                    mac_normalized = dev_mac
                    found_device = True
                    break
            if found_device:
                break

        if not found_device:
            print(f"[SADP] 错误: 设备 {mac} ({mac_normalized}) 未在回调列表中")
            print(f"[SADP] 已发现设备 ({len(self._devices)} 个): {list(self._devices.keys())}")
            # 即使未找到，也尝试用传入的 MAC 执行修改（与 C demo 行为对齐）
            # C demo 中 m_smac 直接来自 UI，不要求回调列表中有该设备
            mac_for_dll = self._mac_for_dll(mac)
        else:
            # 使用 SDK 回调原始 MAC（与 C demo m_smac 来源一致）
            mac_for_dll = self._mac_for_dll(mac_normalized)

        print(f"[SADP] DLL MAC 格式: '{mac_for_dll}'")

        # Step 3: 构造 SADP_DEV_NET_PARAM（严格对齐 C demo OnButtonSafe）
        # C demo: memset(&struNetParam, 0, sizeof(SADP_DEV_NET_PARAM))
        net_param = SADP_DEV_NET_PARAM()
        ctypes.memset(ctypes.byref(net_param), 0, ctypes.sizeof(net_param))

        # C demo: strcpy() 逐字段填充
        net_param.szIPv4Address = new_ip.encode("utf-8")
        net_param.szIPv4SubNetMask = subnet_mask.encode("utf-8")
        net_param.szIPv4Gateway = gateway.encode("utf-8")
        # IPv6 字段: memset 后全 0 字节（C demo m_strIPv6Adress 来自 UI，通常为空字符串）
        # byIPv6MaskLen = 0（C demo: IPv6 为空时 byMaskLen = 0）
        net_param.byIPv6MaskLen = 0
        net_param.byDhcpEnable = 0  # 禁用 DHCP（与 C demo iDhcpCheck=0 一致）

        # 从已发现设备获取端口信息（与 C demo 从 list item 获取一致）
        target_device = self._devices.get(mac_normalized) or None
        if target_device is None:
            for dev_mac, dev in self._devices.items():
                if self._normalize_mac(dev_mac) == mac_normalized:
                    target_device = dev
                    break

        if target_device:
            net_param.wPort = target_device.sdk_port if target_device.sdk_port > 0 else 8000
            net_param.wHttpPort = target_device.http_port if target_device.http_port > 0 else http_port
            print(f"[SADP] 设备端口: sdk_port={net_param.wPort}, http_port={net_param.wHttpPort}")
        else:
            net_param.wPort = 8000
            net_param.wHttpPort = http_port
            print(f"[SADP] 未获取到设备端口，使用默认: sdk_port={net_param.wPort}, http_port={net_param.wHttpPort}")

        net_param.dwSDKOverTLSPort = 0  # C demo: sSDKOverTLSPort 来自 UI，默认 0

        # Step 4: 构造返回参数
        ret_param = SADP_DEV_RET_NET_PARAM()
        ctypes.memset(ctypes.byref(ret_param), 0, ctypes.sizeof(ret_param))

        print(f"[SADP] 结构体大小: SADP_DEV_NET_PARAM={ctypes.sizeof(net_param)}, SADP_DEV_RET_NET_PARAM={ctypes.sizeof(ret_param)}")

        # Step 5: 关键! 调用 ModifyDeviceNetParam_V40 之前发送 inquiry 保持设备活跃
        # C demo 中 OnBtnRefresh 定期刷新设备列表，确保设备在 SDK 内部表中
        self.send_inquiry()
        time.sleep(0.5)  # 给 DLL 短暂时间处理 inquiry 响应

        # Step 6: 调用 SADP_ModifyDeviceNetParam_V40
        # C demo: int bret = SADP_ModifyDeviceNetParam_V40(m_smac, m_spsw, &struNetParam, &struDevRetNetParam, sizeof(struDevRetNetParam))
        print(f"[SADP] 调用 SADP_ModifyDeviceNetParam_V40: MAC={mac_for_dll}, IP={new_ip}, MASK={subnet_mask}, GW={gateway}")
        try:
            # 关键修复: 显式 null 终止字符串，匹配 C demo 中 strcpy() 的 null 终结行为
            # C demo 中 m_spsw 来自 CString (MultiByte 模式 = ANSI = cp936)
            # SDK DLL 内部 AES 加密使用 strlen() 确定密码长度，必须 null 终止
            password_bytes = password.encode("cp936") + b"\x00"
            mac_bytes = mac_for_dll.encode("ascii") + b"\x00"

            print(f"[SADP] 密码字节长度: {len(password_bytes)} bytes (含 null)")
            print(f"[SADP] MAC 字节 (hex): {mac_bytes.hex()}")

            result = self._dll.SADP_ModifyDeviceNetParam_V40(
                mac_bytes,
                password_bytes,
                ctypes.byref(net_param),
                ctypes.byref(ret_param),
                ctypes.sizeof(ret_param),
            )

            if result:
                print(f"[SADP] 修改成功: {new_ip}")
                return {
                    "success": True,
                    "message": f"网络配置已修改: {new_ip}",
                    "method": "SADP_DLL",
                    "error_code": 0,
                }
            else:
                err = self._dll.SADP_GetLastError()
                err_msg = sadp_error_message(err)
                print(f"[SADP] 修改失败: 错误码={err}, {err_msg}")
                print(f"[SADP] 返回参数: byRetryModifyTime={ret_param.byRetryModifyTime}, bySurplusLockTime={ret_param.bySurplusLockTime}")

                # 详细错误信息（参考 C demo 错误处理）
                if err == 2024:  # SADP_PASSWORD_ERROR
                    print(f"[SADP] 密码错误，剩余修改尝试次数: {ret_param.byRetryModifyTime}")
                elif err == 2018:  # SADP_LOCKED
                    print(f"[SADP] 设备已锁定，剩余锁定时间: {ret_param.bySurplusLockTime} 分钟")

                return {
                    "success": False,
                    "message": f"网络配置修改失败: {err_msg} (code={err})",
                    "error_code": err,
                    "error_detail": err_msg,
                }
        except Exception as e:
            print(f"[SADP] 修改网络配置异常: {e}")
            return {"success": False, "message": f"修改网络配置异常: {e}", "error_code": "EXCEPTION"}

        # 注意: 不再调用 stop_discovery()，保持 SADP 运行状态与官方 SADP.exe 行为一致

    def _device_to_dict(self, d: SADPDevice) -> dict:
        """将 SADPDevice 转换为字典."""
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
            "http_port": d.http_port,
            "sdk_port": d.sdk_port,
            "dhcp_enabled": d.dhcp_enabled,
            "source": "sadp",
        }

    def cleanup(self) -> None:
        """清理资源."""
        self.stop_discovery()
        self._devices.clear()
        self._callback = None
