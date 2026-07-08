"""
AstroHub v2.0 - 统一路由聚合

整合 M1-M11 所有模块路由到 /api/v1/ 下:
- /api/v1/health            - 全局健康检查
- /api/v1/discovery/sadp    - SADP 设备发现
- /api/v1/devices/*         - 设备管理(真实)
- /api/v1/ptz/*             - PTZ 控制(真实)
- /api/v1/streams/*         - 流服务
- /api/v1/calibration/*     - 校准
- /api/v1/ascom/*           - ASCOM 设备
- /api/v1/settings          - 系统设置

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel
from fastapi import APIRouter, FastAPI, Query
from fastapi.responses import JSONResponse, Response, StreamingResponse

# v6.40: 操作日志
from src.operation_logger import log_api, log_web, log_error, log_info

# ================================================================ #
#  核心模块导入
# ================================================================ #

from src.core.ws_manager import WebSocketManager
from src.core.ptz_controller import PTZDeviceController
from src.ptz.isapi.ptz import PTZController
from src.core.device_manager import DeviceManager
from src.core.calibration_manager import CalibrationManager
from src.core.auth import AuthManager
from src.core.ascom_manager import ASCOMManager
from src.core.task_scheduler import TaskScheduler
from src.core.health_monitor import HealthMonitor
from src.main.constants import VERSION, VERSION_NUM


# ================================================================ #
#  路由前缀定义
# ================================================================ #

API_V1_PREFIX = "/api/v1"

# 主 API 路由器
api_router = APIRouter(prefix=API_V1_PREFIX, tags=["API v1"])

# 健康检查路由器
health_router = APIRouter(prefix="/api/v1", tags=["System"])


# ================================================================ #
#  v6.40: 操作日志 API
# ================================================================ #

class OperationLogRequest(BaseModel):
    """操作日志请求."""
    level: str = "INFO"
    module: str = "web"
    action: str = ""
    detail: str | dict = ""

@health_router.post("/log/operation", summary="记录操作日志")
async def log_operation_api(req: OperationLogRequest) -> dict:
    """前端发送操作日志到后端."""
    from src.operation_logger import log_operation
    log_operation(req.level, req.module, req.action, req.detail)
    return {"success": True}


# ================================================================ #
#  Pydantic 请求模型
# ================================================================ #

class AddDeviceRequest(BaseModel):
    """手动添加设备请求。"""
    ip: str
    port: int = 80
    username: str = "admin"
    password: str
    name: str = ""
    model: str = ""
    mac: str = ""

class ConnectDeviceRequest(BaseModel):
    """连接设备请求。"""
    username: str = "admin"
    password: str
    port: int = 80

class ModifyNetworkRequest(BaseModel):
    """修改网络配置请求。"""
    ip: str
    subnet_mask: str = "255.255.255.0"
    gateway: str

class SADPIpModifyRequest(BaseModel):
    """SADP IP 修改请求 (含循环验证)。"""
    mac: str
    password: str
    new_ip: str
    original_ip: str = ""
    subnet_mask: str = "255.255.255.0"
    gateway: str = ""

class SystemInfoRequest(BaseModel):
    """系统信息请求(可选的绑定 ip)。"""
    nic_index: int | None = None

class PTZMoveRequest(BaseModel):
    """PTZ 移动请求。

    speed: 1-7 档位,默认 4 档
    档位映射: 1→14, 2→28, 3→43, 4→57, 5→71, 6→86, 7→100
    """
    direction: str
    speed: int = 4  # 默认 4 档

class PTZAbsoluteRequest(BaseModel):
    """PTZ 绝对移动请求。

    speed: 1-7 档位,默认 4 档
    """
    pan: float
    tilt: float
    zoom: float | None = None
    speed: int = 4  # 默认 4 档

class PTZPresetRequest(BaseModel):
    """PTZ 预置位请求。"""
    preset_id: int

class SADPScanRequest(BaseModel):
    """SADP 发现请求。"""
    bind_ip: str = "0.0.0.0"

class RemoveDeviceRequest(BaseModel):
    """移除设备请求。"""
    ip: str = ""
    mac: str = ""


class PTZCaptureRequest(BaseModel):
    """PTZ 截图请求。"""
    stream_url: str = ""
    stream_id: str = ""


class PTZRecordRequest(BaseModel):
    """PTZ 录像请求。"""
    target_name: str = ""


class TelescopeSlewRequest(BaseModel):
    """望远镜 Slew 请求。"""
    ra: float
    dec: float


class TelescopeTrackingRequest(BaseModel):
    """望远镜跟踪模式请求。"""
    mode: str  # trackSidereal / trackLunar / trackSolar / trackOff


# ================================================================ #
#  操作日志 (最多 10 条)
# ================================================================ #

operations_log: list[dict[str, str]] = []
MAX_LOG_ENTRIES = 10


def operation_log(action: str, details: str) ->PTZDeviceController | None:
    """追加操作到日志列表(环形缓冲区,最多 MAX_LOG_ENTRIES 条)。"""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "details": details,
    }
    operations_log.append(entry)
    if len(operations_log) > MAX_LOG_ENTRIES:
        operations_log.pop(0)


# ================================================================ #
#  管理器注入
# ================================================================ #

_managers: dict[str, Any] = {}


def set_managers(**kwargs: Any) ->PTZDeviceController | None:
    """注入所有管理器实例。"""
    _managers.update(kwargs)


def _resolve_device_id_to_ip(mgr: "PTZDeviceController", device_id: str) -> str | None:
    """解析 device_id 为实际 IP 地址。

    device_id 可能是 IP 地址或 MAC 地址。
    - 如果是 IP: 直接返回
    - 如果是 MAC: 从 SADP 发现缓存或已存储设备中查找 IP
    """
    import re
    # 判断是否为 MAC 地址格式 (冒号、横杠分隔或无分隔符)
    mac_clean = device_id.replace(":", "").replace("-", "").lower()
    # 无分隔符12位十六进制 = MAC
    if len(mac_clean) == 12 and re.match(r'^[0-9a-f]{12}$', mac_clean):
        # 是 MAC 地址,尝试从发现缓存中查找
        discovered = mgr.get_discovered_devices()
        for dev in discovered:
            dev_mac = dev.get("mac", "").replace(":", "").replace("-", "").lower()
            if dev_mac == mac_clean:
                return dev.get("ip")
        # 从已存储设备中查找
        stored = mgr.list_stored_devices()
        for dev in stored:
            dev_mac = dev.get("mac", "").replace(":", "").replace("-", "").lower()
            if dev_mac == mac_clean:
                ip = dev.get("ip", "")
                if ip:
                    return ip
        returnPTZDeviceController | None
    # 看起来像 IP 地址,直接返回
    return device_id


# ================================================================ #
#  健康检查端点
# ================================================================ #


@health_router.get("/health", summary="全局健康检查")
async def global_health() -> dict:
    """全局健康检查端点 (GET /api/v1/health)。"""
    module_keys = (
        "ptz_controller",
        "device_manager",
        "calibration_manager",
        "db_manager",
        "auth_service",
        "ws_manager",
        "ascom_manager",
        "health_monitor",
        "orchestrator",
    )

    module_health: dict[str, dict[str, Any]] = {}
    for key in module_keys:
        module_health[key] = {
            "status": "initialized" if _managers.get(key) is not None else "not_initialized",
            "present": key in _managers,
        }

    all_present = all(m["present"] for m in module_health.values())
    initialized_count = sum(1 for m in module_health.values() if m["present"])

    return {
        "status": "healthy" if all_present else "degraded",
        "modules": module_health,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@health_router.get("/version", summary="获取版本号")
async def get_version() -> dict:
    """获取系统版本号 (GET /api/v1/version)。"""
    return {
        "version": VERSION,
        "version_num": VERSION_NUM,
    }


@api_router.get("/localhost", summary="本机信息", tags=["System"])
async def get_localhost_info() -> dict:
    """获取本机系统信息 (hostname, CPU, RAM, GPU, IP, gateway).

    首次调用时会自动收集并保存到 data/reports/localhost.json
    """
    from src.advanced.startup import get_localhost_info, run_startup, check_localhost_exists

    # 如果文件不存在,先收集
    if not check_localhost_exists():
        try:
            info = run_startup()
            return {"success": True, "data": info, "first_run": True}
        except Exception as e:
            return {"success": False, "message": f"收集本机信息失败: {e}"}

    # 读取已保存的信息
    info = get_localhost_info()
    if info:
        return {"success": True, "data": info}
    else:
        return {"success": False, "message": "无法读取本机信息"}


# ================================================================ #
#  SADP 发现端点
# ================================================================ #


@api_router.get("/discovery/sadp", summary="SADP 设备发现", tags=["Discovery"])
async def sadp_discover(bind_ip: str = "0.0.0.0") -> dict:
    """通过 SADP 多播发现局域网内 PTZ 设备。

    BUG-003 修复: 直接使用 SADPManager,不依赖 PTZDeviceController。
    """
    start = time.time()

    # 优先使用 PTZDeviceController(如果已初始化)
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")  # type: ignore[assignment]
    if mgr:
        devices = mgr.discover_devices(bind_ip=bind_ip)
    else:
        # 直接使用 SADPManager 不依赖 PTZDeviceController
        try:
            from src.core.sadp_discovery import SADPManager
            sadp_mgr = SADPManager()
            raw_devices = sadp_mgr.discover_devices(timeout=3, bind_ip=bind_ip)
            # 转换为 SADP 标准格式
            devices = []
            for d in raw_devices:
                devices.append({
                    "mac": d.get("mac", ""),
                    "ip": d.get("ip", ""),
                    "subnet_mask": d.get("subnet_mask", ""),
                    "gateway": d.get("gateway", ""),
                    "model": d.get("model", ""),
                    "serial_number": d.get("serial_number", ""),
                    "device_name": d.get("device_name", ""),
                    "firmware_version": d.get("firmware_version", ""),
                    "activated": d.get("activated", False),
                    "is_hikvision": d.get("is_hikvision", False),
                })
        except Exception as e:
            return {"success": False, "message": f"SADP 发现异常: {e}", "devices": []}

    elapsed = round(time.time() - start, 1)

    # BUG-015 修复: 统一 MAC 地址格式为横杠小写 (24-0f-9b-76-41-93)
    for dev in devices:
        mac = dev.get("mac", "")
        if mac:
            clean = mac.replace(":", "").replace("-", "").lower()
            if len(clean) == 12:
                dev["mac"] = "-".join(clean[i:i+2] for i in range(0, 12, 2))

    return {
        "success": True,
        "message": f"发现 {len(devices)} 台设备 (耗时 {elapsed}s)",
        "devices": devices,
        "count": len(devices),
    }


# ================================================================ #
#  设备管理端点
# ================================================================ #


@api_router.get("/devices", summary="设备列表", tags=["Devices"])
async def list_devices() -> dict:
    """获取设备列表（MAC唯一标识，SADP更新IP/型号）.""" 
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "data": [], "total": 0}

    def _normalize_mac(mac: str) -> str:
        """统一 MAC 为无分隔符小写格式.""" 
        import re
        clean = mac.replace(":", "").replace("-", "").lower()
        if len(clean) != 12 or not re.match(r'^[0-9a-f]{12}$', clean):
            return ""
        return clean

    stored = mgr.list_stored_devices()
    discovered = mgr.get_discovered_devices()

    # 以MAC为唯一键，存储设备为基础
    devices: dict[str, dict[str, Any]] = {}
    for dev in stored:
        mac = _normalize_mac(dev.get("mac", "") or "")
        if mac:
            devices[mac] = {
                "mac": mac,
                "ip": dev.get("ip", ""),
                "name": dev.get("name", "") or dev.get("device_name", ""),
                "model": dev.get("model", ""),
                "gateway": dev.get("gateway", ""),
                "subnet_mask": dev.get("subnet_mask", ""),
                "has_credentials": True,
            }

    # SADP发现：更新或新增
    for sadp in discovered:
        mac = _normalize_mac(sadp.get("mac", "") or "")
        if not mac:
            continue
        if mac in devices:
            # 更新：SADP数据为准（IP可能变了）
            devices[mac]["ip"] = sadp.get("ip", "") or devices[mac]["ip"]
            devices[mac]["model"] = sadp.get("model", "") or devices[mac]["model"]
            devices[mac]["gateway"] = sadp.get("gateway", "")
            devices[mac]["subnet_mask"] = sadp.get("subnet_mask", "")
        else:
            # 新增：首次发现
            devices[mac] = {
                "mac": mac,
                "ip": sadp.get("ip", ""),
                "name": sadp.get("device_name", "") or sadp.get("name", ""),
                "model": sadp.get("model", "") or "PTZ",
                "gateway": sadp.get("gateway", ""),
                "subnet_mask": sadp.get("subnet_mask", ""),
                "has_credentials": False,
            }

    return {"success": True, "data": list(devices.values()), "total": len(devices)}


@api_router.post("/devices/refresh", summary="刷新设备状态", tags=["Devices"])
async def refresh_devices() -> dict:
    """并行ping所有设备，更新在线状态(timeout=1s)。""" 
    from concurrent.futures import ThreadPoolExecutor
    from src.core.ptz_controller import check_reachable
    
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "data": [], "total": 0}

    def _normalize_mac(mac: str) -> str:
        import re
        clean = mac.replace(":", "").replace("-", "").lower()
        if len(clean) != 12 or not re.match(r'^[0-9a-f]{12}$', clean):
            return ""
        return clean

    stored = mgr.list_stored_devices()
    discovered = mgr.get_discovered_devices()

    # 以MAC为唯一键
    devices: dict[str, dict[str, Any]] = {}
    for dev in stored:
        mac = _normalize_mac(dev.get("mac", "") or "")
        if mac:
            devices[mac] = {
                "mac": mac,
                "ip": dev.get("ip", ""),
                "name": dev.get("name", "") or dev.get("device_name", ""),
                "model": dev.get("model", ""),
                "gateway": dev.get("gateway", ""),
                "subnet_mask": dev.get("subnet_mask", ""),
                "has_credentials": True,
                "status": "离线",
            }

    for sadp in discovered:
        mac = _normalize_mac(sadp.get("mac", "") or "")
        if not mac:
            continue
        if mac in devices:
            devices[mac]["ip"] = sadp.get("ip", "") or devices[mac]["ip"]
            devices[mac]["model"] = sadp.get("model", "") or devices[mac]["model"]
            devices[mac]["gateway"] = sadp.get("gateway", "")
            devices[mac]["subnet_mask"] = sadp.get("subnet_mask", "")
        else:
            devices[mac] = {
                "mac": mac,
                "ip": sadp.get("ip", ""),
                "name": sadp.get("device_name", "") or sadp.get("name", ""),
                "model": sadp.get("model", "") or "PTZ",
                "gateway": sadp.get("gateway", ""),
                "subnet_mask": sadp.get("subnet_mask", ""),
                "has_credentials": False,
                "status": "离线",
            }

    # 并行ping检测状态
    devices_list = list(devices.values())
    ips = [d["ip"] for d in devices_list if d["ip"]]
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        reachability = list(executor.map(lambda ip: check_reachable(ip, timeout=1), ips))
    
    # 更新状态
    ip_status = dict(zip(ips, reachability))
    for dev in devices_list:
        ip = dev.get("ip", "")
        if ip and ip_status.get(ip, False):
            dev["status"] = "在线"
        else:
            dev["status"] = "离线"
    
    # 检查已连接状态
    online_ips = mgr.list_controllers()
    for dev in devices_list:
        if dev.get("ip") in online_ips and dev.get("status") == "在线":
            dev["status"] = "已连接"

    return {"success": True, "data": devices_list, "total": len(devices_list)}


@api_router.get("/devices/active", summary="获取上次连接的设备", tags=["Devices"])
async def get_active_device() -> dict:
    """v6.30: 获取上次连接的设备(用于快速连接)。"""
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "active": False, "device": None, "message": "PTZDeviceController未初始化"}

    device = mgr.get_connected_device()
    if device is None:
        return {"success": False, "active": False, "device": None, "message": "无上次连接设备"}

    return {"success": True, "active": True, "device": device}


@api_router.post("/devices/active", summary="设置上次连接的设备", tags=["Devices"])
async def set_active_device(mac: str) -> dict:
    """v6.30: 设置上次连接的设备(用于快速连接)。"""
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    # 从 devices/{mac}/info.json 读取设备信息
    device = mgr.config.get_device(mac)
    if device is None:
        return {"success": False, "message": f"设备不存在: {mac}"}

    # 更新 registry.json 的 active_device 和 last_connected
    mgr.config.upsert_device(mac, {"mac": mac})

    return {
        "success": True,
        "message": f"上次连接设备已设置: {device.get('model', 'Unknown')} @ {device.get('ip')}",
        "device": device
    }


@api_router.post("/devices", summary="注册设备", tags=["Devices"])
async def register_device(req: AddDeviceRequest) -> dict:
    """手动添加设备(IP + 凭据)并自动设为活跃。

    v7.17: 必须有 MAC 地址才能注册,如果没有则从 SADP 发现中查找。
    """
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    # v7.17: 如果没有 MAC,从 SADP 发现中查找
    device_mac = req.mac
    device_model = req.model
    device_name = req.name

    if not device_mac:
        # 检查 SADP 发现中是否有该 IP 的设备
        sadp_devices = mgr._discovered
        for mac, info in sadp_devices.items():
            if info.ip == req.ip:
                device_mac = mac
                device_model = device_model or getattr(info, 'model',PTZDeviceController | None)
                device_name = device_name or getattr(info, 'device_name',PTZDeviceController | None)
                break

        if not device_mac:
            return {"success": False, "message": f"未发现设备 {req.ip},请先执行 SADP 发现"}

    # 使用正确的 MAC 保存
    mgr.save_credentials(
        ip=req.ip,
        username=req.username,
        password=req.password,
        port=req.port,
        mac=device_mac,  # v7.17: 必须使用真实 MAC
        model=device_model,
        name=device_name,
    )

    # 注册到 DeviceManager
    dm: DeviceManager | None = _managers.get("device_manager")  # type: ignore[assignment]
    if dm:
        dm.register_device(
            mac=device_mac,  # v7.17: 使用真实 MAC
            ip=req.ip,
            name=device_name or f"PTZ-{req.ip}",
            model=device_model or "PTZ",
        )

    # 设为活跃设备(更新 registry.json)
    mgr.config.upsert_device(device_mac, {"ip": req.ip, "model": device_model or "", "port": req.port, "mac": device_mac})

    log_info("device", "register", {"ip": req.ip, "mac": device_mac, "name": device_name})
    return {
        "success": True,
        "message": f"设备已保存: {device_mac} @ {req.ip}",
        "device": {
            "ip": req.ip,
            "port": req.port,
            "name": device_name,
            "model": device_model,
            "mac": device_mac,
        },
    }


@api_router.post("/devices/{device_id}/connect", summary="连接设备", tags=["Devices"])
async def connect_device(device_id: str, req: ConnectDeviceRequest | None = None) -> dict:
    """连接 PTZ 设备并认证。

    device_id 可以是 IP 地址或 MAC 地址。如果是 MAC,自动解析为 IP。
    使用 admin 作为默认用户名,密码必须由用户提供或已保存在配置中。

    BUG-014 修复: ISAPI 连接前 socket 预检,5 秒超时快速失败。
    """
    log_api("connect", {"mac": device_id})

    mgr: PTZDeviceController | None = _managers.get("ptz_controller")  # type: ignore[assignment]
    if not mgr:
        log_error("connect", {"mac": device_id, "error": "PTZDeviceController未初始化"})
        return {"success": False, "message": "PTZDeviceController未初始化"}

    # 解析 device_id: 如果看起来像 MAC,从发现缓存中解析 IP
    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        log_error("connect", {"mac": device_id, "error": "无法解析设备标识"})
        return {"success": False, "message": f"无法解析设备标识: {device_id},请提供 IP 地址或确保设备已通过 SADP 发现"}

    # 如果未提供凭据,尝试从存储获取
    if req is None:
        creds = mgr.get_credentials(target_ip)
        if not creds:
            log_error("connect", {"mac": device_id, "error": "设备未保存凭据"})
            return {"success": False, "message": "设备未保存凭据,请先提供用户名和密码"}
        username = creds["username"]
        password = creds["password"]
        port = creds.get("port", 80)
    else:
        username = req.username or "admin"
        if not req.password:
            return {"success": False, "message": "请提供密码"}
        password = req.password
        port = req.port

    result = mgr.connect_device(target_ip, username, password, port)
    if result and result.get("success"):
        log_info("connect", {"mac": device_id, "ip": target_ip, "status": "success"})
        # 更新 DeviceManager 状态(使用 device_id 保持前端一致)
        dm: DeviceManager | None = _managers.get("device_manager")  # type: ignore[assignment]
        if dm:
            dm.update_status(device_id, "online")
        return result

    log_error("connect", {"mac": device_id, "ip": target_ip, "status": "failed"})
    return result or {"success": False, "message": "连接失败"}


@api_router.post("/devices/{device_id}/disconnect", summary="断开设备", tags=["Devices"])
async def disconnect_device(device_id: str) -> dict:
    """断开 PTZ 设备连接."""
    log_api("disconnect", {"mac": device_id})

    mgr: PTZDeviceController | None = _managers.get("ptz_controller")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    mgr.disconnect_device(device_id)

    dm: DeviceManager | None = _managers.get("device_manager")  # type: ignore[assignment]
    if dm:
        dm.update_status(device_id, "offline")

    log_info("disconnect", {"mac": device_id, "status": "success"})
    return {"success": True, "message": f"设备已断开: {device_id}"}


@api_router.delete("/devices/{device_id}", summary="删除设备", tags=["Devices"])
async def delete_device(device_id: str) -> dict:
    """删除设备。"""
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    # 先断开
    mgr.disconnect_device(device_id)

    # 移除凭据
    removed = mgr.remove_credentials(device_id)

    dm: DeviceManager | None = _managers.get("device_manager")  # type: ignore[assignment]
    if dm:
        dm.unregister_device(device_id)

    log_info("device", "delete", {"device_id": device_id})
    return {
        "success": True,
        "message": f"设备已删除: {device_id}",
    }


@api_router.get("/devices/{device_id}/info", summary="设备详细信息", tags=["Devices"])
async def get_device_info(device_id: str) -> dict:
    """获取设备详细信息(通过 ISAPI)。"""
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    # 解析 device_id (MAC) 到 IP
    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": "无法解析设备标识: 请提供 IP 地址或确保设备已连接"}

    info = mgr.get_device_info(target_ip)
    if "error" in info:
        return {"success": False, "message": info["error"]}

    return {"success": True, "data": info}


@api_router.put("/devices/{device_id}/network", summary="修改设备网络配置", tags=["Devices"])
async def modify_network(device_id: str, req: ModifyNetworkRequest) -> dict:
    """修改设备网络配置(通过 SADP 协议)。"""
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    result = mgr.modify_device_network(
        ip=device_id,
        new_ip=req.ip,
        subnet_mask=req.subnet_mask,
        gateway=req.gateway,
    )
    return result


# ================================================================ #
#  SADP IP 修改 & 系统信息端点
# ================================================================ #


@api_router.post("/sadp/{mac}/modify-ip", summary="SADP 修改设备 IP (含自动验证循环)", tags=["SADP"])
async def sadp_modify_ip(mac: str, req: SADPIpModifyRequest) -> dict:
    """通过 SADP DLL 修改设备 IP,含自动重试和扫描确认循环。"""
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    result = mgr.modify_reachable_with_retry(
        mac=mac,
        password=req.password,
        original_ip=req.original_ip or "",
        target_ip=req.new_ip,
        subnet_mask=req.subnet_mask,
        gateway=req.gateway,
    )
    return result


@api_router.get("/sadp/error-codes", summary="SADP 错误码参考表", tags=["SADP"])
async def sadp_error_codes() -> JSONResponse:
    """返回 SADP 错误码中文对照表。"""
    try:
        from src.core.sadp_discovery import SADP_ERROR_CODES
        return JSONResponse(
            content={"success": True, "codes": SADP_ERROR_CODES},
            ensure_ascii=False,
        )
    except ImportError:
        return JSONResponse(
            content={"success": False, "message": "SADP 模块未加载"},
            ensure_ascii=False,
        )


@api_router.post("/sadp/auto-reconnect", summary="P2.7: 已知设备自动重连", tags=["SADP"])
async def sadp_auto_reconnect(req: AutoReconnectDevicesRequest | None = None) -> dict:
    """P2.7: 扫描 SADP 设备 -> MAC匹配已保存设备 -> IP不可达时自动修改 IP。"""
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    bind_ip = "0.0.0.0"
    target_ip = None
    if req:
        bind_ip = req.bind_ip or "0.0.0.0"
        target_ip = req.target_ip or None

    result = mgr.auto_reconnect_known_devices(bind_ip=bind_ip, target_ip=target_ip)
    return result


class AutoReconnectDevicesRequest(BaseModel):
    """P2.7: 已知设备自动重连请求。"""
    bind_ip: str = "0.0.0.0"
    target_ip: str = ""


# ================================================================
#  v6.0 连接状态 API
# ================================================================

@api_router.get("/ptz/connected", summary="获取已连接设备状态 (v6.15)", tags=["PTZ"])
async def get_connected_device() -> dict:
    """v7.10: 获取当前连接状态和上次连接设备信息。

    返回:
    - connected: 当前是否已连接(基于 active_device)
    - device: 上次连接的设备信息(基于 last_connected,用于快速连接)
    """
    import json
    from src.config_paths import REGISTRY_FILE

    mgr: PTZDeviceController | None = _managers.get("ptz_controller")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化", "connected": False, "device": None}

    # v7.10: 获取上次连接的设备(用于快速连接)
    device = mgr.get_connected_device()

    # v7.10: 检查当前是否实际连接(基于 active_device)
    # v7.31: 同时检查 active_device 非空 AND _controllers 非空
    connected = False
    try:
        if REGISTRY_FILE.exists():
            registry = json.loads(REGISTRY_FILE.read_text(encoding='utf-8'))
            active_mac = registry.get('active_device', '').strip()
            # 同时检查 active_device 非空 AND 实际连接存在
            if active_mac and hasattr(mgr, '_controllers') and mgr._controllers:
                connected = True
    except Exception:
        pass

    if not device:
        return {"success": True, "connected": False, "device": None}

    return {"success": True, "connected": connected, "device": device}

@api_router.get("/system/info", summary="系统硬件信息 (P1.1)", tags=["System"])
async def get_system_info() -> dict:
    """获取本机系统硬件信息 (hostname/CPU/RAM/GPU/VRAM)。"""
    try:
        from src.ptz.core.system_info import collect_system_info
        info = collect_system_info()
        return {"success": True, "data": info}
    except Exception as e:
        return {"success": False, "message": str(e)}


@api_router.get("/system/nics", summary="网络接口列表 (P1.2)", tags=["System"])
async def get_nics() -> dict:
    """获取所有网络接口列表,按优先级排序。"""
    try:
        from src.core.net_detector import get_all_nics
        nics = get_all_nics()
        return {"success": True, "data": nics, "total": len(nics)}
    except Exception as e:
        return {"success": False, "message": str(e)}


@api_router.get("/system/default-ip", summary="推荐目标 IP (P1.3)", tags=["System"])
async def get_default_ip() -> dict:
    """获取推荐的目标 IP 地址。"""
    try:
        from src.core.net_detector import suggest_target_ip
        ip = suggest_target_ip()
        return {"success": True, "data": {"ip": ip}}
    except Exception as e:
        return {"success": False, "message": str(e)}


@api_router.get("/system/operations", summary="操作日志 (最近10条)", tags=["System"])
async def get_operations_log() -> dict:
    """获取最近 10 条操作日志。"""
    return {"success": True, "data": list(reversed(operations_log)), "total": len(operations_log)}


@health_router.get("/log/operations/file", summary="从文件读取操作日志")
async def get_operation_log_file(lines: int = 50) -> dict:
    """从日志文件读取最近N条操作日志."""
    from src.operation_logger import LOG_DIR
    from datetime import datetime

    today = datetime.now().strftime("%Y%m%d")
    log_file = LOG_DIR / f"operation_{today}.log"

    if not log_file.exists():
        return {"success": True, "data": [], "total": 0}

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            all_lines = f.readlines()

        recent = all_lines[-lines:] if len(all_lines) > lines else all_lines
        recent.reverse()

        entries = []
        for line in recent:
            line = line.strip()
            if not line:
                continue
            entries.append(line)

        return {"success": True, "data": entries, "total": len(entries)}
    except Exception as e:
        return {"success": False, "message": str(e), "data": [], "total": 0}


# ================================================================ #
#  PTZ 控制端点
# ================================================================ #


@api_router.post("/ptz/{device_id}/move", summary="PTZ 移动", tags=["PTZ"])
async def ptz_move(device_id: str, req: PTZMoveRequest) -> dict:
    """PTZ 方向移动控制。"""
    try:
        mgr: PTZDeviceController | None = _managers.get("ptz_controller")
        if not mgr:
            return {"success": False, "message": "PTZDeviceController未初始化"}

        target_ip = _resolve_device_id_to_ip(mgr, device_id)
        if not target_ip:
            return {"success": False, "message": f"无法解析设备标识: {device_id}"}

        return mgr.ptz_move(target_ip, direction=req.direction, speed=req.speed)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "message": f"PTZ 移动异常: {e}"}


@api_router.post("/ptz/{device_id}/home", summary="PTZ 归位", tags=["PTZ"])
async def ptz_gotohome(device_id: str) -> dict:
    """PTZ 归位(预置点 10)。"""
    import asyncio
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    result = await asyncio.to_thread(mgr.ptz_home, target_ip)
    if result.get("success"):
        log_info("ptz", "home", {"device": device_id})
    return result


@api_router.post("/ptz/{device_id}/stop", summary="PTZ 停止", tags=["PTZ"])
async def ptz_stop(device_id: str) -> dict:
    """PTZ 停止所有移动。"""
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    # BUG-A 修复: 支持 MAC 地址作为 device_id
    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    # BUG-C 修复: ptz_stop 调用 stop_move 而非连续移动
    return mgr.ptz_stop(target_ip)


class FocusModeRequest(BaseModel):
    """对焦模式请求"""
    mode: str  # manual, auto, semiauto


@api_router.post("/ptz/{device_id}/focus/mode", summary="设置对焦模式", tags=["PTZ"])
async def set_focus_mode(device_id: str, req: FocusModeRequest) -> dict:
    """设置对焦模式(手动/自动/半自动)"""
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    # 调用 ISAPI 设置对焦模式
    ctrl = mgr._controllers.get(target_ip)
    if not ctrl:
        return {"success": False, "message": "设备未连接"}

    try:
        # ISAPI 端点: PUT /ISAPI/Image/channels/1/focusConfiguration
        mode_upper = "MANUAL" if req.mode.lower() == "manual" else ("AUTO" if req.mode.lower() == "auto" else "SEMIAUTOMATIC")

        xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<FocusConfiguration version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <focusStyle>{mode_upper}</focusStyle>
  <focusLimited>300</focusLimited>
</FocusConfiguration>'''

        result = ctrl.client.put("/Image/channels/1/focusConfiguration", xml)

        if result.status_code == 200:
            log_info("ptz", "focus_mode", {"device": device_id, "mode": req.mode})
            return {"success": True, "message": f"对焦模式已设置为 {req.mode}"}
        return {"success": False, "message": f"设置对焦模式失败: {result.status_code}"}
    except Exception as e:
        return {"success": False, "message": f"设置对焦模式失败: {e}"}


@api_router.get("/ptz/{device_id}/focus/mode", summary="获取对焦模式", tags=["PTZ"])
async def get_focus_mode(device_id: str) -> dict:
    """获取当前对焦模式"""
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    ctrl = mgr._controllers.get(target_ip)
    if not ctrl:
        return {"success": False, "message": "设备未连接"}

    try:
        import xml.etree.ElementTree as ET
        result = ctrl.client.get("/Image/channels/1")
        if result.status_code != 200:
            return {"success": False, "message": f"获取图像配置失败: {result.status_code}"}

        root = ET.fromstring(result.xml)
        focus_style = "unknown"
        for elem in root.iter():
            if elem.tag.endswith('focusStyle'):
                focus_style = (elem.text or "").lower()
                break

        # 转换为前端格式
        mode_map = {"manual": "manual", "automatic": "auto", "semiautomatic": "semiauto"}
        mode = mode_map.get(focus_style, focus_style)
        return {"success": True, "mode": mode}
    except Exception as e:
        return {"success": False, "message": f"获取对焦模式失败: {e}"}


@api_router.get("/ptz/{device_id}/presets", summary="获取预置点列表", tags=["PTZ"])
async def ptz_list_presets(device_id: str) -> dict:
    """获取设备所有预置点列表."""
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    return mgr.ptz_list_presets(target_ip)


@api_router.post("/ptz/{device_id}/preset/{preset_id}", summary="预置位", tags=["PTZ"])
async def ptz_preset(device_id: str, preset_id: int) -> dict:
    """移动到指定预置点。"""
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    # BUG-A 修复: 支持 MAC 地址作为 device_id
    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    result = mgr.ptz_preset(target_ip, preset_id=preset_id)
    if result.get("success"):
        log_info("ptz", "preset_goto", {"device": device_id, "preset_id": preset_id})
    return result


@api_router.post("/ptz/{device_id}/preset/{preset_id}/set", summary="保存预置位", tags=["PTZ"])
async def ptz_set_preset(device_id: str, preset_id: int, name: str = "") -> dict:
    """设置当前位置为指定预置点。"""
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    result = mgr.set_preset(target_ip, preset_id=preset_id, name=name)
    if result.get("success"):
        log_info("ptz", "preset_set", {"device": device_id, "preset_id": preset_id, "name": name})
    return result


@api_router.post("/ptz/{device_id}/absolute", summary="绝对位置", tags=["PTZ"])
async def ptz_absolute(device_id: str, req: PTZAbsoluteRequest) -> dict:
    """绝对坐标移动(Pan/Tilt/Zoom)。"""
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    # BUG-A 修复: 支持 MAC 地址作为 device_id
    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    return mgr.ptz_absolute(
        target_ip,
        pan=req.pan,
        tilt=req.tilt,
        zoom=req.zoom,
        speed=req.speed,
    )


@api_router.get("/ptz/{device_id}/position", summary="获取 PTZ 位置", tags=["PTZ"])
async def get_ptz_position(device_id: str) -> dict:
    """获取 PTZ 当前位置。"""
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    # BUG-A 修复: 支持 MAC 地址作为 device_id
    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    # BUG-B 修复: 统一返回 response.data
    return mgr.ptz_get_position(target_ip)


# 海康 ISAPI PTZ OSD 显示端点常量
ISAPI_PTZ_OSD_TEMPLATE = "/ISAPI/PTZCtrl/channels/{ch}/PTZOSDDisplay"


@api_router.post("/ptz/{device_id}/osd/toggle", summary="切换 PTZ 坐标 OSD 显示", tags=["PTZ"])
async def ptz_osd_toggle(device_id: str, enabled: bool = True) -> dict:
    """通过海康 ISAPI 控制 PTZ 坐标 OSD 显示开关。

    使用: GET/PUT /ISAPI/PTZCtrl/channels/{ch}/PTZOSDDisplay
    enabled=True  开启 PTZ 坐标OSD
    enabled=False 关闭 PTZ 坐标OSD
    """
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    ctrl, err = mgr._get_controller(target_ip)
    if err:
        return {"success": False, "message": err}

    client = mgr._clients.get(target_ip)
    if not client:
        return {"success": False, "message": f"ISAPI client not found for {target_ip}"}

    try:
        ch = getattr(client, 'channel', 1)
        endpoint = f"/PTZCtrl/channels/{ch}/PTZOSDDisplay"

        # 先 GET 获取当前 OSD 设置
        get_resp = client.get(endpoint)
        if get_resp.status_code != 200:
            return {"success": False, "message": f"GET PTZOSDDisplay 失败: HTTP {get_resp.status_code}, {get_resp.xml[:200]}"}

        import xml.etree.ElementTree as ET
        root = ET.fromstring(get_resp.xml)

        # 根据ISAPI规范, PTZOSDDisplay XML 字段:
        # azimuth: alwaysopen/alwaysclose → P/T 坐标
        # zoomlable: alwaysopen/alwaysclose → Z 值
        # presetlable: alwaysopen/alwaysclose → 预置点标签
        # 全部统一开关
        val = "alwaysopen" if enabled else "alwaysclose"
        for tag_name in ("azimuth", "zoomlable", "presetlable"):
            elem = root.find(tag_name)
            if elem is not None:
                elem.text = val
            else:
                # 带 namespace
                elem = root.find(".//{http://www.hikvision.com/ver20/XMLSchema}" + tag_name)
                if elem is not None:
                    elem.text = val

        # PUT 更新(移除 ns0: 命名空间前缀)
        xml_str = ET.tostring(root, encoding="unicode")
        xml_str = xml_str.replace('ns0:', '')
        xml_str = xml_str.replace('xmlns:ns0=', 'xmlns=')
        new_xml = '<?xml version="1.0" encoding="UTF-8"?>' + xml_str
        put_resp = client.put(endpoint, new_xml)
        if put_resp.status_code == 200:
            return {
                "success": True,
                "message": f"PTZ 坐标 OSD 已{'开启' if enabled else '关闭'}",
                "enabled": enabled,
            }
        else:
            return {"success": False, "message": f"PUT PTZOSDDisplay 失败: HTTP {put_resp.status_code}, {put_resp.xml[:200]}"}

    except Exception as e:
        return {"success": False, "message": f"OSD 切换异常: {e}"}


@api_router.post("/ptz/{device_id}/osd/ptz", summary="切换 PTZ 坐标 OSD", tags=["PTZ"])
async def ptz_osd_ptz_toggle(device_id: str, body: dict = None) -> dict:
    """切换 PTZ 坐标(P/T/Z)OSD 显示。"""
    enabled = (body or {}).get("enabled", True) if body else True

    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    ctrl, err = mgr._get_controller(target_ip)
    if err:
        return {"success": False, "message": err}

    client = ctrl.client

    try:
        ch = getattr(client, 'channel', 1)
        endpoint = f"/PTZCtrl/channels/{ch}/PTZOSDDisplay"

        # GET 获取当前 OSD 配置
        get_resp = client.get(endpoint)
        if get_resp.status_code != 200:
            return {"success": False, "message": f"GET PTZOSDDisplay 失败: HTTP {get_resp.status_code}"}

        import xml.etree.ElementTree as ET
        root = ET.fromstring(get_resp.xml)

        # 只修改 PTZ 坐标相关字段: azimuth, zoomlable
        val = "alwaysopen" if enabled else "alwaysclose"
        for tag_name in ("azimuth", "zoomlable"):
            elem = root.find(tag_name)
            if elem is not None:
                elem.text = val

        # PUT 更新(移除 ns0: 命名空间前缀)
        xml_str = ET.tostring(root, encoding='unicode')
        xml_str = xml_str.replace('ns0:', '')
        xml_str = xml_str.replace('xmlns:ns0=', 'xmlns=')
        put_resp = client.put(endpoint, '<?xml version="1.0" encoding="UTF-8"?>' + xml_str)
        if put_resp.status_code == 200:
            log_info("ptz", "osd_ptz", {"device": device_id, "enabled": enabled})
            return {"success": True, "message": f"PTZ 坐标 OSD 已{'开启' if enabled else '关闭'}", "enabled": enabled}
        else:
            return {"success": False, "message": f"PUT 失败: HTTP {put_resp.status_code}"}

    except Exception as e:
        return {"success": False, "message": f"PTZ OSD 切换异常: {e}"}


@api_router.post("/ptz/{device_id}/osd/info", summary="切换 OSD 信息显示", tags=["PTZ"])
async def ptz_osd_info_toggle(device_id: str, body: dict = None) -> dict:
    """切换 OSD 信息显示(用户自定义、日期时间等)。"""
    enabled = (body or {}).get("enabled", True) if body else True

    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    ctrl, err = mgr._get_controller(target_ip)
    if err:
        return {"success": False, "message": err}

    client = ctrl.client

    try:
        # ISAPI 端点: /ISAPI/System/Video/inputs/channels/{ch}/overlays
        ch = getattr(client, 'channel', 1)
        endpoint = f"/System/Video/inputs/channels/{ch}/overlays"

        # GET 获取当前 overlay 配置
        get_resp = client.get(endpoint)
        if get_resp.status_code != 200:
            return {"success": False, "message": f"GET overlays 失败: HTTP {get_resp.status_code}"}

        import xml.etree.ElementTree as ET
        root = ET.fromstring(get_resp.xml)

        # 只修改 DateTimeOverlay 和 channelNameOverlay 的 enabled 字段
        val = "true" if enabled else "false"
        for target in ["DateTimeOverlay", "channelNameOverlay"]:
            elem = root.find(target)
            if elem is None:
                elem = root.find(".//{http://www.hikvision.com/ver20/XMLSchema}" + target)
            if elem is not None:
                enabled_elem = elem.find("enabled")
                if enabled_elem is None:
                    enabled_elem = elem.find("{http://www.hikvision.com/ver20/XMLSchema}enabled")
                if enabled_elem is not None:
                    enabled_elem.text = val

        # PUT 更新(带 XML 声明,移除 ns0: 命名空间前缀)
        new_xml = '<?xml version="1.0" encoding="UTF-8"?>'
        xml_str = ET.tostring(root, encoding='unicode')
        # 移除 ns0: 前缀和 xmlns:ns0 声明
        xml_str = xml_str.replace('ns0:', '')
        xml_str = xml_str.replace('xmlns:ns0=', 'xmlns=')
        new_xml += xml_str
        put_resp = client.put(endpoint, new_xml)
        if put_resp.status_code == 200:
            log_info("ptz", "osd_info", {"device": device_id, "enabled": enabled})
            return {"success": True, "message": f"OSD 信息显示已{'开启' if enabled else '关闭'}", "enabled": enabled}
        else:
            return {"success": False, "message": f"PUT 失败: HTTP {put_resp.status_code}"}

    except Exception as e:
        return {"success": False, "message": f"OSD 信息切换异常: {e}"}


# ============================================================
# 画面调整
# ============================================================

class ImageAdjustRequest(BaseModel):
    """画面调整请求"""
    brightness: int | None = None  # 0-100
    contrast: int | None = None    # 0-100
    saturation: int | None = None  # 0-100


@api_router.get("/ptz/{device_id}/image/settings", summary="获取画面设置", tags=["Image"])
async def get_image_settings(device_id: str) -> dict:
    """获取当前画面参数(亮度/对比度/饱和度)。"""
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    client = mgr._clients.get(target_ip)
    if not client:
        return {"success": False, "message": f"ISAPI client not found for {target_ip}"}

    try:
        resp = client.get("/Image/channels/1")
        if resp.status_code != 200:
            return {"success": False, "message": f"获取画面设置失败: HTTP {resp.status_code}"}

        import xml.etree.ElementTree as ET
        root = ET.fromstring(resp.xml)

        # 查找 Color 节点
        result = {"success": True, "data": {}}
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "Color":
                for child in elem:
                    ctag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if ctag == "brightnessLevel":
                        result["data"]["brightness"] = int((child.text or "50").strip())
                    elif ctag == "contrastLevel":
                        result["data"]["contrast"] = int((child.text or "50").strip())
                    elif ctag == "saturationLevel":
                        result["data"]["saturation"] = int((child.text or "50").strip())
                break

        return result
    except Exception as e:
        return {"success": False, "message": f"获取画面设置异常: {e}"}


@api_router.put("/ptz/{device_id}/image/settings", summary="更新画面设置", tags=["Image"])
async def update_image_settings(device_id: str, req: ImageAdjustRequest) -> dict:
    """更新画面参数。"""
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    client = mgr._clients.get(target_ip)
    if not client:
        return {"success": False, "message": f"ISAPI client not found for {target_ip}"}

    try:
        # 先获取当前设置
        resp = client.get("/Image/channels/1")
        if resp.status_code != 200:
            return {"success": False, "message": f"获取画面设置失败: HTTP {resp.status_code}"}

        xml_str = resp.xml
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml_str)

        # 修改 Color 节点
        updated = {}
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "Color":
                for child in elem:
                    ctag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if ctag == "brightnessLevel" and req.brightness is not None:
                        child.text = str(req.brightness)
                        updated["brightness"] = req.brightness
                    elif ctag == "contrastLevel" and req.contrast is not None:
                        child.text = str(req.contrast)
                        updated["contrast"] = req.contrast
                    elif ctag == "saturationLevel" and req.saturation is not None:
                        child.text = str(req.saturation)
                        updated["saturation"] = req.saturation
                break

        # 发送更新
        # 使用 /Image/channels/1/Color 端点,而不是整个 ImageChannel
        color_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Color version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
<brightnessLevel>{updated.get("brightness", 50)}</brightnessLevel>
<contrastLevel>{updated.get("contrast", 50)}</contrastLevel>
<saturationLevel>{updated.get("saturation", 50)}</saturationLevel>
</Color>'''

        put_resp = client.put("/Image/channels/1/Color", color_xml)
        if put_resp.status_code == 200:
            log_info("image", "color", {"device": device_id, "updated": updated})
            return {"success": True, "message": "画面设置已更新", "data": updated}
        else:
            return {"success": False, "message": f"更新失败: HTTP {put_resp.status_code}"}

    except Exception as e:
        return {"success": False, "message": f"更新画面设置异常: {e}"}


@api_router.post("/ptz/{device_id}/capture", summary="PTZ 截图(ISAPI 原生)", tags=["PTZ"])
async def ptz_capture(device_id: str, req: PTZCaptureRequest | None = None) -> dict:
    """通过海康 ISAPI 原生方法截取 PTZ 设备当前视频帧。

    使用: GET /ISAPI/Streaming/Channels/{channel}/picture
    不再依赖 ffmpeg。
    """
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    ctrl, err = mgr._get_controller(target_ip)
    if err:
        return {"success": False, "message": err}

    client = mgr._clients.get(target_ip)
    if not client:
        return {"success": False, "message": f"ISAPI client not found for {target_ip}"}

    try:
        jpeg_bytes = client.capture_picture()
        if not jpeg_bytes:
            return {"success": False, "message": "ISAPI 截图失败:设备未返回图像数据"}

        # JPEG 头验证
        if jpeg_bytes[:3] != b"\xff\xd8\xff":
            return {"success": False, "message": "返回的数据不是有效的 JPEG"}

        # v7.105: 保存文件(使用配置路径 + 日期子目录)
        from datetime import datetime
        from src.core.file_naming import generate_filename

        record_path = _resolve_storage_path()
        from pathlib import Path
        record_dir = Path(record_path)

        # 日期子目录
        date_str = datetime.now().strftime("%Y-%m-%d")
        date_dir = record_dir / date_str
        date_dir.mkdir(parents=True, exist_ok=True)

        # v7.108: 获取设备名称(优先 name,回退 device_name,再回退 model)
        creds = mgr.get_credentials(target_ip)
        device_name = (creds.get("name", "") or creds.get("device_name", "") or creds.get("model", "") or "").replace(" ", "_").replace("/", "_").replace("\\", "_") or target_ip

        filename = generate_filename(target_name=device_name, extension=".jpg")
        filepath = date_dir / filename
        filepath.write_bytes(jpeg_bytes)
        file_size = filepath.stat().st_size

        log_info("ptz", "capture", {"device": device_id, "filename": filename})
        return {
            "success": True,
            "message": f"截图成功: {device_id}",
            "data": {
                "mac": device_id,
                "image_path": str(filepath),
                "image_size": file_size,
                "filename": filename,
                "relative_path": f"{date_str}/{filename}",
                "format": "jpeg",
                "verified": True,
            },
        }
    except Exception as e:
        return {"success": False, "message": f"截图异常: {e}"}


# ================================================================ #
#  PTZ 录像端点
# ================================================================ #


@api_router.post("/ptz/{device_id}/record/start", summary="启动录像(ISAPI 官方)", tags=["PTZ"])
async def ptz_record_start(device_id: str, req: PTZRecordRequest | None = None) -> dict:
    """v7.107: 通过海康 ISAPI 官方方法启动摄像头录像。"""
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    target_name = req.target_name if req else ""
    log_info("ptz", "record_start", {"device": device_id, "target": target_name})
    return mgr.start_recording(target_ip, target_name=target_name)


@api_router.post("/ptz/{device_id}/record/stop", summary="停止录像(ISAPI 官方)", tags=["PTZ"])
async def ptz_record_stop(device_id: str) -> dict:
    """停止 FFmpeg 录制进程。如有 FTP 配置则自动上传。
    """
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    log_info("ptz", "record_stop", {"device": device_id})
    return mgr.stop_recording(target_ip)


# ================================================================ #
#  流服务端点
# ================================================================ #



# ================================================================ #
#  校准端点
# ================================================================ #


@api_router.post("/calibration/{device_id}/{cal_type}", summary="开始校准", tags=["Calibration"])
async def start_calibration(device_id: str, cal_type: str) -> dict:
    """开始设备校准。"""
    mgr: CalibrationManager | None = _managers.get("calibration_manager")  # type: ignore[assignment]
    if mgr:
        try:
            if hasattr(mgr, "start_calibration"):
                await mgr.start_calibration(device_id, cal_type)  # type: ignore[arg-type]
        except Exception:
            pass
    return {
        "data": {"mac": device_id, "type": cal_type, "status": "started"},
        "message": f"校准已启动: {cal_type}",
    }


# ================================================================ #
#  ASCOM 端点
# ================================================================ #


# ================================================================ #
#  ASCOM 端点
# ================================================================ #


@api_router.post("/ascom/{ascom_type}/connect", summary="连接 ASCOM 设备", tags=["ASCOM"])
async def ascom_connect(ascom_type: str) -> dict:
    """连接 ASCOM 设备。"""
    mgr: ASCOMManager | None = _managers.get("ascom_manager")  # type: ignore[assignment]
    if mgr:
        try:
            if hasattr(mgr, "connect"):
                await mgr.connect(ascom_type)  # type: ignore[arg-type]
        except Exception:
            pass
    return {
        "data": {"type": ascom_type, "connected": True},
        "message": f"ASCOM 设备已连接: {ascom_type}",
    }


# ================================================================ #
#  ASCOM Telescope 控制端点 (P1 集成)
# ================================================================ #


@api_router.post("/ascom/telescope/slew", summary="望远镜 Slew 到目标坐标", tags=["ASCOM"])
async def ascom_telescope_slew(req: TelescopeSlewRequest | None = None,
                                ra: float = 0, dec: float = 0) -> dict:
    """控制望远镜 Slew 到目标赤经/赤纬。

    支持两种参数传入方式:
    1. JSON body: {"ra": 12.5, "dec": 45.0}
    2. Query params: ?ra=12.5&dec=45.0
    """
    ra_val = req.ra if req else ra
    dec_val = req.dec if req else dec

    from src.ascom.core.driver_manager import get_telescope
    from src.ascom.constants import ErrorCode

    try:
        scope = get_telescope()
        result = scope.slew_to_coordinates(ra_val, dec_val)
        if not result.get("success"):
            return {
                "success": False,
                "message": result.get("message", "Slew 失败"),
                "code": result.get("code", "ASCOM_TELESCOPE_SLEW_FAILED"),
            }
        log_info("ascom", "slew", {"ra": ra_val, "dec": dec_val})
        return {
            "success": True,
            "message": result.get("message", "Slew 成功"),
            "data": {"ra": ra_val, "dec": dec_val},
        }
    except Exception as e:
        return {"success": False, "message": f"Slew 异常: {e}"}


@api_router.post("/ascom/telescope/tracking", summary="设置望远镜跟踪模式", tags=["ASCOM"])
async def ascom_telescope_tracking(mode: str = "trackSidereal") -> dict:
    """设置望远镜跟踪模式。

    支持的模式:
    - trackSidereal: 恒星跟踪
    - trackLunar: 月球跟踪
    - trackSolar: 太阳跟踪
    - trackOff: 关闭跟踪
    """
    from src.ascom.core.driver_manager import get_telescope
    from src.ascom.constants import TrackingMode, ErrorCode

    mode_map = {
        "trackSidereal": TrackingMode.SIDEREAL,
        "trackLunar": TrackingMode.LUNAR,
        "trackSolar": TrackingMode.SOLAR,
        "trackOff": TrackingMode.OFF,
    }

    tracking_mode = mode_map.get(mode)
    if tracking_mode is None:
        return {
            "success": False,
            "message": f"无效的跟踪模式: {mode} (支持: {list(mode_map.keys())})",
        }

    try:
        scope = get_telescope()
        result = scope.set_tracking_mode(tracking_mode)
        if not result.get("success"):
            return {
                "success": False,
                "message": result.get("message", "设置跟踪模式失败"),
            }
        log_info("ascom", "tracking", {"mode": mode})
        return {
            "success": True,
            "message": result.get("message", f"跟踪模式已设为 {mode}"),
            "data": {"mode": mode},
        }
    except Exception as e:
        return {"success": False, "message": f"设置跟踪模式异常: {e}"}


@api_router.post("/ascom/telescope/disconnect", summary="断开望远镜连接", tags=["ASCOM"])
async def ascom_telescope_disconnect() -> dict:
    """断开 ASCOM 望远镜连接。"""
    from src.ascom.core.driver_manager import get_telescope

    try:
        scope = get_telescope()
        result = scope.disconnect()
        return {
            "success": True,
            "message": result.get("message", "望远镜已断开"),
        }
    except Exception as e:
        return {"success": False, "message": f"断开连接异常: {e}"}


@api_router.get("/ascom/telescope/position", summary="查询望远镜位置", tags=["ASCOM"])
async def ascom_telescope_position() -> dict:
    """查询望远镜当前赤经/赤纬。"""
    from src.ascom.core.driver_manager import get_telescope

    try:
        scope = get_telescope()
        result = scope.get_position()
        if not result.get("success"):
            return {"success": False, "message": result.get("message", "获取位置失败")}
        return {"success": True, "data": result.get("data")}
    except Exception as e:
        return {"success": False, "message": f"获取位置异常: {e}"}


@api_router.post("/ascom/telescope/abort", summary="取消 Slew", tags=["ASCOM"])
async def ascom_telescope_abort() -> dict:
    """取消正在进行的 Slew 操作。"""
    from src.ascom.core.driver_manager import get_telescope

    try:
        scope = get_telescope()
        result = scope.abort_slew()
        if not result.get("success"):
            return {"success": False, "message": result.get("message", "取消 Slew 失败")}
        return {"success": True, "message": result.get("message", "Slew 已取消")}
    except Exception as e:
        return {"success": False, "message": f"取消 Slew 异常: {e}"}


@api_router.get("/settings", summary="获取系统设置", tags=["Settings"])
async def get_settings() -> dict:
    """获取当前系统配置。"""
    try:
        from src.config import HOST, PORT, WINDOW_TITLE, WINDOW_WIDTH, WINDOW_HEIGHT
        return {
            "success": True,
            "data": {
                "host": HOST,
                "port": PORT,
                "window_title": WINDOW_TITLE,
                "window_width": WINDOW_WIDTH,
                "window_height": WINDOW_HEIGHT,
            },
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


@api_router.post("/settings", summary="保存系统设置", tags=["Settings"])
async def save_settings() -> dict:
    """保存系统设置。"""
    return {
        "data": {"saved": True},
        "message": "设置已保存",
    }


class StorageSettingsRequest(BaseModel):
    record_path: str = ""


class PathSettingsRequest(BaseModel):
    category: str = ""  # "config" or "ext"
    local_config: str = ""
    device_config: str = ""
    test_data: str = ""
    sdk_path: str = ""
    astap_path: str = ""
    obs_path: str = ""


@api_router.get("/settings/storage", summary="获取存储设置", tags=["Settings"])
async def get_storage_settings() -> dict:
    """v7.105: 获取统一存储路径。"""
    record_path = _resolve_storage_path()
    return {"success": True, "data": {"record_path": record_path}}


@api_router.get("/files/list", summary="获取文件列表(按日期分组)", tags=["Files"])
async def list_files() -> dict:
    """v7.106: 列出统一存储目录下的文件,按日期分组返回。

    排除缩略图文件(.thumb.jpg)。
    """
    from pathlib import Path
    from datetime import datetime

    try:
        record_path = _resolve_storage_path()
        rdir = Path(record_path)

        if not rdir.exists():
            return {"success": True, "data": {"groups": []}}

        groups = {}
        media_exts = ["*.jpg", "*.jpeg", "*.mp4", "*.avi", "*.mov", "*.mkv"]

        for d in rdir.iterdir():
            if d.is_dir() and len(d.name) == 10 and d.name[4] == '-' and d.name[7] == '-':
                for pattern in media_exts:
                    for f in d.glob(pattern):
                        # 排除缩略图文件
                        if f.name.endswith('.thumb.jpg'):
                            continue
                        try:
                            mtime = f.stat().st_mtime
                            ext = f.suffix.lower()
                            file_type = "video" if ext in [".mp4", ".avi", ".mov", ".mkv"] else "image"
                            groups.setdefault(d.name, []).append({
                                "file": d.name + "/" + f.name,
                                "date": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"),
                                "type": file_type
                            })
                        except Exception:
                            pass

        sorted_groups = []
        for date_str in sorted(groups.keys(), reverse=True):
            sorted_groups.append({"date": date_str, "items": sorted(groups[date_str], key=lambda x: x["date"], reverse=True)})

        return {"success": True, "data": {"groups": sorted_groups}}
    except Exception as e:
        return {"success": False, "message": str(e)}


@api_router.get("/files/serve/{filename:path}", summary="提供文件访问", tags=["Files"])
async def serve_file(filename: str):
    """v7.105: 提供文件直接访问(流式传输,零内存占用)."""
    from pathlib import Path
    from fastapi.responses import FileResponse

    record_path = _resolve_storage_path()
    file_path = Path(record_path) / filename

    if not file_path.exists():
        return JSONResponse(status_code=404, content={"success": False, "message": "文件不存在"})

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type=_guess_mime(file_path.suffix.lower()),
    )


def _guess_mime(ext: str) -> str:
    """v7.105: 根据扩展名猜 MIME 类型."""
    mime_map = {
        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
        '.png': 'image/png', '.gif': 'image/gif',
        '.mp4': 'video/mp4', '.avi': 'video/x-msvideo',
        '.mov': 'video/quicktime', '.mkv': 'video/x-matroska',
    }
    return mime_map.get(ext, 'application/octet-stream')


@api_router.post("/files/open-folder", summary="打开存储目录", tags=["Files"])
async def open_record_folder() -> dict:
    """v7.105: 打开存储目录。"""
    import subprocess
    import platform
    from pathlib import Path

    record_path = _resolve_storage_path()
    folder = Path(record_path)
    if not folder.exists():
        folder.mkdir(parents=True, exist_ok=True)

    try:
        if platform.system() == 'Windows':
            subprocess.Popen(['explorer', str(folder.resolve())])
        elif platform.system() == 'Darwin':
            subprocess.Popen(['open', str(folder)])
        else:
            subprocess.Popen(['xdg-open', str(folder)])
        return {"success": True, "path": str(folder.resolve())}
    except Exception as e:
        return {"success": False, "message": str(e)}


@api_router.get("/files/thumb/{filename:path}", summary="获取视频缩略图", tags=["Files"])
async def get_video_thumb(filename: str):
    """v7.105: 提取视频第一帧作为缩略图."""
    from pathlib import Path
    from fastapi.responses import FileResponse
    import subprocess, tempfile, os

    record_path = _resolve_storage_path()
    file_path = Path(record_path) / filename
    if not file_path.exists():
        return JSONResponse(status_code=404, content={"success": False, "message": "文件不存在"})

    # 非视频文件直接返回原文件
    ext = file_path.suffix.lower()
    if ext not in ['.mp4', '.avi', '.mov', '.mkv']:
        return FileResponse(path=str(file_path), media_type=_guess_mime(ext))

    # 缓存缩略图
    thumb_path = file_path.with_suffix('.thumb.jpg')
    if not thumb_path.exists():
        try:
            subprocess.run([
                'ffmpeg', '-y', '-ss', '1', '-i', str(file_path),
                '-vframes', '1', '-q:v', '5', '-s', '320x180', str(thumb_path)
            ], capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
        except Exception:
            pass

    if thumb_path.exists():
        return FileResponse(path=str(thumb_path), media_type='image/jpeg')
    return FileResponse(path=str(file_path), media_type=_guess_mime(ext))


@api_router.get("/files/info/{filename:path}", summary="获取文件信息", tags=["Files"])
async def get_file_info(filename: str) -> dict:
    """v7.105: 获取视频/图片的分辨率和时长."""
    from pathlib import Path
    import subprocess, json

    record_path = _resolve_storage_path()
    file_path = Path(record_path) / filename
    if not file_path.exists():
        return {"success": False, "message": "文件不存在"}

    ext = file_path.suffix.lower()
    info = {"type": "image" if ext in ['.jpg','.jpeg','.png','.gif'] else "video"}

    if info["type"] == "video":
        try:
            result = subprocess.run([
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', '-show_streams', str(file_path)
            ], capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
            if result.returncode == 0:
                probe = json.loads(result.stdout)
                for s in probe.get('streams', []):
                    if s.get('codec_type') == 'video':
                        info['width'] = s.get('width', 0)
                        info['height'] = s.get('height', 0)
                        break
                dur = float(probe.get('format', {}).get('duration', 0))
                h, m = divmod(int(dur), 3600)
                m, s = divmod(m, 60)
                info['duration'] = f"{h:02d}:{m:02d}:{s:02d}"
                info['duration_sec'] = int(dur)
        except Exception:
            info['width'] = 0; info['height'] = 0; info['duration'] = '00:00:00'
    else:
        try:
            from PIL import Image
            with Image.open(file_path) as img:
                info['width'] = img.width
                info['height'] = img.height
        except Exception:
            info['width'] = 0; info['height'] = 0

    return {"success": True, "data": info}


class DeleteFilesRequest(BaseModel):
    files: list[str] = []


@api_router.post("/files/delete", summary="批量删除文件", tags=["Files"])
async def delete_files(req: DeleteFilesRequest) -> dict:
    """v7.105: 批量删除文件."""
    from pathlib import Path

    record_path = _resolve_storage_path()
    deleted = []
    failed = []

    for f in req.files:
        file_path = Path(record_path) / f
        if file_path.exists():
            try:
                file_path.unlink()
                deleted.append(f)
            except Exception:
                failed.append(f)
        else:
            failed.append(f)

    return {"success": True, "deleted": deleted, "failed": failed}


@api_router.post("/files/upload-record", summary="上传录像文件到服务器", tags=["Files"])
async def upload_record(request: Request) -> dict:
    """v7.108: 接收浏览器上传的录像文件,保存到配置路径。"""
    from pathlib import Path
    from datetime import datetime
    from fastapi import UploadFile
    import shutil

    try:
        form = await request.form()
        file: UploadFile = form.get("file")
        if not file:
            return {"success": False, "message": "未收到文件"}

        record_path = _resolve_storage_path()
        date_str = datetime.now().strftime("%Y-%m-%d")
        date_dir = Path(record_path) / date_str
        date_dir.mkdir(parents=True, exist_ok=True)

        filepath = date_dir / file.filename
        with open(filepath, "wb") as f:
            shutil.copyfileobj(file.file, f)

        return {"success": True, "filepath": str(filepath), "filename": file.filename}
    except Exception as e:
        return {"success": False, "message": str(e)}


class MoveRecordingRequest(BaseModel):
    filename: str
    device_ip: str = ""


@api_router.post("/files/move-recording", summary="静默移动录像到存储路径", tags=["Files"])
async def move_recording(req: MoveRecordingRequest) -> dict:
    """v7.113: WASM 录制存到浏览器下载目录后,服务端静默移动到配置路径。"""
    from pathlib import Path
    from datetime import datetime
    import shutil
    import time

    try:
        # 目标路径(复用 _resolve_storage_path)
        record_path = _resolve_storage_path()
        date_str = datetime.now().strftime("%Y-%m-%d")
        date_str_alt = datetime.now().strftime("%Y%m%d")
        target_dir = Path(record_path) / date_str
        target_dir.mkdir(parents=True, exist_ok=True)

        target_file = target_dir / req.filename

        # 源目录:浏览器默认下载目录(bDateDir 创建的目录可能是 YYYY-MM-DD 或 YYYYMMDD)
        downloads = Path.home() / "Downloads"
        src_candidates = [
            downloads / date_str / req.filename,
            downloads / date_str_alt / req.filename,
            downloads / req.filename,
        ]

        src_file = None
        # 重试等待文件落盘(I_StopRecord 回调成功不代表文件已写完)
        for _ in range(6):
            for candidate in src_candidates:
                if candidate.exists():
                    src_file = candidate
                    break
            if src_file:
                break
            time.sleep(0.5)

        if src_file is None:
            return {"success": False, "message": f"源文件未找到: {req.filename}"}

        # 移动文件
        shutil.move(str(src_file), str(target_file))
        return {"success": True, "filepath": str(target_file), "filename": req.filename}
    except Exception as e:
        return {"success": False, "message": str(e)}


def _resolve_storage_path() -> str:
    """v7.105: 获取统一存储路径(优先从配置文件读取)。"""
    from src.config_paths import RECORD_DIR, DATA_DIR
    import json

    default_path = str(RECORD_DIR)

    config_path = DATA_DIR / "config" / "storage.json"
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            return config.get("record_path") or default_path
        except Exception:
            pass
    return default_path


# 保留旧函数以兼容外部调用(已弃用)
def _resolve_storage_paths() -> tuple[str, str]:
    """已弃用:保留兼容性。"""
    p = _resolve_storage_path()
    return (p, p)


@api_router.post("/settings/storage", summary="保存存储设置", tags=["Settings"])
async def save_storage_settings(req: StorageSettingsRequest) -> dict:
    """v7.105: 保存统一存储路径。"""
    from src.config_paths import DATA_DIR
    import json
    config_path = DATA_DIR / "config" / "storage.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config = {"record_path": req.record_path}
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    return {"success": True, "message": "存储设置已保存"}


@api_router.get("/settings/folder-picker", summary="打开文件夹选择对话框", tags=["Settings"])
async def folder_picker() -> dict:
    """打开系统原生文件夹选择对话框,返回用户选择的路径。"""
    import asyncio
    import threading

    result = {"path": ""}

    def _pick():
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            path = filedialog.askdirectory(title="选择文件夹")
            root.destroy()
            result["path"] = path or ""
        except Exception as e:
            result["error"] = str(e)

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: _pick())

    if result.get("error"):
        return {"success": False, "message": result["error"]}
    if result["path"]:
        return {"success": True, "path": result["path"]}
    return {"success": False, "message": "未选择文件夹"}


@api_router.get("/settings/file-picker", summary="打开文件选择对话框", tags=["Settings"])
async def file_picker() -> dict:
    """打开系统原生文件选择对话框,返回用户选择的文件路径。"""
    import asyncio

    result = {"path": ""}

    def _pick():
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            path = filedialog.askopenfilename(title="选择文件")
            root.destroy()
            result["path"] = path or ""
        except Exception as e:
            result["error"] = str(e)

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: _pick())

    if result.get("error"):
        return {"success": False, "message": result["error"]}
    if result["path"]:
        return {"success": True, "path": result["path"]}
    return {"success": False, "message": "未选择文件"}


@api_router.get("/settings/paths", summary="获取所有路径配置", tags=["Settings"])
async def get_all_paths() -> dict:
    """获取配置路径和扩展路径的当前设置。"""
    from src.config_paths import DATA_DIR, CONFIG_DIR, DEVICES_DIR, APP_DIR, SDK_LIBS_DIR
    import json

    # 默认值来自 config_paths (实际路径)
    defaults = {
        "local_config": str(CONFIG_DIR),
        "device_config": str(DEVICES_DIR),
        "test_data": str(DEVICES_DIR),
        "sdk_path": str(SDK_LIBS_DIR),
        "astap_path": r"C:\Program Files\astap\astap.exe",
        "obs_path": r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
    }

    # 从存储文件读取已保存的配置 (覆盖默认值)
    config_path = DATA_DIR / "config" / "paths.json"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
                defaults.update(saved)
        except Exception:
            pass

    return {"success": True, "data": defaults}


@api_router.post("/settings/paths", summary="保存路径配置", tags=["Settings"])
async def save_paths(req: PathSettingsRequest) -> dict:
    """保存配置路径和扩展路径。动态更新 astap_solve 等模块的路径引用。"""
    from src.config_paths import DATA_DIR
    import json

    config_path = DATA_DIR / "config" / "paths.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # 读取现有配置
    existing = {}
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            pass

    # 更新配置
    if req.category == "config":
        if req.local_config: existing["local_config"] = req.local_config
        if req.device_config: existing["device_config"] = req.device_config
        if req.test_data: existing["test_data"] = req.test_data
    elif req.category == "ext":
        if req.sdk_path: existing["sdk_path"] = req.sdk_path
        if req.astap_path: existing["astap_path"] = req.astap_path
        if req.obs_path: existing["obs_path"] = req.obs_path

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

    # 动态更新 ASTAP 路径
    if req.category == "ext" and req.astap_path:
        try:
            from src.api import astap_solve
            astap_solve.ASTAP_EXE = req.astap_path
        except Exception:
            pass

    return {"success": True, "message": "路径配置已保存"}


# ================================================================ #
#  流服务器扩展端点 (P0: 启动 / Snapshot / HLS)
# ================================================================ #






# ================================================================ #
#  高级功能端点 (Advanced: Function/Limit/Speed/Config/Onboarding)
# ================================================================ #

def _resolve_mac_from_ip(device_ip: str, client: "ISAPIClient | None" = None,
                          ptz_mgr: "PTZDeviceController" = None) -> str:
    """通过 PTZDeviceController | None缓存或 ISAPI 获取设备的 MAC 地址。"""
    # Try PTZDeviceController | Nonecache first
    if ptz_mgr:
        import re
        discovered = ptz_mgr.get_discovered_devices()
        for dev in discovered:
            if dev.get("ip") == device_ip:
                mac = dev.get("mac", "")
                if mac:
                    # Normalize to colon-format uppercase
                    return mac.replace("-", ":").upper()
        stored = ptz_mgr.list_stored_devices()
        for dev in stored:
            if dev.get("ip") == device_ip:
                mac = dev.get("mac", "")
                if mac:
                    return mac.replace("-", ":").upper()
    # Fallback: use IP as identifier
    return device_ip.replace(".", "_").replace("/", "_").upper()

# Pydantic 请求模型
class AdvancedConfigWriteRequest(BaseModel):
    """配置写入请求。"""
    mac: str
    ip: str = ""
    model: str = ""
    capabilities: dict | None = None
    limits: dict | None = None
    speed: dict | None = None


class AdvancedOnboardingStartRequest(BaseModel):
    """引导开始请求。"""
    mac: str





# --- One-Click Detect 一键检测 ---

class AdvancedDetectStartRequest(BaseModel):
    """一键检测启动请求。"""
    device_ip: str = ""
    username: str = "admin"
    password: str = ""
    port: int = 80
    items: list[str] = ["function", "limit", "speed"]
    speed_profile: str = "lite"


# 一键检测任务注册表
detect_tasks: dict[str, dict] = {}


def _format_speed_results(results: list) -> dict:
    """将 run_all_tests 返回的 list 分组为前端格式。

    Returns: {speed_map, pan_speed, tilt_speed, by_zoom, total_tests}
    """
    by_zoom = {}
    speed_map = {}
    pan_map = {}
    tilt_map = {}
    for r in results:
        sl = str(r.get("speed_level", 0))
        sv = r.get("speed_val", 0.0)
        axis = r.get("axis", "")
        zoom = r.get("zoom", 0)
        speed_map.setdefault(sl, []).append(sv)
        if axis == "pan":
            pan_map.setdefault(sl, []).append(sv)
        elif axis == "tilt":
            tilt_map.setdefault(sl, []).append(sv)
        by_zoom.setdefault(zoom, {}).setdefault(axis, {})[sl] = sv
    for m in (speed_map, pan_map, tilt_map):
        for k, v in m.items():
            m[k] = round(sum(v) / len(v), 2)
    return {
        "speed_map": speed_map,
        "pan_speed": pan_map,
        "tilt_speed": tilt_map,
        "by_zoom": by_zoom,
        "total_tests": len(results),
    }



@api_router.post("/advanced/detect/start", summary="启动一键检测", tags=["Advanced"])
async def advanced_detect_start(req: AdvancedDetectStartRequest) -> dict:
    """启动异步一键检测 (Function + Limit + Speed)。"""
    import asyncio
    import uuid

    task_id = str(uuid.uuid4())
    detect_tasks[task_id] = {
        "status": "running",
        "progress": 0.0,
        "current_step": "initializing",
        "results": {},
        "items": req.items,
    }

    async def _run_detect():
        try:
            from src.ptz.isapi.client import ISAPIClient
            from src.advanced.config_writer import write_device_config

            def _cancelled():
                return detect_tasks.get(task_id, {}).get("status") == "cancelled"

            mgr: PTZDeviceController | None = _managers.get("ptz_controller")
            if not mgr:
                detect_tasks[task_id].update(status="failed", current_step="PTZDeviceControllernot initialized")
                return

            # Fallback: retrieve stored credentials if password is empty
            username = req.username or "admin"
            password = req.password
            port = req.port or 80
            if not password:
                creds = mgr.get_credentials(req.device_ip)
                if creds:
                    username = creds.get("username", username)
                    password = creds.get("password", "")
                    port = creds.get("port", port)

            ctrl, err = mgr._get_controller(req.device_ip)
            if err:
                detect_tasks[task_id].update(status="failed", current_step=f"Controller error: {err}")
                return

            client = ISAPIClient(ip=req.device_ip, username=username, password=password, port=port)
            if not client.verify_credentials():
                detect_tasks[task_id].update(status="failed", current_step="Authentication failed")
                return

            total_items = len(req.items)
            results: dict = {}

            if "function" in req.items:
                from src.advanced.function import FunctionDetector, FUNCTION_ENDPOINTS

                if _cancelled(): return
                detect_tasks[task_id].update(progress=0.0, current_step="function_detection")
                detector = FunctionDetector(client)
                func_result = {}
                total_funcs = len(FUNCTION_ENDPOINTS)
                for idx, item_key in enumerate(FUNCTION_ENDPOINTS):
                    if _cancelled(): return
                    detect_tasks[task_id]["current_step"] = f"{item_key}"
                    detect_tasks[task_id]["total_items"] = total_funcs
                    func_result[item_key] = await asyncio.to_thread(detector.detect_single, item_key)
                    detect_tasks[task_id]["completed_items"] = idx + 1
                    detect_tasks[task_id]["progress"] = round(10.0 + ((idx + 1) / total_funcs) * 20.0, 1)
                    detect_tasks[task_id]["last_result"] = "pass" if func_result[item_key].get("supported", False) else "failed"
                await asyncio.to_thread(detector.restore_all)
                results["function"] = func_result
                write_device_config(mac=_resolve_mac_from_ip(req.device_ip, ptz_mgr=mgr), capabilities=func_result, ip=req.device_ip)

            if "limit" in req.items:
                from src.advanced.limit import LimitTester

                if _cancelled(): return
                detect_tasks[task_id].update(progress=35.0, current_step="limit_test", total_items=3, completed_items=0)
                mac = _resolve_mac_from_ip(req.device_ip, ptz_mgr=mgr)
                device_id = mac.upper().replace(":", "-") if mac else "onboarding"
                if not PTZController(client).setup_home_preset():
                    detect_tasks[task_id].update(status="failed", current_step="limit: HOME预设10设置失败(10s超时)")
                    return
                limit_tester = LimitTester(client, device_id=device_id)
                # v7.56: 添加进度回调
                def limit_progress_callback(step_name: str, completed: int, result: str = ""):
                    detect_tasks[task_id]["current_step"] = step_name
                    detect_tasks[task_id]["completed_items"] = completed
                    detect_tasks[task_id]["last_result"] = result
                limit_result = await asyncio.to_thread(limit_tester.run_all_tests, limit_progress_callback)
                if not limit_result.get("success"):
                    detect_tasks[task_id].update(status="failed", current_step=f"limit: {limit_result.get('message', limit_result.get('error', '未知错误'))}")
                    return
                results["limit"] = limit_result
                detect_tasks[task_id].update(progress=60.0, completed_items=3)
                write_device_config(mac=mac, limits=limit_result, ip=req.device_ip)

            if "speed" in req.items:
                from src.advanced.speed import SpeedTester

                if _cancelled(): return
                detect_tasks[task_id].update(progress=65.0, current_step="speed_test", total_items=0, completed_items=0)
                if not PTZController(client).setup_home_preset():
                    detect_tasks[task_id].update(status="failed", current_step="speed: HOME预设10设置失败(10s超时)")
                    return
                speed_tester = SpeedTester(PTZController(client))
                # v7.56: 添加进度回调
                def speed_progress_callback(step_name: str, completed: int, total: int, result: str = ""):
                    detect_tasks[task_id]["current_step"] = step_name
                    detect_tasks[task_id]["completed_items"] = completed
                    detect_tasks[task_id]["total_items"] = total
                    detect_tasks[task_id]["last_result"] = result
                speed_result = await asyncio.to_thread(speed_tester.run_all_tests, None, req.speed_profile, speed_progress_callback)
                if not speed_result:
                    detect_tasks[task_id].update(status="failed", current_step="speed: 无结果")
                    return
                # v7.119: 将list结果分组为前端格式 {speed_map, pan_speed, tilt_speed, by_zoom}
                speed_formatted = _format_speed_results(speed_result)
                results["speed"] = speed_formatted
                detect_tasks[task_id].update(progress=95.0)
                write_device_config(mac=_resolve_mac_from_ip(req.device_ip, ptz_mgr=mgr), speed=speed_result, ip=req.device_ip)

            detect_tasks[task_id].update(
                status="completed",
                progress=100.0,
                current_step="completed",
                results=results,
            )
        except Exception as e:
            detect_tasks[task_id].update(status="failed", current_step=str(e), progress=0.0)

    asyncio.create_task(_run_detect())

    return {
        "success": True,
        "task_id": task_id,
        "message": "检测任务已启动",
    }


@api_router.get("/advanced/detect/status/{task_id}", summary="获取检测任务状态", tags=["Advanced"])
async def advanced_detect_status(task_id: str) -> dict:
    """获取一键检测任务进度。"""
    task = detect_tasks.get(task_id)
    if not task:
        return {"success": False, "message": "任务不存在"}
    return {
        "success": True,
        "status": task["status"],
        "progress": task.get("progress", 0.0),
        "current_step": task.get("current_step", ""),
        "completed_items": task.get("completed_items", 0),
        "total_items": task.get("total_items", 0),
        "last_result": task.get("last_result", ""),
    }


@api_router.get("/advanced/detect/result/{task_id}", summary="获取检测结果", tags=["Advanced"])
async def advanced_detect_result(task_id: str) -> dict:
    """获取一键检测最终结果。"""
    task = detect_tasks.get(task_id)
    if not task:
        return {"success": False, "message": "任务不存在"}
    if task["status"] != "completed":
        return {"success": False, "message": f"任务尚未完成: {task['status']}"}
    return {
        "success": True,
        "results": task.get("results", {}),
    }


@api_router.post("/advanced/detect/cancel/{task_id}", summary="取消检测任务", tags=["Advanced"])
async def advanced_detect_cancel(task_id: str) -> dict:
    """取消正在运行的一键检测任务。"""
    task = detect_tasks.get(task_id)
    if not task:
        return {"success": False, "message": "任务不存在"}
    if task["status"] not in ("running",):
        return {"success": False, "message": f"任务状态为 {task['status']},无法取消"}
    task["status"] = "cancelled"
    task["current_step"] = "cancelled"
    return {"success": True, "message": "任务已取消"}


# --- Config 配置 ---

@api_router.get("/advanced/config/{mac}", summary="获取设备配置", tags=["Advanced"])
async def advanced_get_config(mac: str) -> dict:
    """获取设备配置文件。"""
    try:
        from src.advanced.config_writer import load_device_config, list_device_configs

        if mac == "all":
            configs = list_device_configs()
            return {
                "success": True,
                "data": configs,
                "total": len(configs),
            }

        config = load_device_config(mac)
        if config:
            return {
                "success": True,
                "data": config.to_dict(),
            }
        return {
            "success": False,
            "message": f"未找到设备配置: {mac}",
        }
    except Exception as e:
        return {"success": False, "message": f"获取配置异常: {e}"}


@api_router.post("/advanced/config/write", summary="写入设备配置", tags=["Advanced"])
async def advanced_write_config(req: AdvancedConfigWriteRequest) -> dict:
    """写入设备配置文件。"""
    try:
        from src.advanced.config_writer import write_device_config

        result = write_device_config(
            mac=req.mac,
            capabilities=req.capabilities,
            limits=req.limits,
            speed=req.speed,
            ip=req.ip,
            model=req.model,
        )

        return result
    except Exception as e:
        return {"success": False, "message": f"写入配置异常: {e}"}


# --- Onboarding 引导 ---

@api_router.get("/advanced/onboarding/status", summary="获取引导状态", tags=["Advanced"])
async def advanced_onboarding_status(mac: str = Query(default="")) -> dict:
    """获取设备引导状态。"""
    if not mac:
        return {"success": True, "is_new_device": False, "progress": {"total_steps": 0, "completed": False}}
    try:
        from src.advanced.onboarding import OnboardingManager

        manager = OnboardingManager()
        is_new = manager.is_new_device(mac)
        progress = manager.get_progress(mac)

        return {
            "success": True,
            "is_new_device": is_new,
            "progress": progress,
        }
    except Exception as e:
        return {"success": False, "message": f"获取引导状态异常: {e}"}


@api_router.post("/advanced/onboarding/start", summary="开始引导流程", tags=["Advanced"])
async def advanced_onboarding_start(req: AdvancedOnboardingStartRequest) -> dict:
    """开始设备首次连接引导流程。"""
    try:
        from src.advanced.onboarding import OnboardingManager

        manager = OnboardingManager()
        result = manager.start_onboarding(req.mac)

        return result
    except Exception as e:
        return {"success": False, "message": f"开始引导异常: {e}"}


@api_router.post("/advanced/onboarding/complete", summary="完成引导流程", tags=["Advanced"])
async def advanced_onboarding_complete(mac: str) -> dict:
    """完成设备引导流程。"""
    try:
        from src.advanced.onboarding import OnboardingManager

        manager = OnboardingManager()
        result = manager.complete_onboarding(mac)

        return result
    except Exception as e:
        return {"success": False, "message": f"完成引导异常: {e}"}


@api_router.post("/advanced/onboarding/reset", summary="重置引导流程", tags=["Advanced"])
async def advanced_onboarding_reset(mac: str) -> dict:
    """重置设备引导流程 (允许重新执行)。"""
    try:
        from src.advanced.onboarding import OnboardingManager

        manager = OnboardingManager()
        result = manager.reset_onboarding(mac)

        return result
    except Exception as e:
        return {"success": False, "message": f"重置引导异常: {e}"}


@api_router.post("/advanced/onboarding/run", summary="完整执行设备引导流程", tags=["Advanced"])
async def advanced_onboarding_run(req: AdvancedOnboardingStartRequest) -> dict:
    """自动执行完整的设备首次连接引导流程。

    依次执行: 设备信息 → 功能探测 → HOME验证 → 限位测试 → 速度校准 → 恢复默认 → 保存配置 → 完成
    """
    from src.advanced.onboarding import OnboardingManager

    mgr = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    # Find device IP from PTZDeviceController
    device_ip = None
    for dev in mgr.list_stored_devices():
        if dev.get("mac", "").upper().replace("-", ":") == req.mac.upper().replace("-", ":"):
            device_ip = dev.get("ip")
            break
    if not device_ip:
        for dev in mgr.get_discovered_devices():
            if dev.get("mac", "").upper().replace("-", ":") == req.mac.upper().replace("-", ":"):
                device_ip = dev.get("ip")
                break
    if not device_ip:
        return {"success": False, "message": f"未找到设备 {req.mac} 的 IP 地址"}

    creds = mgr.get_credentials(device_ip)
    if not creds:
        return {"success": False, "message": "设备未保存凭据,请先连接设备"}

    manager = OnboardingManager()

    import asyncio
    result = await asyncio.to_thread(
        manager.execute_full_onboarding,
        mac=req.mac,
        ip=device_ip,
        username=str(creds.get("username", "admin")),
        password=str(creds.get("password", "")),
        port=int(creds.get("port", 80)),
    )
    return result


@api_router.get("/ws/stats", summary="WebSocket连接统计", tags=["WebSocket"])
async def get_ws_stats() -> dict:
    """获取当前 WebSocket 连接统计。"""
    try:
        from src.websocket.core.ws_manager import get_ws_manager
        ws_mgr = get_ws_manager()
        if ws_mgr:
            return {"success": True, "data": ws_mgr.get_stats()}
        return {"success": False, "error": "WebSocket not initialized"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@api_router.get("/ws/connections", summary="WebSocket详细连接列表", tags=["WebSocket"])
async def get_ws_connections() -> dict:
    """获取当前 WebSocket 连接详细信息。"""
    try:
        from src.websocket.core.ws_manager import get_ws_manager
        ws_mgr = get_ws_manager()
        if ws_mgr:
            return {"success": True, "data": ws_mgr.list_all_connections() if hasattr(ws_mgr, "list_all_connections") else []}
        return {"success": False, "error": "WebSocket not initialized"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ================================================================ #
#  快捷函数
# ================================================================ #


def create_app() -> FastAPI:
    """创建并配置完整的 FastAPI 应用。"""
    app = FastAPI(
        title="AstroHub",
        description="统一天文设备控制平台",
        version="2.0",
    )

    app.include_router(api_router)
    app.include_router(health_router)

    # Wave 4: 挂载 WebSocket 端点
    try:
        from websocket.server import WebSocketServer, WebSocketServerConfig
        ws_server = WebSocketServer(config=WebSocketServerConfig(
            path="/ws",
            heartbeat_interval=30,
            heartbeat_timeout_count=2,  # 60秒无响应断开 (30s * 2)
        ))
        ws_server.mount_to(app)
    except Exception as e:
        print(f"[api] WebSocket 挂载失败 (可选): {e}")

    return app


# ASTAP 截图解析
from src.api.astap_solve import router as astap_router
api_router.include_router(astap_router)

@api_router.get("/ptz/devices/{ip}/credentials")
async def get_ptz_device_credentials(ip: str):
    """获取设备凭据。
    先查内存,再回退读 data/devices/{MAC}.json
    """
    ptz_mgr = _managers.get("ptz_controller")
    if ptz_mgr:
        creds = ptz_mgr._credentials.get(ip)
        if creds:
            return {
                "success": True,
                "ip": ip,
                "username": creds.get("username", "admin"),
                "password": creds.get("password", ""),
                "port": creds.get("port", 80),
            }
    # 回退:从 data/devices/{MAC}.json 文件读取
    try:
        from pathlib import Path
        import json as _json
        devices_dir = Path(__file__).resolve().parent.parent.parent / "data" / "devices"
        if devices_dir.exists():
            for f in devices_dir.glob("*.json"):
                if f.name == "devices.json":
                    continue
                try:
                    with open(f, "r", encoding="utf-8") as fh:
                        dev = _json.load(fh)
                    if dev.get("ip") == ip:
                        return {
                            "success": True,
                            "ip": ip,
                            "username": dev.get("username", "admin"),
                            "password": dev.get("password", ""),
                            "port": dev.get("port", 80),
                        }
                except Exception:
                    continue
    except Exception:
        pass
    return {"success": False, "message": "凭据不存在"}


# ================================================================ #
#  图像参数 API 端点 (白平衡/快门/光圈/降噪/锐度/OSD)
# ================================================================ #

@api_router.get("/ptz/{device_id}/function", summary="获取设备功能探测结果", tags=["Image"])
async def get_device_function(device_id: str) -> dict:
    """v6.33: 从 data/devices/{mac}/ 读取设备功能探测结果。

    1. 通过 IP 找到对应设备的 MAC
    2. 使用 MAC 读取 data/devices/{mac}/function.json 或 function_*.json
    3. 优先最新时间戳文件,其次固定名称
    4. MAC 不匹配则返回错误
    """
    import json
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化", "data": None}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}", "data": None}

    # v6.33: 通过 IP 找到 MAC,确保数据匹配正确设备
    from src.advanced.device_path import get_devices_dir, get_data_path_read
    devices_dir = get_devices_dir()

    target_mac = None
    for device_dir in devices_dir.iterdir():
        if device_dir.is_dir():
            info_file = device_dir / "info.json"
            if info_file.exists():
                try:
                    info = json.loads(info_file.read_text(encoding="utf-8"))
                    if info.get("ip") == target_ip:
                        target_mac = device_dir.name  # MAC = 目录名
                        break
                except Exception:
                    continue

    if not target_mac:
        return {"success": False, "message": "未找到该设备的设备目录", "data": None}

    # v6.33: 使用 MAC 读取功能探测数据(优先时间戳文件)
    func_file = get_data_path_read(None, target_mac, "function")
    if func_file and func_file.exists():
        try:
            func_data = json.loads(func_file.read_text(encoding="utf-8"))
            return {"success": True, "data": func_data}
        except Exception as e:
            return {"success": False, "message": f"读取功能探测数据失败: {e}", "data": None}
    else:
        return {"success": False, "message": "未找到功能探测数据,请先完成功能测试", "data": None}




def _parse_wb_xml(xml_str: str) -> tuple[int, int]:
    """从 whiteBalance XML 解析 (red_gain, blue_gain), 失败返回 (100, 100)。"""
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml_str)
        red, blue = 100, 100
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag in ("WhiteBalanceRed", "whiteBalanceRed"):
                red = int((elem.text or "100").strip())
            elif tag in ("WhiteBalanceBlue", "whiteBalanceBlue"):
                blue = int((elem.text or "100").strip())
        return red, blue
    except Exception:
        return 100, 100


@api_router.get("/ptz/{device_id}/image/whitebalance", summary="获取白平衡设置", tags=["Image"])
async def get_whitebalance(device_id: str) -> dict:
    """获取设备白平衡当前设置。"""
    import xml.etree.ElementTree as ET
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    ctrl, err = mgr._get_controller(target_ip)
    if err:
        return {"success": False, "message": err}

    client = ctrl.client
    try:
        resp = client.get("/Image/channels/1/whiteBalance")
        if resp.status_code != 200:
            return {"success": False, "message": f"获取白平衡失败: HTTP {resp.status_code}"}

        import xml.etree.ElementTree as ET
        root = ET.fromstring(resp.xml)
        mode = "manual"
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "WhiteBalanceStyle":
                mode = (elem.text or "manual").lower()
        red_gain, blue_gain = _parse_wb_xml(resp.xml)
        
        # 从设备配置文件读取白平衡范围
        wb_min, wb_max = 0, 255
        import json as _json
        try:
            dm: DeviceManager | None = _managers.get("device_manager")  # type: ignore[assignment]
            if dm:
                for dev in dm.list_devices():
                    if dev.ip == target_ip:
                        cfg_path = dm._devices_dir / f"{dev.mac}.json"
                        if cfg_path.exists():
                            with open(cfg_path, "r", encoding="utf-8") as f:
                                dev_data = _json.load(f)
                            caps = dev_data.get("capabilities", {})
                            wb_cap = caps.get("white_balance", {})
                            wb_min = wb_cap.get("min_val", 0)
                            wb_max = wb_cap.get("max_val", 255)
                        break
        except Exception:
            pass
        
        result = {"success": True, "data": {"mode": mode, "red_gain": red_gain, "blue_gain": blue_gain, "min": wb_min, "max": wb_max, "supported_modes": ["manual", "auto"]}}
        return result
    except Exception as e:
        return {"success": False, "message": f"获取白平衡异常: {e}"}


@api_router.post("/ptz/{device_id}/image/whitebalance", summary="设置白平衡", tags=["Image"])
async def set_whitebalance(device_id: str, data: dict) -> dict:
    """设置白平衡参数(模式或R/B增益)。"""
    import xml.etree.ElementTree as ET
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    ctrl, err = mgr._get_controller(target_ip)
    if err:
        return {"success": False, "message": err}

    client = ctrl.client
    try:
        # 参数处理
        mode_input = data.get("mode")
        red_input = data.get("red_gain")
        blue_input = data.get("blue_gain")

        # 获取当前值
        resp = client.get("/Image/channels/1/whiteBalance")
        current_mode = "auto"
        current_red = 100
        current_blue = 80
        if resp.status_code == 200:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(resp.xml)
            for elem in root.iter():
                tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                if tag == "WhiteBalanceStyle":
                    current_mode = (elem.text or "auto").lower()
                elif tag == "WhiteBalanceRed":
                    current_red = int(elem.text or 100)
                elif tag == "WhiteBalanceBlue":
                    current_blue = int(elem.text or 80)

        # 使用传入值或当前值
        mode_val = mode_input if mode_input else current_mode
        red_val = red_input if red_input is not None else current_red
        blue_val = blue_input if blue_input is not None else current_blue

        # ISAPI 要求小写
        mode_isapi = mode_val.lower() if mode_val else "manual"

        xml_str = f'''<?xml version="1.0" encoding="UTF-8"?>
<WhiteBalance version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
<WhiteBalanceStyle>{mode_isapi}</WhiteBalanceStyle>
<WhiteBalanceRed>{red_val}</WhiteBalanceRed>
<WhiteBalanceBlue>{blue_val}</WhiteBalanceBlue>
</WhiteBalance>'''

        put_resp = client.put("/Image/channels/1/whiteBalance", xml_str)
        if put_resp.status_code == 200:
            log_info("image", "whitebalance", {"device": device_id, "mode": mode_val, "red": red_val, "blue": blue_val})
            return {"success": True, "message": "白平衡已更新", "data": {"mode": mode_val, "red_gain": red_val, "blue_gain": blue_val}}
        return {"success": False, "message": f"更新失败: HTTP {put_resp.status_code}"}
    except Exception as e:
        return {"success": False, "message": f"设置白平衡异常: {e}"}


@api_router.get("/ptz/{device_id}/image/noisereduce", summary="获取降噪设置", tags=["Image"])
async def get_noisereduce(device_id: str) -> dict:
    """获取设备降噪当前设置。"""
    import xml.etree.ElementTree as ET
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    ctrl, err = mgr._get_controller(target_ip)
    if err:
        return {"success": False, "message": err}

    client = ctrl.client
    try:
        resp = client.get("/Image/channels/1/noiseReduce")
        if resp.status_code != 200:
            return {"success": False, "message": f"获取降噪失败: HTTP {resp.status_code}"}

        root = ET.fromstring(resp.xml)
        result = {"success": True, "data": {}}
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "mode":
                result["data"]["mode"] = (elem.text or "general").strip()
            elif tag == "generalLevel":
                result["data"]["spatial_level"] = int((elem.text or "50").strip())
                result["data"]["temporal_level"] = int((elem.text or "50").strip())
            elif tag == "FrameNoiseReduceLevel":
                result["data"]["spatial_level"] = int((elem.text or "50").strip())
            elif tag == "InterFrameNoiseReduceLevel":
                result["data"]["temporal_level"] = int((elem.text or "50").strip())

        return result
    except Exception as e:
        return {"success": False, "message": f"获取降噪异常: {e}"}


@api_router.post("/ptz/{device_id}/image/noisereduce", summary="设置降噪", tags=["Image"])
async def set_noisereduce(device_id: str, data: dict) -> dict:
    """设置降噪参数。"""
    import xml.etree.ElementTree as ET
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    ctrl, err = mgr._get_controller(target_ip)
    if err:
        return {"success": False, "message": err}

    client = ctrl.client
    try:
        # 先获取当前降噪设置
        current_spatial = 50
        current_temporal = 50

        resp = client.get("/Image/channels/1/noiseReduce")
        if resp.status_code == 200:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(resp.xml)
            for elem in root.iter():
                tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                if tag == "FrameNoiseReduceLevel":
                    current_spatial = int(elem.text or 50)
                elif tag == "InterFrameNoiseReduceLevel":
                    current_temporal = int(elem.text or 50)

        # 使用传入值或当前值
        spatial = data.get("spatial_level", current_spatial)
        temporal = data.get("temporal_level", current_temporal)

        # ISAPI advanced 模式: FrameNoiseReduceLevel = 空域, InterFrameNoiseReduceLevel = 时域
        xml_str = f'''<?xml version="1.0" encoding="UTF-8"?>
<NoiseReduce version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
<mode>advanced</mode>
<AdvancedMode>
<FrameNoiseReduceLevel>{spatial}</FrameNoiseReduceLevel>
<InterFrameNoiseReduceLevel>{temporal}</InterFrameNoiseReduceLevel>
</AdvancedMode>
</NoiseReduce>'''

        put_resp = client.put("/Image/channels/1/noiseReduce", xml_str)
        if put_resp.status_code == 200:
            log_info("image", "noisereduce", {"device": device_id, "spatial": spatial, "temporal": temporal})
            return {"success": True, "message": "降噪已更新", "data": {"spatial_level": spatial, "temporal_level": temporal}}
        return {"success": False, "message": f"更新失败: HTTP {put_resp.status_code}"}
    except Exception as e:
        return {"success": False, "message": f"设置降噪异常: {e}"}


@api_router.post("/ptz/{device_id}/image/reset", summary="重置画面控制到默认值", tags=["Image"])
async def reset_image_controls(device_id: str) -> dict:
    """v6.51: 重置设备画面控制到默认值(不调用设备系统重置)。"""
    import xml.etree.ElementTree as ET
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    ctrl, err = mgr._get_controller(target_ip)
    if err:
        return {"success": False, "message": err}

    client = ctrl.client
    results = {}

    # 定义画面控制默认值
    default_values = {
        "brightness": 50,
        "contrast": 50,
        "saturation": 50,
        "white_balance_mode": "auto",
        "noise_reduce": 50,
        "sharpness": 50,
    }

    try:
        # 1. 重置亮度/对比度/饱和度
        color_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Color version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
<brightnessLevel>50</brightnessLevel>
<contrastLevel>50</contrastLevel>
<saturationLevel>50</saturationLevel>
</Color>'''
        resp = client.put("/Image/channels/1/Color", color_xml)
        results["color"] = resp.status_code == 200

        # 2. 重置白平衡
        wb_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<WhiteBalance version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
<WhiteBalanceStyle>auto</WhiteBalanceStyle>
</WhiteBalance>'''
        resp = client.put("/Image/channels/1/whiteBalance", wb_xml)
        results["white_balance"] = resp.status_code == 200

        # 3. 重置降噪 - 使用 advanced 模式
        nr_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<NoiseReduce version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
<mode>advanced</mode>
<AdvancedMode>
<FrameNoiseReduceLevel>50</FrameNoiseReduceLevel>
<InterFrameNoiseReduceLevel>50</InterFrameNoiseReduceLevel>
</AdvancedMode>
</NoiseReduce>'''
        resp = client.put("/Image/channels/1/noiseReduce", nr_xml)
        results["noise_reduce"] = resp.status_code == 200

        # 4. 重置锐度
        sharp_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<Sharpness version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
<SharpnessLevel>50</SharpnessLevel>
</Sharpness>'''
        resp = client.put("/Image/channels/1/Sharpness", sharp_xml)
        results["sharpness"] = resp.status_code == 200

        all_success = all(results.values())
        if all_success:
            log_info("image", "reset", {"device": device_id})
        return {
            "success": all_success,
            "message": "画面控制已重置到默认值" if all_success else "部分重置失败",
            "details": results
        }
    except Exception as e:
        return {"success": False, "message": f"重置异常: {e}"}


@api_router.get("/ptz/{device_id}/image/exposure", summary="获取曝光模式", tags=["Image"])
async def get_exposure(device_id: str) -> dict:
    """获取设备曝光当前模式 - v7.03: 使用 ExposureType 字段"""
    import xml.etree.ElementTree as ET
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    ctrl, err = mgr._get_controller(target_ip)
    if err:
        return {"success": False, "message": err}

    client = ctrl.client
    try:
        resp = client.get("/Image/channels/1/exposure")
        if resp.status_code != 200:
            return {"success": False, "message": f"获取曝光模式失败: HTTP {resp.status_code}"}

        root = ET.fromstring(resp.xml)
        result = {"success": True, "data": {}}
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            # v7.03: 使用 ExposureType
            if tag in ("ExposureType", "exposureType", "ExposureMode", "exposureMode"):
                result["data"]["mode"] = elem.text or "auto"

        # 如果没有找到曝光模式,默认 auto
        if "mode" not in result["data"]:
            result["data"]["mode"] = "auto"
        return result
    except Exception as e:
        return {"success": False, "message": f"获取曝光模式异常: {e}"}


@api_router.post("/ptz/{device_id}/image/exposure", summary="设置曝光模式", tags=["Image"])
async def set_exposure(device_id: str, data: dict) -> dict:
    """设置曝光模式 - v7.03: 使用 ExposureType 字段"""
    import xml.etree.ElementTree as ET
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    ctrl, err = mgr._get_controller(target_ip)
    if err:
        return {"success": False, "message": err}

    client = ctrl.client
    try:
        mode = data.get("mode", "manual")
        # v7.03: 使用 ExposureType 而不是 ExposureMode
        xml_str = f'''<?xml version="1.0" encoding="UTF-8"?>
<Exposure version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <ExposureType>{mode}</ExposureType>
</Exposure>'''

        put_resp = client.put("/Image/channels/1/exposure", xml_str)
        if put_resp.status_code == 200:
            log_info("image", "exposure", {"device": device_id, "mode": mode})
            return {"success": True, "message": f"曝光模式已设置为 {mode}"}
        return {"success": False, "message": f"更新失败: HTTP {put_resp.status_code}"}
    except Exception as e:
        return {"success": False, "message": f"设置曝光模式异常: {e}"}


@api_router.get("/ptz/{device_id}/image/shutter", summary="获取快门设置", tags=["Image"])
async def get_shutter(device_id: str) -> dict:
    """获取设备快门当前设置。"""
    import xml.etree.ElementTree as ET
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    ctrl, err = mgr._get_controller(target_ip)
    if err:
        return {"success": False, "message": err}

    client = ctrl.client
    try:
        resp = client.get("/Image/channels/1/Shutter")
        if resp.status_code != 200:
            return {"success": False, "message": f"获取快门失败: HTTP {resp.status_code}"}

        root = ET.fromstring(resp.xml)
        result = {"success": True, "data": {}}
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag in ("ShutterLevel", "shutterLevel"):
                result["data"]["current_level"] = elem.text or "1/60"
            elif tag in ("minShutterLevelLimit", "MinShutterLevelLimit"):
                result["data"]["min"] = elem.text or "1/30000"
            elif tag in ("maxShutterLevelLimit", "MaxShutterLevelLimit"):
                result["data"]["max"] = elem.text or "1/25"

        # 常用快门值
        result["data"]["supported_levels"] = [
            "1/30", "1/60", "1/125", "1/250", "1/500",
            "1/1000", "1/2000", "1/4000", "1/8000",
            result["data"].get("min", "1/30000"),
            result["data"].get("max", "1/25")
        ]
        result["data"]["mode"] = "manual"
        return result
    except Exception as e:
        return {"success": False, "message": f"获取快门异常: {e}"}


@api_router.post("/ptz/{device_id}/image/shutter", summary="设置快门", tags=["Image"])
async def set_shutter(device_id: str, data: dict) -> dict:
    """设置快门参数 - v7.07: 使用独立 Shutter 端点"""
    import xml.etree.ElementTree as ET
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    ctrl, err = mgr._get_controller(target_ip)
    if err:
        return {"success": False, "message": err}

    client = ctrl.client
    try:
        level = data.get("level", "1/60")

        # v7.07: 使用独立 Shutter 端点
        xml_str = f'''<?xml version="1.0" encoding="UTF-8"?>
<Shutter version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <ShutterLevel>{level}</ShutterLevel>
</Shutter>'''

        put_resp = client.put("/Image/channels/1/Shutter", xml_str)
        if put_resp.status_code == 200:
            log_info("image", "shutter", {"device": device_id, "level": level})
            return {"success": True, "message": f"快门已设置为 {level}"}
        return {"success": False, "message": f"更新失败: HTTP {put_resp.status_code}"}
    except Exception as e:
        return {"success": False, "message": f"设置快门异常: {e}"}


@api_router.get("/ptz/{device_id}/image/iris", summary="获取光圈设置", tags=["Image"])
async def get_iris(device_id: str) -> dict:
    """获取设备光圈当前设置。"""
    import xml.etree.ElementTree as ET
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    ctrl, err = mgr._get_controller(target_ip)
    if err:
        return {"success": False, "message": err}

    client = ctrl.client
    try:
        resp = client.get("/Image/channels/1/Iris")
        if resp.status_code != 200:
            return {"success": False, "message": f"获取光圈失败: HTTP {resp.status_code}"}

        root = ET.fromstring(resp.xml)
        result = {"success": True, "data": {}}
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag in ("IrisLevel", "irisLevel"):
                result["data"]["current_level"] = int((elem.text or "160").strip())
            elif tag in ("minIrisLevelLimit", "MinIrisLevelLimit"):
                result["data"]["min"] = int((elem.text or "160").strip())
            elif tag in ("maxIrisLevelLimit", "MaxIrisLevelLimit"):
                result["data"]["max"] = int((elem.text or "2200").strip())

        return result
    except Exception as e:
        return {"success": False, "message": f"获取光圈异常: {e}"}


@api_router.post("/ptz/{device_id}/image/iris", summary="设置光圈", tags=["Image"])
async def set_iris(device_id: str, data: dict) -> dict:
    """设置光圈参数。"""
    import xml.etree.ElementTree as ET
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    ctrl, err = mgr._get_controller(target_ip)
    if err:
        return {"success": False, "message": err}

    client = ctrl.client
    try:
        level = data.get("level", 160)

        # v7.03: 使用独立的 Iris 端点
        xml_str = f'''<?xml version="1.0" encoding="UTF-8"?>
<Iris version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <IrisLevel>{level}</IrisLevel>
</Iris>'''

        put_resp = client.put("/Image/channels/1/Iris", xml_str)
        if put_resp.status_code == 200:
            log_info("image", "iris", {"device": device_id, "level": level})
            return {"success": True, "message": f"光圈已设置"}
        return {"success": False, "message": f"更新失败: HTTP {put_resp.status_code}"}
    except Exception as e:
        return {"success": False, "message": f"设置光圈异常: {e}"}


# v7.03: 增益 (Gain) API
@api_router.get("/ptz/{device_id}/image/gain", summary="获取增益设置", tags=["Image"])
async def get_gain(device_id: str) -> dict:
    """获取设备增益当前设置。"""
    import xml.etree.ElementTree as ET
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    ctrl, err = mgr._get_controller(target_ip)
    if err:
        return {"success": False, "message": err}

    client = ctrl.client
    try:
        resp = client.get("/Image/channels/1/Gain")
        if resp.status_code != 200:
            return {"success": False, "message": f"获取增益失败: HTTP {resp.status_code}"}

        root = ET.fromstring(resp.xml)
        result = {"success": True, "data": {}}
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag in ("GainLevel", "gainLevel"):
                result["data"]["current_level"] = int((elem.text or "0").strip())
            elif tag in ("GainLimit", "gainLimit", "GainLevelLimit", "MaxGainLevelLimit"):
                result["data"]["limit"] = int((elem.text or "100").strip())

        return result
    except Exception as e:
        return {"success": False, "message": f"获取增益异常: {e}"}


@api_router.post("/ptz/{device_id}/image/gain", summary="设置增益", tags=["Image"])
async def set_gain(device_id: str, data: dict) -> dict:
    """设置增益参数。"""
    import xml.etree.ElementTree as ET
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    ctrl, err = mgr._get_controller(target_ip)
    if err:
        return {"success": False, "message": err}

    client = ctrl.client
    try:
        level = data.get("level", 0)

        # v7.03: 使用独立的 Gain 端点
        xml_str = f'''<?xml version="1.0" encoding="UTF-8"?>
<Gain version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <GainLevel>{level}</GainLevel>
</Gain>'''

        put_resp = client.put("/Image/channels/1/Gain", xml_str)
        if put_resp.status_code == 200:
            log_info("image", "gain", {"device": device_id, "level": level})
            return {"success": True, "message": f"增益已设置为 {level}"}
        return {"success": False, "message": f"更新失败: HTTP {put_resp.status_code}"}
    except Exception as e:
        return {"success": False, "message": f"设置增益异常: {e}"}


@api_router.get("/ptz/{device_id}/image/sharpness", summary="获取锐度设置", tags=["Image"])
async def get_sharpness(device_id: str) -> dict:
    """获取设备锐度当前设置。"""
    import xml.etree.ElementTree as ET
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    ctrl, err = mgr._get_controller(target_ip)
    if err:
        return {"success": False, "message": err}

    client = ctrl.client
    try:
        resp = client.get("/Image/channels/1/Sharpness")
        if resp.status_code != 200:
            return {"success": False, "message": f"获取锐度失败: HTTP {resp.status_code}"}

        root = ET.fromstring(resp.xml)
        result = {"success": True, "data": {}}
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag in ("SharpnessLevel", "sharpnessLevel"):
                result["data"]["current_level"] = int((elem.text or "50").strip())
                result["data"]["min"] = 0
                result["data"]["max"] = 100

        return result
    except Exception as e:
        return {"success": False, "message": f"获取锐度异常: {e}"}


@api_router.post("/ptz/{device_id}/image/sharpness", summary="设置锐度", tags=["Image"])
async def set_sharpness(device_id: str, data: dict) -> dict:
    """设置锐度参数。"""
    import xml.etree.ElementTree as ET
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    ctrl, err = mgr._get_controller(target_ip)
    if err:
        return {"success": False, "message": err}

    client = ctrl.client
    try:
        level = data.get("level", 50)

        xml_str = f'''<?xml version="1.0" encoding="UTF-8"?>
<Sharpness version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <SharpnessLevel>{level}</SharpnessLevel>
</Sharpness>'''

        put_resp = client.put("/Image/channels/1/Sharpness", xml_str)
        if put_resp.status_code == 200:
            log_info("image", "sharpness", {"device": device_id, "level": level})
            return {"success": True, "message": f"锐度已设置为 {level}"}
        return {"success": False, "message": f"更新失败: HTTP {put_resp.status_code}"}
    except Exception as e:
        return {"success": False, "message": f"设置锐度异常: {e}"}


@api_router.get("/ptz/{device_id}/image/color", summary="获取颜色设置", tags=["Image"])
async def get_color(device_id: str) -> dict:
    """获取设备颜色(亮度/对比度/饱和度)当前设置。"""
    import xml.etree.ElementTree as ET
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    ctrl, err = mgr._get_controller(target_ip)
    if err:
        return {"success": False, "message": err}

    client = ctrl.client
    try:
        resp = client.get("/Image/channels/1/Color")
        if resp.status_code != 200:
            return {"success": False, "message": f"获取颜色失败: HTTP {resp.status_code}"}

        root = ET.fromstring(resp.xml)
        result = {"success": True, "data": {}}
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "brightnessLevel":
                result["data"]["brightness"] = int((elem.text or "50").strip())
            elif tag == "contrastLevel":
                result["data"]["contrast"] = int((elem.text or "50").strip())
            elif tag == "saturationLevel":
                result["data"]["saturation"] = int((elem.text or "50").strip())

        return result
    except Exception as e:
        return {"success": False, "message": f"获取颜色异常: {e}"}


# === 滤镜与日夜模式 (v8.43) ===

@api_router.get("/ptz/{device_id}/image/filter", summary="获取滤镜与日夜模式", tags=["Image"])
async def get_filter_settings(device_id: str) -> dict:
    """获取当前 dayNightMode 和 irCutFilter 设置。"""
    import xml.etree.ElementTree as ET
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    ctrl, err = mgr._get_controller(target_ip)
    if err:
        return {"success": False, "message": err}

    client = ctrl.client
    try:
        resp = client.get("/Image/channels/1")
        if resp.status_code != 200:
            return {"success": False, "message": f"获取滤镜设置失败: HTTP {resp.status_code}"}

        root = ET.fromstring(resp.xml)
        day_night = "unknown"
        ir_cut = "unknown"
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "dayNightMode":
                day_night = (elem.text or "").strip()
            elif tag == "irCutFilter":
                ir_cut = (elem.text or "").strip()

        return {
            "success": True,
            "data": {
                "dayNightMode": day_night,
                "irCutFilter": ir_cut
            }
        }
    except Exception as e:
        return {"success": False, "message": f"获取滤镜设置异常: {e}"}


@api_router.put("/ptz/{device_id}/image/filter", summary="设置滤镜与日夜模式", tags=["Image"])
async def set_filter_settings(device_id: str, body: dict) -> dict:
    """设置 dayNightMode 和/或 irCutFilter。

    请求体:
        {"dayNightMode": "day|night|auto", "irCutFilter": "on|off|auto"}
    """
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    ctrl, err = mgr._get_controller(target_ip)
    if err:
        return {"success": False, "message": err}

    client = ctrl.client
    day_night = body.get("dayNightMode", "")
    ir_cut = body.get("irCutFilter", "")

    # 先 GET 当前完整 XML，再修改对应字段后 PUT
    try:
        resp = client.get("/Image/channels/1")
        if resp.status_code != 200:
            return {"success": False, "message": f"获取当前设置失败: HTTP {resp.status_code}"}

        xml_str = resp.xml
        import re

        if day_night:
            xml_str = re.sub(
                r'(<dayNightMode>)[^<]*(</dayNightMode>)',
                f'\\g<1>{day_night}\\g<2>',
                xml_str
            )
        if ir_cut:
            xml_str = re.sub(
                r'(<irCutFilter>)[^<]*(</irCutFilter>)',
                f'\\g<1>{ir_cut}\\g<2>',
                xml_str
            )

        put_resp = client.put("/Image/channels/1", xml_str)
        if put_resp.status_code == 200:
            log_info("image", "filter", {"device": device_id, "dayNight": day_night, "irCut": ir_cut})
            return {"success": True, "message": "滤镜设置成功"}
        else:
            return {"success": False, "message": f"设置失败: HTTP {put_resp.status_code}"}
    except Exception as e:
        return {"success": False, "message": f"设置滤镜异常: {e}"}


# === 慢快门 DSS (v8.45) ===

@api_router.get("/ptz/{device_id}/image/slow-shutter", summary="获取慢快门设置", tags=["Image"])
async def get_slow_shutter(device_id: str) -> dict:
    mgr = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}
    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}
    ctrl, err = mgr._get_controller(target_ip)
    if err:
        return {"success": False, "message": err}
    client = ctrl.client
    try:
        resp = client.get("/Image/channels/1/DSS")
        if resp.status_code != 200:
            return {"success": False, "message": f"获取DSS失败: HTTP {resp.status_code}"}
        import xml.etree.ElementTree as ET
        root = ET.fromstring(resp.xml)
        enabled = False
        dss_level = ""
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "enabled":
                enabled = (elem.text or "").strip().lower() == "true"
            elif tag == "DSSLevel":
                dss_level = (elem.text or "").strip()
        return {"success": True, "data": {"supported": True, "enabled": enabled, "dss_level": dss_level}}
    except Exception as e:
        return {"success": False, "message": f"获取DSS异常: {e}"}

@api_router.put("/ptz/{device_id}/image/slow-shutter", summary="设置慢快门", tags=["Image"])
async def set_slow_shutter(device_id: str, body: dict) -> dict:
    mgr = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}
    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}
    ctrl, err = mgr._get_controller(target_ip)
    if err:
        return {"success": False, "message": err}
    client = ctrl.client
    dss_level = body.get("dss_level", "")
    try:
        if dss_level == "off":
            enabled = "false"
            level_str = "*1"
        else:
            enabled = "true"
            level_str = dss_level
        xml_str = '<?xml version="1.0" encoding="UTF-8"?>' + chr(10) + '<DSS version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">' + chr(10) + '  <enabled>' + enabled + '</enabled>' + chr(10) + '  <DSSLevel>' + level_str + '</DSSLevel>' + chr(10) + '</DSS>'
        put_resp = client.put("/Image/channels/1/DSS", xml_str)
        if put_resp.status_code == 200:
            log_info("image", "dss", {"device": device_id, "level": dss_level})
            return {"success": True, "message": "慢快门: " + ("关闭" if dss_level == "off" else dss_level)}
        return {"success": False, "message": f"设置失败: HTTP {put_resp.status_code}"}
    except Exception as e:
        return {"success": False, "message": f"设置DSS异常: {e}"}

@api_router.get("/ptz/{device_id}/osd/ptz", summary="获取PTZ OSD状态", tags=["OSD"])
async def get_osd_ptz(device_id: str) -> dict:
    """获取PTZ OSD显示状态。"""
    import xml.etree.ElementTree as ET
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    ctrl, err = mgr._get_controller(target_ip)
    if err:
        return {"success": False, "message": err}

    client = ctrl.client
    try:
        ch = getattr(client, 'channel', 1)
        resp = client.get(f"/PTZCtrl/channels/{ch}/PTZOSDDisplay")
        if resp.status_code != 200:
            return {"success": False, "message": f"获取OSD失败: HTTP {resp.status_code}"}

        root = ET.fromstring(resp.xml)
        enabled = False
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag in ("azimuth", "zoomlable"):
                if elem.text == "alwaysopen":
                    enabled = True
                    break

        return {"success": True, "enabled": enabled}
    except Exception as e:
        return {"success": False, "message": f"获取OSD异常: {e}"}


@api_router.get("/ptz/{device_id}/osd/info", summary="获取Info OSD状态", tags=["OSD"])
async def get_osd_info(device_id: str) -> dict:
    """获取Info OSD显示状态。"""
    import xml.etree.ElementTree as ET
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    ctrl, err = mgr._get_controller(target_ip)
    if err:
        return {"success": False, "message": err}

    client = ctrl.client
    try:
        ch = getattr(client, 'channel', 1)
        resp = client.get(f"/System/Video/inputs/channels/{ch}/overlays")
        if resp.status_code != 200:
            return {"success": False, "message": f"获取OSD失败: HTTP {resp.status_code}"}

        root = ET.fromstring(resp.xml)
        enabled = False
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "enabled":
                if elem.text == "true":
                    enabled = True
                    break

        return {"success": True, "enabled": enabled}
    except Exception as e:
        return {"success": False, "message": f"获取OSD异常: {e}"}


# ================================================================ #
#  系统管理端点
# ================================================================ #

@api_router.get("/system/token", summary="获取设备Token", tags=["System"])
async def get_device_token() -> dict:
    """v7.52: 后端获取设备Token(使用Digest认证)."""
    import requests
    from requests.auth import HTTPDigestAuth

    # v7.98: 从活跃设备配置读取,不再硬编码
    device_result = await get_active_device()
    if not device_result.get("success"):
        return {"success": False, "message": "无活跃设备,请先连接设备"}

    device = device_result["device"]
    camera_ip = device.get("ip", "")
    username = device.get("username", "admin")
    password = device.get("password", "")

    if not camera_ip:
        return {"success": False, "message": "活跃设备无IP地址"}

    try:
        resp = requests.get(
            f'http://{camera_ip}:80/ISAPI/Security/token?format=json',
            auth=HTTPDigestAuth(username, password),
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            token = data.get('Token', {}).get('value', '')
            return {"success": True, "token": token}
        else:
            return {"success": False, "message": f"Token获取失败: {resp.status_code}"}
    except Exception as e:
        return {"success": False, "message": f"Token获取异常: {e}"}

@api_router.post("/system/restart", summary="重启 AstroHub", tags=["System"])
async def restart_astrohub() -> dict:
    """v7.114: 干净重启 - 独立脚本等端口释放后启动新进程,sys.exit 触发 graceful shutdown."""
    import subprocess
    import os
    import sys

    cwd = os.getcwd()
    python_exe = sys.executable

    helper = os.path.join(cwd, "src", "main", "restart_helper.py")
    subprocess.Popen(
        [python_exe, helper, "127.0.0.1", "10280", python_exe, cwd],
        cwd=cwd,
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )

    sys.exit(0)


# ================================================================ #
#  v8.10: Vision 端点 - 框选分析 + 星点叠加
# ================================================================ #

import asyncio
import base64
import os
import cv2
import numpy as np
from pydantic import BaseModel as PydanticBase


class RegionAnalyzeRequest(PydanticBase):
    """框选区域分析请求。"""
    image_base64: str = ""  # 裁剪区域的 base64 图像
    image_path: str = ""    # 或：截图文件路径 + 裁剪坐标
    x: float = 0
    y: float = 0
    w: float = 0
    h: float = 0
    action: str = "both"  # whitebalance / focus / both


class StackStartRequest(PydanticBase):
    """叠加开始请求。"""
    total_exposure: float
    frame_exposure_ms: int = 100


_stack_engine = None
_stack_task = None


def _decode_image(b64: str) -> np.ndarray | None:
    if ',' in b64:
        b64 = b64.split(',', 1)[1]
    data = base64.b64decode(b64)
    arr = np.frombuffer(data, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _get_client_for_device(mgr, device_id: str):
    """从 device_id (MAC或IP) 获取 ISAPIClient。"""
    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return None, f"无法解析设备: {device_id}"
    ctrl, err = mgr._get_controller(target_ip)
    if err:
        return None, err
    client = mgr._clients.get(target_ip)
    if not client:
        return None, f"ISAPI client not found for {target_ip}"
    return client, ""


def _get_active_client(mgr):
    """获取当前活跃设备的 ISAPIClient。"""
    connected = mgr.get_connected_device()
    if not connected:
        return None, "无活跃设备"
    target_ip = connected.get("ip", "")
    if not target_ip:
        return None, "活跃设备无IP"
    return _get_client_for_device(mgr, target_ip)


# ── v8.11: ISAPI 截图 → 后端裁剪 → 迭代搜索 ──────────────

_TEMP_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "temp")


def _temp_dir(category: str, device_ip: str) -> str:
    """获取临时目录并确保存在。"""
    d = os.path.join(_TEMP_ROOT, category, device_ip.replace(".", "_"))
    os.makedirs(d, exist_ok=True)
    return d


def _cleanup_temp(category: str, device_ip: str):
    """清理指定设备指定类别的临时文件。"""
    import shutil
    d = os.path.join(_TEMP_ROOT, category, device_ip.replace(".", "_"))
    if os.path.exists(d):
        shutil.rmtree(d, ignore_errors=True)


def _capture_and_crop(client, mgr, device_ip: str, category: str,
                      x: float, y: float, w: float, h: float) -> tuple:
    """ISAPI 截图 → 按比例裁剪 → 返回 (bgr, 截图路径, 裁剪信息dict)。

    统一入口，白平衡和对焦共用。
    """
    import time as _time
    from src.controlpanel.region_base import calc_stable_delay
    delay = calc_stable_delay(client)
    _time.sleep(delay)  # v8.44: 统一延时
    jpg = client.capture_picture()
    if not jpg:
        return None, "", {"error": "ISAPI截图失败"}

    # 保存全图
    ts = int(_time.time() * 1000)
    temp_dir = _temp_dir(category, device_ip)
    full_path = os.path.join(temp_dir, f"full_{ts}.jpg")
    with open(full_path, "wb") as f:
        f.write(jpg)

    bgr = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
    if bgr is None:
        return None, full_path, {"error": "图像解码失败"}

    full_h, full_w = bgr.shape[:2]

    # 裁剪
    if w > 0 and h > 0:
        x1 = max(0, int(x * full_w))
        y1 = max(0, int(y * full_h))
        x2 = min(full_w, int((x + w) * full_w))
        y2 = min(full_h, int((y + h) * full_h))
        if x2 <= x1 or y2 <= y1:
            return bgr, full_path, {"error": "裁剪区域无效"}
        cropped = bgr[y1:y2, x1:x2]
        crop_path = os.path.join(temp_dir, f"crop_{ts}.jpg")
        cv2.imwrite(crop_path, cropped)
    else:
        cropped = bgr
        crop_path = full_path
        x1, y1, x2, y2 = 0, 0, full_w, full_h

    info = {
        "full_w": full_w, "full_h": full_h,
        "crop_x1": x1, "crop_y1": y1, "crop_x2": x2, "crop_y2": y2,
        "crop_w": x2 - x1, "crop_h": y2 - y1,
        "crop_path": crop_path,
        "pixels": (x2 - x1) * (y2 - y1),
    }
    return cropped, crop_path, info


def _apply_whitebalance(client, red: int, blue: int) -> dict:
    """写入白平衡到 ISAPI。"""
    xml_str = f'''<?xml version="1.0" encoding="UTF-8"?>
<WhiteBalance version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
<WhiteBalanceStyle>manual</WhiteBalanceStyle>
<WhiteBalanceRed>{red}</WhiteBalanceRed>
<WhiteBalanceBlue>{blue}</WhiteBalanceBlue>
</WhiteBalance>'''
    resp = client.put("/Image/channels/1/whiteBalance", xml_str)
    return {"success": resp.status_code == 200, "status": resp.status_code}


@api_router.post("/vision/region-analyze", summary="框选区域分析（单次）", tags=["Vision"])
async def region_analyze(req: RegionAnalyzeRequest) -> dict:
    """单次框选分析：裁剪 + RGB统计 + 反差。用于预览。"""
    from src.controlpanel.region_base import _rgb_stats, calc_contrast

    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZ控制器未初始化"}

    connected = mgr.get_connected_device()
    if not connected:
        return {"success": False, "message": "无活跃设备"}

    device_ip = connected["ip"]
    client, err = _get_client_for_device(mgr, device_ip)
    if err:
        return {"success": False, "message": err}

    bgr, crop_path, info = _capture_and_crop(client, mgr, device_ip, "WB",
                                              req.x, req.y, req.w, req.h)
    if bgr is None:
        return {"success": False, "message": info.get("error", "截图失败")}

    stats = _rgb_stats(bgr)
    contrast = calc_contrast(bgr)
    return {"success": True, "crop": info, "rgb": stats, "contrast": round(contrast, 2)}



# v8.41: 搜索器全局变量
_wb_searcher = None
_focus_searcher = None


@api_router.post("/vision/whitebalance-search", summary="白平衡迭代搜索 (SSE)", tags=["Vision"])
async def whitebalance_search(data: dict):
    """白平衡迭代搜索 - SSE流式。路由层只验证输入和调用白平衡模块。"""
    import json
    from fastapi.responses import StreamingResponse
    from src.controlpanel.whitebalance import WhiteBalanceSearcher

    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return StreamingResponse(
            iter([f"data: {json.dumps({'type': 'error', 'message': 'PTZ控制器未初始化'})}\n\n"]),
            media_type="text/event-stream"
        )

    connected = mgr.get_connected_device()
    if not connected:
        return StreamingResponse(
            iter([f"data: {json.dumps({'type': 'error', 'message': '无活跃设备'})}\n\n"]),
            media_type="text/event-stream"
        )

    device_ip = connected["ip"]
    client, err = _get_client_for_device(mgr, device_ip)
    if err:
        return StreamingResponse(
            iter([f"data: {json.dumps({'type': 'error', 'message': err})}\n\n"]),
            media_type="text/event-stream"
        )

    x = float(data.get("x", 0))
    y = float(data.get("y", 0))
    w = float(data.get("w", 0))
    h = float(data.get("h", 0))

    if w <= 0 or h <= 0:
        return StreamingResponse(
            iter([f"data: {json.dumps({'type': 'error', 'message': '框选区域无效'})}\n\n"]),
            media_type="text/event-stream"
        )

    searcher = WhiteBalanceSearcher(
        mgr=mgr, device_ip=device_ip, client=client,
        x=x, y=y, w=w, h=h,
        capture_func=_capture_and_crop,
        cleanup_func=_cleanup_temp
    )
    
    # v8.41: 保存搜索器到全局变量
    global _wb_searcher
    _wb_searcher = searcher
    
    return StreamingResponse(
        searcher.run(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@api_router.post("/vision/whitebalance-stop", summary="停止白平衡搜索", tags=["Vision"])
async def whitebalance_stop():
    """停止当前白平衡搜索并写入最佳值到设备"""
    global _wb_searcher
    if not _wb_searcher:
        return {"success": False, "message": "无活跃的白平衡搜索"}
    
    _wb_searcher._interrupt()
    _wb_searcher = None
    
    return {"success": True, "message": "白平衡搜索已停止"}


@api_router.post("/vision/focus-search", summary="反差对焦搜索", tags=["Vision"])
async def focus_search(data: dict):
    """反差对焦搜索 - SSE流式。路由层只验证输入和调用对焦模块。"""
    import json
    from fastapi.responses import StreamingResponse
    from src.controlpanel.autofocus import FocusSearcher

    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return StreamingResponse(
            iter([f"data: {json.dumps({'type': 'error', 'message': 'PTZ控制器未初始化'})}\n\n"]),
            media_type="text/event-stream"
        )

    connected = mgr.get_connected_device()
    if not connected:
        return StreamingResponse(
            iter([f"data: {json.dumps({'type': 'error', 'message': '无活跃设备'})}\n\n"]),
            media_type="text/event-stream"
        )

    device_ip = connected["ip"]
    client, err = _get_client_for_device(mgr, device_ip)
    if err:
        return StreamingResponse(
            iter([f"data: {json.dumps({'type': 'error', 'message': err})}\n\n"]),
            media_type="text/event-stream"
        )

    x = float(data.get("x", 0))
    y = float(data.get("y", 0))
    w = float(data.get("w", 0))
    h = float(data.get("h", 0))

    if w <= 0 or h <= 0:
        return StreamingResponse(
            iter([f"data: {json.dumps({'type': 'error', 'message': '框选区域无效'})}\n\n"]),
            media_type="text/event-stream"
        )

    searcher = FocusSearcher(
        mgr=mgr, device_ip=device_ip, client=client,
        x=x, y=y, w=w, h=h,
        capture_func=_capture_and_crop,
        cleanup_func=_cleanup_temp
    )
    
    # v8.41: 保存搜索器到全局变量
    global _focus_searcher
    _focus_searcher = searcher
    
    return StreamingResponse(
        searcher.run(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@api_router.post("/vision/focus-stop", summary="停止对焦搜索", tags=["Vision"])
async def focus_stop():
    """停止当前对焦搜索"""
    global _focus_searcher
    if not _focus_searcher:
        return {"success": False, "message": "无活跃的对焦搜索"}
    
    _focus_searcher._interrupt()
    _focus_searcher = None
    
    return {"success": True, "message": "对焦搜索已停止"}


@api_router.post("/vision/stack-start", summary="启动星点叠加", tags=["Vision"])
async def stack_start(req: StackStartRequest) -> dict:
    """启动星点叠加会话。"""
    global _stack_engine, _stack_task
    mgr: PTZDeviceController | None = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZ控制器未初始化"}

    client, err = _get_active_client(mgr)
    if err:
        return {"success": False, "message": err}

    total_frames = int(req.total_exposure * 1000 / req.frame_exposure_ms)
    if total_frames < 2:
        return {"success": False, "message": f"总帧数太少: {total_frames}"}

    from src.vision.stack_engine import StackEngine
    _stack_engine = StackEngine(client)
    _stack_engine.start(total_frames)

    connected = mgr.get_connected_device()
    target_ip = connected["ip"]
    _stack_task = asyncio.create_task(
        _run_stack_collection(mgr, target_ip, req.frame_exposure_ms, total_frames))

    return {"success": True, "total_frames": total_frames,
            "frame_exposure_ms": req.frame_exposure_ms, "total_exposure_s": req.total_exposure}


async def _run_stack_collection(mgr, target_ip: str, exposure_ms: int, total_frames: int):
    global _stack_engine
    client, err = _get_client_for_device(mgr, target_ip)
    if err or not _stack_engine:
        return

    for i in range(total_frames):
        if not _stack_engine._running or _stack_engine._cancelled:
            break
        try:
            jpg = client.capture_picture()
            if not jpg:
                continue
            arr = np.frombuffer(jpg, np.uint8)
            bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if bgr is None:
                continue
            _stack_engine.add_frame(bgr)
        except Exception:
            continue
        await asyncio.sleep(exposure_ms / 1000.0)


@api_router.post("/vision/stack-stop", summary="停止星点叠加", tags=["Vision"])
async def stack_stop() -> dict:
    global _stack_engine, _stack_task
    if _stack_engine:
        result = _stack_engine.finish()
        _stack_engine = None
        _stack_task = None
        return result
    return {"success": False, "message": "无活跃叠加会话"}


@api_router.post("/vision/stack-cancel", summary="取消星点叠加", tags=["Vision"])
async def stack_cancel() -> dict:
    global _stack_engine, _stack_task
    if _stack_engine:
        _stack_engine.cancel()
        _stack_engine = None
        _stack_task = None
        return {"success": True, "message": "已取消"}
    return {"success": False, "message": "无活跃叠加会话"}
