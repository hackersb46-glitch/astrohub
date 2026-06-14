"""
M2 Device Manager v1.0 - SADP 设备发现模块

实现海康威视 SADP (Search Active Device Protocol) 协议的设备发现功能。
包括: UDP广播扫描、设备信息解析、MAC型号联合识别、激活状态检测、IP可达性判断。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import socket
import struct
import time
from datetime import datetime
from typing import Any

try:
    import requests
except ImportError:
    raise ImportError("需要安装 requests 库: pip install requests")

from device.constants import (
    ONLINE_CHECK_ENDPOINT,
    ONLINE_CHECK_TIMEOUT,
)
from device.core.logger import LOG
from device.core.mac_utils import normalize_mac
from device.isapi.client import ISAPIClient


# SADP 协议常量
SADP_MULTICAST_IP = "239.255.255.250"
SADP_PORT = 37020
SADP_PACKET_SIZE = 4096
SADP_TIMEOUT = 5  # 秒


class SADPDiscovery:
    """SADP 设备发现器。

    通过 SADP 协议广播扫描局域网内的海康设备，解析设备信息。

    Args:
        bind_ip: 绑定的本地IP地址
        timeout: 等待响应超时时间(秒)
    """

    def __init__(self, bind_ip: str = "0.0.0.0", timeout: int = SADP_TIMEOUT) -> None:
        self._bind_ip = bind_ip
        self._timeout = timeout
        LOG.info(f"SADPDiscovery 初始化完成: bind={bind_ip}, timeout={timeout}s")

    def _build_discovery_packet(self) -> bytes:
        """构建 SADP 设备发现请求包。

        Returns:
            SADP 协议请求包字节数据
        """
        # SADP 协议发现包 (简化版本)
        packet_header = b"\x00\x01\x00\x00\x00\x00\x00\x00"
        # UUID - 随机生成的唯一标识符
        import uuid
        uuid_bytes = uuid.uuid4().bytes
        packet_body = struct.pack(
            "!8s16s",
            packet_header,
            uuid_bytes
        )
        # 添加搜索标志
        search_flag = b"\x00\x00\x00\x01"
        return packet_body + search_flag

    def _parse_sadp_response(self, data: bytes) -> dict | None:
        """解析 SADP 设备响应数据。

        Args:
            data: 接收到的 UDP 数据包

        Returns:
            设备信息字典，包含 MAC/IP/型号/SN 等字段
        """
        try:
            # SADP 响应包解析 (根据海康协议标准格式)
            device_info: dict[str, Any] = {}

            # 提取 UUID (前 24 字节)
            if len(data) < 24:
                return None

            # 解析 MAC 地址 (在响应包的特定偏移)
            mac_start = 40
            if len(data) > mac_start + 6:
                mac_bytes = data[mac_start:mac_start + 6]
                mac = ":".join(f"{b:02X}" for b in mac_bytes)
                device_info["mac"] = normalize_mac(mac)

            # 解析 IP 地址
            ip_start = 50
            if len(data) > ip_start + 4:
                ip_bytes = data[ip_start:ip_start + 4]
                device_info["ip"] = socket.inet_ntoa(ip_bytes)

            # 解析子网掩码
            mask_start = 54
            if len(data) > mask_start + 4:
                mask_bytes = data[mask_start:mask_start + 4]
                device_info["subnet_mask"] = socket.inet_ntoa(mask_bytes)

            # 解析网关
            gw_start = 58
            if len(data) > gw_start + 4:
                gw_bytes = data[gw_start:gw_start + 4]
                device_info["gateway"] = socket.inet_ntoa(gw_bytes)

            # 解析端口
            port_start = 62
            if len(data) > port_start + 2:
                device_info["port"] = struct.unpack("!H", data[port_start:port_start + 2])[0]
            else:
                device_info["port"] = 80

            # 解析设备型号 (字符串字段，从特定偏移开始)
            model_start = 64
            model_end = data.find(b"\x00", model_start) if model_start < len(data) else -1
            if model_start < len(data):
                if model_end > model_start:
                    device_info["model"] = data[model_start:model_end].decode("utf-8", errors="ignore").strip()
                else:
                    device_info["model"] = data[model_start:model_start + 32].decode("utf-8", errors="ignore").strip()

            # 解析序列号
            sn_start = model_end + 1 if model_end > model_start else model_start + 32
            sn_end = data.find(b"\x00", sn_start) if sn_start < len(data) else -1
            if sn_start < len(data):
                if sn_end > sn_start:
                    device_info["serial_number"] = data[sn_start:sn_end].decode("utf-8", errors="ignore").strip()
                else:
                    device_info["serial_number"] = data[sn_start:sn_start + 32].decode("utf-8", errors="ignore").strip()

            # 如果无法解析关键字段，返回 None
            if not device_info.get("mac") and not device_info.get("ip"):
                return None

            # 补充默认值
            device_info.setdefault("model", "Unknown")
            device_info.setdefault("serial_number", "Unknown")
            device_info.setdefault("port", 80)

            return device_info

        except Exception as e:
            LOG.error(f"SADP 响应解析失败: {e}")
            return None

    def scan_network(self, timeout: int | None = None) -> list[dict]:
        """通过 SADP 协议广播扫描局域网内的所有海康设备。

        Args:
            timeout: 等待响应超时时间(秒)，默认使用实例配置的超时时间

        Returns:
            发现的设备列表，每个设备包含 MAC/IP/型号/SN 等信息
        """
        timeout = timeout or self._timeout
        LOG.info(f"SADP 设备发现扫描开始... (timeout={timeout}s)")

        discovered_devices: list[dict] = []
        seen_macs: set[str] = set()

        try:
            # 创建 UDP socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.settimeout(1)  # 1秒接收超时，主循环控制总超时

            # 发送 discovery packet
            discovery_packet = self._build_discovery_packet()

            # 发送到 SADP 组播地址
            try:
                sock.sendto(
                    discovery_packet,
                    (SADP_MULTICAST_IP, SADP_PORT)
                )
                LOG.info(f"SADP 发现请求已发送: {SADP_MULTICAST_IP}:{SADP_PORT}")
            except Exception as e:
                LOG.warning(f"SADP 组播发送失败: {e} - 尝试本地广播")
                # 组播失败时尝试本地广播
                sock.sendto(
                    discovery_packet,
                    ("<broadcast>", SADP_PORT)
                )

            # 接收响应
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    data, addr = sock.recvfrom(SADP_PACKET_SIZE)
                    device_info = self._parse_sadp_response(data)
                    if device_info:
                        mac = device_info.get("mac", "")
                        if mac and mac not in seen_macs:
                            seen_macs.add(mac)
                            device_info["discovery_time"] = datetime.now().isoformat()
                            device_info["source_ip"] = addr[0]
                            LOG.done(f"发现设备: MAC={mac}, IP={device_info.get('ip')}, 型号={device_info.get('model')}")
                            discovered_devices.append(device_info)
                except socket.timeout:
                    continue
                except Exception as e:
                    LOG.warning(f"SADP 接收异常: {e}")
                    continue

        except Exception as e:
            LOG.error(f"SADP 扫描失败: {e}")
        finally:
            try:
                sock.close()
            except Exception:
                pass

        LOG.info(f"SADP 设备发现扫描结束: 发现 {len(discovered_devices)} 个设备")
        return discovered_devices

    # ------------------------------------------------------------------ #
    #  MAC + 型号联合识别
    # ------------------------------------------------------------------ #

    def identify_device(
        self,
        mac: str,
        model: str,
        ip: str,
        port: int = 80,
    ) -> dict:
        """通过 MAC 和型号联合识别设备，验证设备真实信息。

        Args:
            mac: 设备 MAC 地址
            model: 设备型号
            ip: 设备 IP 地址
            port: 设备端口

        Returns:
            设备识别结果，包含 success 标志和详细信息
        """
        norm_mac = normalize_mac(mac)
        LOG.info(f"设备识别验证: MAC={norm_mac}, Model={model}, IP={ip}")

        # 通过 ISAPI 接口获取设备详细信息
        result = self._verify_device_via_isapi(ip, port)
        if not result.get("success"):
            return {
                "success": False,
                "mac": norm_mac,
                "model": model,
                "ip": ip,
                "error": result.get("error", "ISAPI 验证失败"),
            }

        isapi_info = result.get("device_info", {})

        # 验证 MAC 匹配
        isapi_mac = normalize_mac(isapi_info.get("mac", ""))
        mac_match = isapi_mac == norm_mac

        # 验证型号匹配
        isapi_model = isapi_info.get("model", "")
        model_match = model.lower() in isapi_model.lower() if isapi_model else False

        # 综合判断
        if mac_match and model_match:
            LOG.done(f"设备识别成功: MAC 和型号均匹配")
            return {
                "success": True,
                "mac": norm_mac,
                "model": model,
                "ip": ip,
                "isapi_mac": isapi_mac,
                "isapi_model": isapi_model,
                "serial_number": isapi_info.get("serial_number", ""),
                "firmware_version": isapi_info.get("firmware_version", ""),
                "identification_method": "MAC+Model",
            }
        elif mac_match:
            LOG.warning(f"设备识别: MAC 匹配但型号不匹配 (期望={model}, 实际={isapi_model})")
            return {
                "success": True,
                "mac": norm_mac,
                "model": model,
                "isapi_model": isapi_model,
                "ip": ip,
                "serial_number": isapi_info.get("serial_number", ""),
                "firmware_version": isapi_info.get("firmware_version", ""),
                "identification_method": "MAC_only",
                "model_mismatch": True,
            }
        else:
            LOG.warning(f"设备识别失败: MAC 不匹配 (期望={norm_mac}, 实际={isapi_mac})")
            return {
                "success": False,
                "mac": norm_mac,
                "isapi_mac": isapi_mac,
                "ip": ip,
                "error": f"MAC 不匹配: 期望 {norm_mac}, 实际 {isapi_mac}",
            }

    # ------------------------------------------------------------------ #
    #  激活状态检测
    # ------------------------------------------------------------------ #

    def check_activation_status(self, ip: str, port: int = 80) -> dict:
        """检查设备是否已激活。

        设备未激活时会返回特定状态码或重定向到激活页面。

        Args:
            ip: 设备 IP 地址
            port: 设备端口

        Returns:
            激活状态检测结果
        """
        LOG.info(f"检查设备激活状态: {ip}:{port}")

        try:
            # 尝试访问设备信息接口，判断是否需要激活
            response = requests.get(
                f"http://{ip}:{port}{ONLINE_CHECK_ENDPOINT}",
                timeout=ONLINE_CHECK_TIMEOUT,
            )

            # 检查响应状态
            if response.status_code == 200:
                # 设备已激活且可正常访问
                return {
                    "success": True,
                    "ip": ip,
                    "port": port,
                    "is_activated": True,
                    "status_code": response.status_code,
                    "message": "设备已激活",
                }
            elif response.status_code == 401:
                # 设备已激活但需要认证
                return {
                    "success": True,
                    "ip": ip,
                    "port": port,
                    "is_activated": True,
                    "status_code": response.status_code,
                    "message": "设备已激活 (需认证)",
                }
            elif response.status_code == 403:
                # 可能设备未激活或权限不足
                return {
                    "success": True,
                    "ip": ip,
                    "port": port,
                    "is_activated": False,
                    "status_code": response.status_code,
                    "message": "设备可能未激活",
                }
            else:
                return {
                    "success": True,
                    "ip": ip,
                    "port": port,
                    "is_activated": False,
                    "status_code": response.status_code,
                    "message": f"设备状态异常: HTTP {response.status_code}",
                }

        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "ip": ip,
                "port": port,
                "is_activated": None,
                "error": "设备连接失败",
            }
        except requests.exceptions.Timeout:
            return {
                "success": False,
                "ip": ip,
                "port": port,
                "is_activated": None,
                "error": "设备连接超时",
            }
        except Exception as e:
            return {
                "success": False,
                "ip": ip,
                "port": port,
                "is_activated": None,
                "error": f"激活状态检测异常: {e}",
            }

    # ------------------------------------------------------------------ #
    #  IP 可达性判断
    # ------------------------------------------------------------------ #

    def check_ip_reachable(self, ip: str, port: int = 80, timeout: int = ONLINE_CHECK_TIMEOUT) -> dict:
        """判断设备 IP 是否可达。

        尝试 TCP 连接设备的 ISAPI 接口，验证网络连通性。

        Args:
            ip: 设备 IP 地址
            port: 设备端口
            timeout: 连接超时时间(秒)

        Returns:
            IP 可达性检测结果
        """
        LOG.info(f"检查 IP 可达性: {ip}:{port}, timeout={timeout}s")

        # 方法 1: 尝试 TCP 连接
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result_code = sock.connect_ex((ip, port))
            sock.close()

            if result_code == 0:
                return {
                    "success": True,
                    "ip": ip,
                    "port": port,
                    "reachable": True,
                    "method": "TCP_CONNECT",
                    "response_time_ms": 0,
                    "message": "IP 可达 (TCP 连接成功)",
                }
            else:
                # 方法 2: 尝试 HTTP 请求
                return self._check_http_reachable(ip, port, timeout)

        except Exception as e:
            LOG.warning(f"TCP 连接检测失败: {e}")
            return self._check_http_reachable(ip, port, timeout)

    def _check_http_reachable(self, ip: str, port: int, timeout: int) -> dict:
        """通过 HTTP 请求检测 IP 可达性。

        Args:
            ip: 设备 IP 地址
            port: 设备端口
            timeout: 连接超时时间(秒)

        Returns:
            HTTP 可达性检测结果
        """
        import time
        start_time = time.time()

        try:
            response = requests.get(
                f"http://{ip}:{port}{ONLINE_CHECK_ENDPOINT}",
                timeout=timeout,
            )
            response_time_ms = (time.time() - start_time) * 1000

            if response.status_code in (200, 401):
                return {
                    "success": True,
                    "ip": ip,
                    "port": port,
                    "reachable": True,
                    "method": "HTTP_CHECK",
                    "status_code": response.status_code,
                    "response_time_ms": round(response_time_ms, 2),
                    "message": "IP 可达 (HTTP 响应成功)",
                }
            else:
                return {
                    "success": True,
                    "ip": ip,
                    "port": port,
                    "reachable": False,
                    "method": "HTTP_CHECK",
                    "status_code": response.status_code,
                    "message": f"IP 不可达 (HTTP {response.status_code})",
                }

        except requests.exceptions.ConnectionError:
            response_time_ms = (time.time() - start_time) * 1000
            return {
                "success": True,
                "ip": ip,
                "port": port,
                "reachable": False,
                "method": "HTTP_CHECK",
                "response_time_ms": round(response_time_ms, 2),
                "message": "IP 不可达 (连接拒绝)",
            }
        except requests.exceptions.Timeout:
            response_time_ms = (time.time() - start_time) * 1000
            return {
                "success": True,
                "ip": ip,
                "port": port,
                "reachable": False,
                "method": "HTTP_CHECK",
                "response_time_ms": round(response_time_ms, 2),
                "message": "IP 不可达 (超时)",
            }
        except Exception as e:
            return {
                "success": False,
                "ip": ip,
                "port": port,
                "reachable": None,
                "error": f"可达性检测异常: {e}",
            }

    # ------------------------------------------------------------------ #
    #  完整设备发现流程
    # ------------------------------------------------------------------ #

    def discover_and_verify(self, ip: str, port: int = 80) -> dict:
        """完整的设备发现流程: 可达性 → 激活状态 → 设备信息获取。

        Args:
            ip: 设备 IP 地址
            port: 设备端口

        Returns:
            完整的设备发现和验证结果
        """
        LOG.info(f"开始完整设备发现流程: {ip}:{port}")

        # Step 1: 检查 IP 可达性
        reachability = self.check_ip_reachable(ip, port)
        if not reachability.get("reachable", False):
            LOG.failed(f"设备发现失败: IP 不可达 - {ip}")
            return {
                "success": False,
                "ip": ip,
                "step": "reachability",
                "reachability": reachability,
                "error": f"设备 IP 不可达: {ip}",
            }

        # Step 2: 检查激活状态
        activation = self.check_activation_status(ip, port)
        if not activation.get("is_activated", False):
            LOG.failed(f"设备发现失败: 设备未激活 - {ip}")
            return {
                "success": False,
                "ip": ip,
                "step": "activation",
                "reachability": reachability,
                "activation": activation,
                "error": f"设备未激活: {ip}",
            }

        # Step 3: 获取设备详细信息
        device_info_result = self._verify_device_via_isapi(ip, port)
        if not device_info_result.get("success"):
            LOG.failed(f"设备发现失败: 无法获取设备信息 - {ip}")
            return {
                "success": False,
                "ip": ip,
                "step": "device_info",
                "reachability": reachability,
                "activation": activation,
                "error": f"无法获取设备信息: {device_info_result.get('error')}",
            }

        device_info = device_info_result.get("device_info", {})
        LOG.done(f"设备发现成功: MAC={device_info.get('mac')}, 型号={device_info.get('model')}")

        return {
            "success": True,
            "ip": ip,
            "port": port,
            "reachability": reachability,
            "activation": activation,
            "device_info": {
                "mac": device_info.get("mac", ""),
                "model": device_info.get("model", ""),
                "serial_number": device_info.get("serial_number", ""),
                "firmware_version": device_info.get("firmware_version", ""),
            },
        }

    # ------------------------------------------------------------------ #
    #  辅助方法
    # ------------------------------------------------------------------ #

    def _verify_device_via_isapi(self, ip: str, port: int = 80) -> dict:
        """通过 ISAPI 接口验证设备信息。

        Args:
            ip: 设备 IP 地址
            port: 设备端口

        Returns:
            设备信息验证结果
        """
        try:
            # 尝试无需认证的 ISAPI 请求
            response = requests.get(
                f"http://{ip}:{port}{ONLINE_CHECK_ENDPOINT}",
                timeout=ONLINE_CHECK_TIMEOUT,
            )

            device_info: dict[str, Any] = {
                "ip": ip,
                "port": port,
            }

            if response.status_code == 200:
                # 解析 XML 响应获取设备信息
                import xml.etree.ElementTree as ET
                try:
                    root = ET.fromstring(response.text)
                    for child in root.iter():
                        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                        if tag == "model":
                            device_info["model"] = child.text or ""
                        elif tag == "serialNumber":
                            device_info["serial_number"] = child.text or ""
                        elif tag == "firmwareVersion":
                            device_info["firmware_version"] = child.text or ""
                        elif tag == "macAddress":
                            device_info["mac"] = normalize_mac(child.text or "")
                except ET.ParseError:
                    pass

                return {
                    "success": True,
                    "device_info": device_info,
                }
            elif response.status_code == 401:
                # 设备需要认证，无法获取详细信息
                device_info["requires_auth"] = True
                return {
                    "success": True,
                    "device_info": device_info,
                    "message": "设备需要认证",
                }
            else:
                return {
                    "success": False,
                    "error": f"ISAPI 验证失败: HTTP {response.status_code}",
                }

        except Exception as e:
            return {
                "success": False,
                "error": f"ISAPI 验证异常: {e}",
            }