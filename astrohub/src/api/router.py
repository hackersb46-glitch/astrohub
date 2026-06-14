"""
AstroHub v2.0 - 统一路由聚合

整合 M1-M11 所有模块路由到 /api/v1/ 下:
- /api/v1/health            - 全局健康检查
- /api/v1/discovery/sadp    - SADP 设备发现
- /api/v1/devices/*         - 设备管理（真实）
- /api/v1/ptz/*             - PTZ 控制（真实）
- /api/v1/streams/*         - 流服务
- /api/v1/calibration/*     - 校准
- /api/v1/ascom/*           - ASCOM 设备
- /api/v1/settings          - 系统设置

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel
from fastapi import APIRouter, FastAPI, Query
from fastapi.responses import JSONResponse

# v6.40: 操作日志
from src.operation_logger import log_api, log_web, log_error, log_info

# ================================================================ #
#  核心模块导入
# ================================================================ #

from src.core.ws_manager import WebSocketManager
from src.core.ptz_manager import PTZManager
from src.core.device_manager import DeviceManager
from src.core.stream_manager import StreamManager
from src.core.calibration_manager import CalibrationManager
from src.core.auth import AuthManager
from src.core.ascom_manager import ASCOMManager
from src.core.orchestrator import Orchestrator
from src.core.health_monitor import HealthMonitor


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
    """系统信息请求（可选的绑定 ip）。"""
    nic_index: int | None = None

class PTZMoveRequest(BaseModel):
    """PTZ 移动请求。
    
    speed: 1-7 档位，默认 4 档
    档位映射: 1→14, 2→28, 3→43, 4→57, 5→71, 6→86, 7→100
    """
    direction: str
    speed: int = 4  # 默认 4 档

class PTZAbsoluteRequest(BaseModel):
    """PTZ 绝对移动请求。
    
    speed: 1-7 档位，默认 4 档
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


def operation_log(action: str, details: str) -> None:
    """追加操作到日志列表（环形缓冲区，最多 MAX_LOG_ENTRIES 条）。"""
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


def set_managers(**kwargs: Any) -> None:
    """注入所有管理器实例。"""
    _managers.update(kwargs)


def _resolve_device_id_to_ip(mgr: "PTZManager", device_id: str) -> str | None:
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
        # 是 MAC 地址，尝试从发现缓存中查找
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
        return None
    # 看起来像 IP 地址，直接返回
    return device_id


# ================================================================ #
#  健康检查端点
# ================================================================ #


@health_router.get("/health", summary="全局健康检查")
async def global_health() -> dict:
    """全局健康检查端点 (GET /api/v1/health)。"""
    module_keys = (
        "ptz_manager",
        "device_manager",
        "stream_manager",
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


@api_router.get("/localhost", summary="本机信息", tags=["System"])
async def get_localhost_info() -> dict:
    """获取本机系统信息 (hostname, CPU, RAM, GPU, IP, gateway).
    
    首次调用时会自动收集并保存到 data/reports/localhost.json
    """
    from src.advanced.startup import get_localhost_info, run_startup, check_localhost_exists
    
    # 如果文件不存在，先收集
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
    
    BUG-003 修复: 直接使用 SADPManager，不依赖 PTZManager。
    """
    start = time.time()
    
    # 优先使用 PTZManager（如果已初始化）
    mgr: PTZManager | None = _managers.get("ptz_manager")  # type: ignore[assignment]
    if mgr:
        devices = mgr.discover_devices(bind_ip=bind_ip)
    else:
        # 直接使用 SADPManager 不依赖 PTZManager
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
                    "source": "sadp",
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
    """获取设备列表（MAC 去重合并 SADP 发现 + 手动存储）."""
    mgr: PTZManager | None = _managers.get("ptz_manager")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "data": [], "total": 0}

    def _normalize_mac(mac: str) -> str:
        """统一 MAC 为无分隔符小写格式 (aabbccddeeff).

        BUG-016 修复: 增强 MAC 格式校验，拒绝假 MAC 地址（如 IP 地址填入 MAC 字段）。
        """
        import re
        clean = mac.replace(":", "").replace("-", "").lower()
        # 验证: 必须是恰好12位十六进制字符
        if len(clean) != 12 or not re.match(r'^[0-9a-f]{12}$', clean):
            return ""
        return clean

    def _has_device_mac(dev: dict) -> bool:
        """判断设备是否有有效 MAC."""
        return bool(_normalize_mac(dev.get("mac", "") or ""))

    stored = mgr.list_stored_devices()
    discovered = mgr.get_discovered_devices()
    online_ips = mgr.list_controllers()

    # --- Pass 1: 存储设备按 MAC 建索引 ---
    keyed: dict[str, dict[str, Any]] = {}  # normalized_mac -> merged_record
    no_mac: list[dict[str, Any]] = []      # manual entry without MAC

    for dev in stored:
        mac_norm = _normalize_mac(dev.get("mac", "") or "")
        if mac_norm:
            keyed[mac_norm] = {
                "mac": mac_norm,
                "ip": dev.get("ip", ""),
                "name": dev.get("name", "") or dev.get("device_name", ""),  # 用户设置的名称
                "model": dev.get("model", ""),  # 设备型号
                "gateway": dev.get("gateway", ""),  # v6.01
                "subnet_mask": dev.get("subnet_mask", ""),  # v6.01
                "source": "manual",
                "online": False,  # updated later
                "activated": False,
                "has_credentials": True,
            }
        else:
            no_mac.append({
                "mac": "",
                "ip": dev.get("ip", ""),
                "name": dev.get("name", "") or dev.get("device_name", ""),
                "model": dev.get("model", ""),
                "source": "manual",
                "online": False,
                "activated": False,
                "has_credentials": True,
            })

    # --- Pass 2: 合并 SADP 发现设备 ---
    for sadp in discovered:
        sadp_mac = _normalize_mac(sadp.get("mac", "") or "")
        if sadp_mac and sadp_mac in keyed:
            # 匹配到存储设备 → 合并
            existing = keyed[sadp_mac]
            existing["ip"] = sadp.get("ip") or existing["ip"]
            existing["model"] = sadp.get("model") or existing["model"]
            # name: 优先保留用户设置的名称，否则用 SADP 发现的
            if not existing.get("name"):
                existing["name"] = sadp.get("device_name") or sadp.get("name", "")
            existing["activated"] = sadp.get("activated", False)
            existing["gateway"] = sadp.get("gateway", "")
            existing["subnet_mask"] = sadp.get("subnet_mask", "")
            existing["source"] = "merged"
        elif sadp_mac:
            # 新发现设备
            keyed[sadp_mac] = {
                "mac": sadp_mac,
                "ip": sadp.get("ip", ""),
                "name": sadp.get("device_name") or sadp.get("name", ""),
                "model": sadp.get("model", ""),
                "source": "sadp",
                "online": False,
                "activated": sadp.get("activated", False),
                "has_credentials": False,
            }

    # --- 构建最终列表 + 在线状态 ---
    all_devices: list[dict[str, Any]] = list(keyed.values()) + no_mac
    for dev in all_devices:
        ip = dev.get("ip", "")
        dev["online"] = ip in online_ips

    return {"success": True, "data": all_devices, "total": len(all_devices)}


@api_router.get("/devices/active", summary="获取上次连接的设备", tags=["Devices"])
async def get_active_device() -> dict:
    """v6.30: 获取上次连接的设备（用于快速连接）。"""
    from src.advanced.device_config import get_current_device
    
    device = get_current_device()
    if device is None:
        return {
            "success": False,
            "active": False,
            "device": None,
            "message": "无上次连接设备"
        }
    
    return {
        "success": True,
        "active": True,
        "device": device
    }


@api_router.post("/devices/active", summary="设置上次连接的设备", tags=["Devices"])
async def set_active_device(mac: str) -> dict:
    """v6.30: 设置上次连接的设备（用于快速连接）。"""
    from src.advanced.device_config import get_device_by_mac, load_config, save_config
    
    device = get_device_by_mac(mac)
    if device is None:
        return {"success": False, "message": f"设备不存在: {mac}"}
    
    config = load_config()
    config["current_device"] = mac
    save_config(config)
    
    return {
        "success": True,
        "message": f"上次连接设备已设置: {device.get('model', 'Unknown')} @ {device.get('ip')}",
        "device": device
    }


@api_router.post("/devices", summary="注册设备", tags=["Devices"])
async def register_device(req: AddDeviceRequest) -> dict:
    """手动添加设备（IP + 凭据）并自动设为活跃。"""
    from src.advanced.device_config import set_current_device
    
    mgr: PTZManager | None = _managers.get("ptz_manager")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

    mgr.save_credentials(
        ip=req.ip,
        username=req.username,
        password=req.password,
        port=req.port,
        mac=req.mac,
        model=req.model,
        name=req.name,
    )

    # 自动注册到 DeviceManager
    dm: DeviceManager | None = _managers.get("device_manager")  # type: ignore[assignment]
    if dm:
        dm.register_device(
            mac=req.mac or req.ip,
            ip=req.ip,
            name=req.name or f"Hikvision-{req.ip}",
            model=req.model or "Hikvision PTZ",
        )
    
    # 设为活跃设备
    if req.mac:
        set_current_device(req.mac, ip=req.ip, model=req.model, port=req.port)

    return {
        "success": True,
        "message": f"设备已保存并设为活跃: {req.ip}",
        "device": {
            "ip": req.ip,
            "port": req.port,
            "name": req.name,
            "model": req.model,
            "mac": req.mac,
        },
    }


@api_router.post("/devices/{device_id}/connect", summary="连接设备", tags=["Devices"])
async def connect_device(device_id: str, req: ConnectDeviceRequest | None = None) -> dict:
    """连接 PTZ 设备并认证。

    device_id 可以是 IP 地址或 MAC 地址。如果是 MAC，自动解析为 IP。
    使用 admin 作为默认用户名，密码必须由用户提供或已保存在配置中。
    
    BUG-014 修复: ISAPI 连接前 socket 预检，5 秒超时快速失败。
    """
    log_api("connect", {"mac": device_id})
    
    mgr: PTZManager | None = _managers.get("ptz_manager")  # type: ignore[assignment]
    if not mgr:
        log_error("connect", {"mac": device_id, "error": "PTZManager 未初始化"})
        return {"success": False, "message": "PTZManager 未初始化"}

    # 解析 device_id: 如果看起来像 MAC，从发现缓存中解析 IP
    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        log_error("connect", {"mac": device_id, "error": "无法解析设备标识"})
        return {"success": False, "message": f"无法解析设备标识: {device_id}，请提供 IP 地址或确保设备已通过 SADP 发现"}

    # 如果未提供凭据，尝试从存储获取
    if req is None:
        creds = mgr.get_credentials(target_ip)
        if not creds:
            log_error("connect", {"mac": device_id, "error": "设备未保存凭据"})
            return {"success": False, "message": "设备未保存凭据，请先提供用户名和密码"}
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
        # 更新 DeviceManager 状态（使用 device_id 保持前端一致）
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
    
    mgr: PTZManager | None = _managers.get("ptz_manager")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

    mgr.disconnect_device(device_id)

    dm: DeviceManager | None = _managers.get("device_manager")  # type: ignore[assignment]
    if dm:
        dm.update_status(device_id, "offline")

    log_info("disconnect", {"mac": device_id, "status": "success"})
    return {"success": True, "message": f"设备已断开: {device_id}"}


@api_router.delete("/devices/{device_id}", summary="删除设备", tags=["Devices"])
async def delete_device(device_id: str) -> dict:
    """删除设备。"""
    mgr: PTZManager | None = _managers.get("ptz_manager")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

    # 先断开
    mgr.disconnect_device(device_id)

    # 移除凭据
    removed = mgr.remove_credentials(device_id)

    dm: DeviceManager | None = _managers.get("device_manager")  # type: ignore[assignment]
    if dm:
        dm.unregister_device(device_id)

    return {
        "success": True,
        "message": f"设备已删除: {device_id}",
    }


@api_router.get("/devices/{device_id}/info", summary="设备详细信息", tags=["Devices"])
async def get_device_info(device_id: str) -> dict:
    """获取设备详细信息（通过 ISAPI）。"""
    mgr: PTZManager | None = _managers.get("ptz_manager")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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
    """修改设备网络配置（通过 SADP 协议）。"""
    mgr: PTZManager | None = _managers.get("ptz_manager")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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
    """通过 SADP DLL 修改设备 IP，含自动重试和扫描确认循环。"""
    mgr: PTZManager | None = _managers.get("ptz_manager")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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
    mgr: PTZManager | None = _managers.get("ptz_manager")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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
    - connected: 当前是否已连接（基于 active_device）
    - device: 上次连接的设备信息（基于 last_connected，用于快速连接）
    """
    import json
    from src.config_paths import REGISTRY_FILE
    
    mgr: PTZManager | None = _managers.get("ptz_manager")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化", "connected": False, "device": None}
    
    # v7.10: 获取上次连接的设备（用于快速连接）
    device = mgr.get_connected_device()
    
    # v7.10: 检查当前是否实际连接（基于 active_device）
    connected = False
    try:
        if REGISTRY_FILE.exists():
            registry = json.loads(REGISTRY_FILE.read_text(encoding='utf-8'))
            active_mac = registry.get('active_device', '').strip()
            connected = bool(active_mac)
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
    """获取所有网络接口列表，按优先级排序。"""
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


# ================================================================ #
#  PTZ 控制端点
# ================================================================ #


@api_router.post("/ptz/{device_id}/move", summary="PTZ 移动", tags=["PTZ"])
async def ptz_move(device_id: str, req: PTZMoveRequest) -> dict:
    """PTZ 方向移动控制。"""
    try:
        mgr: PTZManager | None = _managers.get("ptz_manager")
        if not mgr:
            return {"success": False, "message": "PTZManager 未初始化"}

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
    """PTZ 归位（预置点 10）。"""
    import asyncio
    mgr: PTZManager | None = _managers.get("ptz_manager")
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    result = await asyncio.to_thread(mgr.ptz_home, target_ip)
    return result


@api_router.post("/ptz/{device_id}/stop", summary="PTZ 停止", tags=["PTZ"])
async def ptz_stop(device_id: str) -> dict:
    """PTZ 停止所有移动。"""
    mgr: PTZManager | None = _managers.get("ptz_manager")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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
    """设置对焦模式（手动/自动/半自动）"""
    mgr: PTZManager | None = _managers.get("ptz_manager")
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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
            return {"success": True, "message": f"对焦模式已设置为 {req.mode}"}
        return {"success": False, "message": f"设置对焦模式失败: {result.status_code}"}
    except Exception as e:
        return {"success": False, "message": f"设置对焦模式失败: {e}"}


@api_router.get("/ptz/{device_id}/focus/mode", summary="获取对焦模式", tags=["PTZ"])
async def get_focus_mode(device_id: str) -> dict:
    """获取当前对焦模式"""
    mgr: PTZManager | None = _managers.get("ptz_manager")
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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
    mgr: PTZManager | None = _managers.get("ptz_manager")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    return mgr.ptz_list_presets(target_ip)


@api_router.post("/ptz/{device_id}/preset/{preset_id}", summary="预置位", tags=["PTZ"])
async def ptz_preset(device_id: str, preset_id: int) -> dict:
    """移动到指定预置点。"""
    mgr: PTZManager | None = _managers.get("ptz_manager")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

    # BUG-A 修复: 支持 MAC 地址作为 device_id
    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    return mgr.ptz_preset(target_ip, preset_id=preset_id)


@api_router.post("/ptz/{device_id}/preset/{preset_id}/set", summary="保存预置位", tags=["PTZ"])
async def ptz_set_preset(device_id: str, preset_id: int) -> dict:
    """设置当前位置为指定预置点。"""
    mgr: PTZManager | None = _managers.get("ptz_manager")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    return mgr.set_preset(target_ip, preset_id=preset_id)


@api_router.post("/ptz/{device_id}/absolute", summary="绝对位置", tags=["PTZ"])
async def ptz_absolute(device_id: str, req: PTZAbsoluteRequest) -> dict:
    """绝对坐标移动（Pan/Tilt/Zoom）。"""
    mgr: PTZManager | None = _managers.get("ptz_manager")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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
    mgr: PTZManager | None = _managers.get("ptz_manager")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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
    mgr: PTZManager | None = _managers.get("ptz_manager")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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

        # PUT 更新（移除 ns0: 命名空间前缀）
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
    """切换 PTZ 坐标（P/T/Z）OSD 显示。"""
    enabled = (body or {}).get("enabled", True) if body else True
    
    mgr: PTZManager | None = _managers.get("ptz_manager")
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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

        # PUT 更新（移除 ns0: 命名空间前缀）
        xml_str = ET.tostring(root, encoding='unicode')
        xml_str = xml_str.replace('ns0:', '')
        xml_str = xml_str.replace('xmlns:ns0=', 'xmlns=')
        put_resp = client.put(endpoint, '<?xml version="1.0" encoding="UTF-8"?>' + xml_str)
        if put_resp.status_code == 200:
            return {"success": True, "message": f"PTZ 坐标 OSD 已{'开启' if enabled else '关闭'}", "enabled": enabled}
        else:
            return {"success": False, "message": f"PUT 失败: HTTP {put_resp.status_code}"}

    except Exception as e:
        return {"success": False, "message": f"PTZ OSD 切换异常: {e}"}


@api_router.post("/ptz/{device_id}/osd/info", summary="切换 OSD 信息显示", tags=["PTZ"])
async def ptz_osd_info_toggle(device_id: str, body: dict = None) -> dict:
    """切换 OSD 信息显示（用户自定义、日期时间等）。"""
    enabled = (body or {}).get("enabled", True) if body else True
    
    mgr: PTZManager | None = _managers.get("ptz_manager")
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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

        # PUT 更新（带 XML 声明，移除 ns0: 命名空间前缀）
        new_xml = '<?xml version="1.0" encoding="UTF-8"?>'
        xml_str = ET.tostring(root, encoding='unicode')
        # 移除 ns0: 前缀和 xmlns:ns0 声明
        xml_str = xml_str.replace('ns0:', '')
        xml_str = xml_str.replace('xmlns:ns0=', 'xmlns=')
        new_xml += xml_str
        put_resp = client.put(endpoint, new_xml)
        if put_resp.status_code == 200:
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
    """获取当前画面参数（亮度/对比度/饱和度）。"""
    mgr: PTZManager | None = _managers.get("ptz_manager")
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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
    mgr: PTZManager | None = _managers.get("ptz_manager")
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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
        # 使用 /Image/channels/1/Color 端点，而不是整个 ImageChannel
        color_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Color version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
<brightnessLevel>{updated.get("brightness", 50)}</brightnessLevel>
<contrastLevel>{updated.get("contrast", 50)}</contrastLevel>
<saturationLevel>{updated.get("saturation", 50)}</saturationLevel>
</Color>'''
        
        put_resp = client.put("/Image/channels/1/Color", color_xml)
        if put_resp.status_code == 200:
            return {"success": True, "message": "画面设置已更新", "data": updated}
        else:
            return {"success": False, "message": f"更新失败: HTTP {put_resp.status_code}"}

    except Exception as e:
        return {"success": False, "message": f"更新画面设置异常: {e}"}


@api_router.post("/ptz/{device_id}/capture", summary="PTZ 截图（ISAPI 原生）", tags=["PTZ"])
async def ptz_capture(device_id: str, req: PTZCaptureRequest | None = None) -> dict:
    """通过海康 ISAPI 原生方法截取 PTZ 设备当前视频帧。

    使用: GET /ISAPI/Streaming/Channels/{channel}/picture
    不再依赖 ffmpeg。
    """
    mgr: PTZManager | None = _managers.get("ptz_manager")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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
            return {"success": False, "message": "ISAPI 截图失败：设备未返回图像数据"}

        # JPEG 头验证
        if jpeg_bytes[:3] != b"\xff\xd8\xff":
            return {"success": False, "message": "返回的数据不是有效的 JPEG"}

        # 保存文件
        from src.stream.constants import DOWNLOAD_IMAGE_DIR
        from src.core.file_naming import generate_filename

        # 获取设备名称（如有）
        target_name = ""
        if req and req.stream_id:
            target_name = req.stream_id
        elif req and req.stream_url:
            target_name = "capture"

        filename = generate_filename(target_name=target_name or None, device_ip=target_ip, extension=".jpg")
        filepath = DOWNLOAD_IMAGE_DIR / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_bytes(jpeg_bytes)
        file_size = filepath.stat().st_size

        return {
            "success": True,
            "message": f"截图成功: {device_id}",
            "data": {
                "mac": device_id,
                "image_path": str(filepath),
                "image_size": file_size,
                "filename": filename,
                "format": "jpeg",
                "verified": True,
            },
        }
    except Exception as e:
        return {"success": False, "message": f"截图异常: {e}"}


# ================================================================ #
#  PTZ 录像端点
# ================================================================ #


@api_router.post("/ptz/{device_id}/record/start", summary="启动录像（FFmpeg RTSP → 本地）", tags=["PTZ"])
async def ptz_record_start(device_id: str, req: PTZRecordRequest | None = None) -> dict:
    """通过 FFmpeg 拉取 RTSP 流录制到本地 record/ 目录。

    适用于设备无内置存储介质（HDD/SD/NAS 为空）的场景。
    支持 target_name 参数指定文件名标识（跟踪目标名称）。
    """
    mgr: PTZManager | None = _managers.get("ptz_manager")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    target_name = req.target_name if req else ""
    return mgr.start_recording(target_ip, target_name=target_name)


@api_router.post("/ptz/{device_id}/record/stop", summary="停止录像（FFmpeg 进程）", tags=["PTZ"])
async def ptz_record_stop(device_id: str) -> dict:
    """停止 FFmpeg 录制进程。如有 FTP 配置则自动上传。
    """
    mgr: PTZManager | None = _managers.get("ptz_manager")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}

    return mgr.stop_recording(target_ip)


# ================================================================ #
#  流服务端点
# ================================================================ #


@api_router.get("/streams", summary="流列表", tags=["Streams"])
async def list_streams() -> dict:
    """获取流列表。"""
    mgr: StreamManager | None = _managers.get("stream_manager")  # type: ignore[assignment]
    if mgr:
        try:
            streams = mgr.list_streams()
            if streams:
                return {"data": streams, "total": len(streams)}
        except Exception:
            pass
    # Return empty but properly structured
    return {"data": [], "total": 0}


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


# ================================================================ #
#  流服务器扩展端点 (P0: 启动 / Snapshot / HLS)
# ================================================================ #


@api_router.post("/streams/{device_id}/start", summary="启动设备视频流", tags=["Streams"])
async def start_stream(device_id: str, rtsp_url: str = "", stream_name: str = "") -> dict:
    """启动设备视频流（HLS）。"""
    from src.core.stream_manager import StreamManager
    from src.config_paths import DATA_DIR
    import os
    
    mgr: StreamManager | None = _managers.get("stream_manager")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "StreamManager 未初始化", "data": [], "total": 0}
    
    # Try to get credentials for the device
    ptz_mgr = _managers.get("ptz_manager")
    if not rtsp_url and ptz_mgr:
        creds = ptz_mgr._credentials.get(device_id)
        if creds:
            user = creds.get("username", "admin")
            pwd = creds.get("password", "")
            rtsp_url = f"rtsp://{user}:{pwd}@{device_id}:554/Streaming/Channels/101"
    
    if not rtsp_url:
        rtsp_url = f"rtsp://admin@{device_id}:554/Streaming/Channels/101"
    if not stream_name:
        stream_name = f"Stream-{device_id}"
    
    # Create stream record in StreamManager
    stream_result = mgr.start_stream(
        device_id=device_id,
        rtsp_url=rtsp_url,
        stream_name=stream_name,
    )
    stream_id = stream_result.get("stream_id") if isinstance(stream_result, dict) else stream_result

    
    
    if not stream_id:
        return {"success": False, "message": "流启动失败", "data": [], "total": 0, "stream_id": None}
    
    streams = mgr.list_streams()
    return {
        "success": True,
        "message": f"已启动流: {stream_name}",
        "data": streams,
        "total": len(streams),
        "stream_id": stream_id,
    }

@api_router.post("/streams/{device_id}/stop", summary="停止设备视频流", tags=["Streams"])
async def stop_stream(device_id: str) -> dict:
    """停止设备的视频流。"""
    mgr: StreamManager | None = _managers.get("stream_manager")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "StreamManager 未初始化"}
    
    # 查找该设备的流
    for stream in mgr.list_streams():
        if stream.get("device_id") == device_id:
            sid = stream.get("stream_id")
            mgr.stop_stream(sid)
            streams = mgr.list_streams()
            return {
                "success": True,
                "message": f"流已停止: {device_id}",
                "data": streams,
                "total": len(streams),
            }
    return {"success": False, "message": f"未找到设备 {device_id} 的流"}


@api_router.get("/streams/{device_id}/snapshot", summary="获取设备快照", tags=["Streams"])
async def get_stream_snapshot(device_id: str) -> dict:
    """获取设备当前帧的静态图像快照。
    
    返回 base64 编码的 JPEG 图像或快照 URL。
    """
    mgr: StreamManager | None = _managers.get("stream_manager")  # type: ignore[assignment]
    if not mgr:
        return {"success": False, "message": "StreamManager 未初始化"}
    
    # 查找该设备的流
    for stream in mgr.list_streams():
        if str(stream.get("device_id")) == str(device_id):
            sid = stream.get("stream_id")
            preview_url = mgr.get_preview_url(sid)
            status = mgr.get_stream_status(sid)
            return {
                "success": True,
                "message": f"快照获取成功: {device_id}",
                "data": {
                    "mac": device_id,
                    "stream_id": sid,
                    "preview_url": preview_url,
                    "status": status,
                    "snapshot_url": f"/hls/{sid}/snapshot.jpg",
                },
            }
    
    # 如果流未启动，尝试自动创建
    rtsp_url = f"rtsp://{device_id}:554/stream"
    try:
        stream_id = mgr.start_stream(
            device_id=device_id,
            rtsp_url=rtsp_url,
            stream_name=f"Snapshot-{device_id}",
        )
        preview_url = mgr.get_preview_url(stream_id)
        return {
            "success": True,
            "message": f"流已自动创建并获取快照: {device_id}",
            "data": {
                "mac": device_id,
                "stream_id": stream_id,
                "preview_url": preview_url,
                "snapshot_url": f"/hls/{stream_id}/snapshot.jpg",
            },
        }
    except Exception as e:
        return {"success": False, "message": f"获取快照失败: {e}"}


# ================================================================ #
#  高级功能端点 (Advanced: Function/Limit/Speed/Config/Onboarding)
# ================================================================ #

def _resolve_mac_from_ip(device_ip: str, client: "ISAPIClient | None" = None,
                          ptz_mgr: "PTZManager | None" = None) -> str:
    """通过 PTZManager 缓存或 ISAPI 获取设备的 MAC 地址。"""
    # Try PTZManager cache first
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
class AdvancedFunctionRunRequest(BaseModel):
    """功能探测运行请求。"""
    device_ip: str = ""
    username: str = "admin"
    password: str = ""
    port: int = 80
    item: str = ""  # 留空 = 全部探测


class AdvancedLimitRunRequest(BaseModel):
    """限位测试运行请求。"""
    device_ip: str = ""
    username: str = "admin"
    password: str = ""
    port: int = 80


class AdvancedSpeedRunRequest(BaseModel):
    """速度测试运行请求。"""
    device_ip: str = ""
    username: str = "admin"
    password: str = ""
    port: int = 80
    speed_profile: str = "lite"


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


# --- Function 功能探测 ---

@api_router.post("/advanced/function/run", summary="运行功能探测", tags=["Advanced"])
async def advanced_function_run(req: AdvancedFunctionRunRequest) -> dict:
    """运行设备功能探测 (P4.1-P4.21)。"""
    try:
        from src.ptz.isapi.client import ISAPIClient
        from src.advanced.function import FunctionDetector

        mgr: "PTZManager | None" = _managers.get("ptz_manager")  # type: ignore[assignment]
        username = req.username or "admin"
        password = req.password
        port = req.port or 80
        if not password:
            creds = mgr.get_credentials(req.device_ip) if mgr else None
            if creds:
                username = creds.get("username", username)
                password = creds.get("password", "")
                port = creds.get("port", port)

        client = ISAPIClient(
            ip=req.device_ip,
            username=username,
            password=password,
            port=port,
        )
        if not client.verify_credentials():
            return {"success": False, "message": "设备认证失败"}

        detector = FunctionDetector(client)

        if req.item:
            result = {req.item: detector.detect_single(req.item)}
        else:
            # Bug #2 修复: 功能探测开始前，第一步设置预置点10并归位
            import time
            from src.ptz.isapi.ptz import PTZController
            ptz = PTZController(client)
            ptz.set_preset(10)
            time.sleep(1)
            ptz.goto_preset(10)
            time.sleep(3)

            from src.advanced.function import FUNCTION_ENDPOINTS
            result = {}
            for item_key in FUNCTION_ENDPOINTS:
                result[item_key] = detector.detect_single(item_key)

        restore_ok = detector.restore_all()

        # Auto-save to DataStore (按设计文档)
        from src.storage.store import get_store

        ptz_mgr_fn: "PTZManager | None" = _managers.get("ptz_manager")  # type: ignore[assignment]
        mac = _resolve_mac_from_ip(req.device_ip, ptz_mgr=ptz_mgr_fn)
        config_saved = False
        try:
            store = get_store()
            registry = store.get_registry()
            mac_key = mac.upper().replace(":", "-")
            device_id = registry.get("devices", {}).get(mac_key, {}).get("id", "dev_001")
            store.save_function_results(device_id, result)
            config_saved = True
        except Exception:
            pass

        return {
            "success": True,
            "message": f"功能探测完成: {req.device_ip}",
            "results": result,
            "restored": restore_ok,
            "status": detector.get_status(),
            "config_saved": config_saved,
            "mac": mac,
        }
    except Exception as e:
        return {"success": False, "message": f"功能探测异常: {e}"}


@api_router.get("/advanced/function/status", summary="获取功能探测状态", tags=["Advanced"])
async def advanced_function_status(device_ip: str = Query(default="")) -> dict:
    """获取设备功能探测状态。"""
    if not device_ip:
        return {"success": True, "status": {"total": 0, "completed": 0, "supported": 0, "progress": 0}, "supported_functions": []}
    try:
        from src.ptz.isapi.client import ISAPIClient
        from src.advanced.function import FunctionDetector

        ptz_mgr: PTZManager | None = _managers.get("ptz_manager")  # type: ignore[assignment]
        creds = ptz_mgr.get_credentials(device_ip) if ptz_mgr else None
        if not creds:
            return {"success": False, "message": "设备未保存凭据，请先注册设备"}
        client = ISAPIClient(
            ip=device_ip,
            username=creds["username"],
            password=creds["password"],
            port=creds.get("port", 80),
        )
        detector = FunctionDetector(client)

        return {
            "success": True,
            "status": detector.get_status(),
            "supported_functions": detector.get_supported_functions(),
        }
    except Exception as e:
        return {"success": False, "message": f"获取状态异常: {e}"}


@api_router.post("/advanced/function/restore", summary="恢复功能默认值", tags=["Advanced"])
async def advanced_function_restore(device_ip: str = "", username: str = "admin", password: str = "", port: int = 80) -> dict:
    """恢复设备功能默认值 (P4.21)。"""
    if not device_ip:
        return {"success": False, "message": "缺少 device_ip 参数"}
    try:
        from src.ptz.isapi.client import ISAPIClient
        from src.advanced.function import FunctionDetector, RESTORE_DEFAULTS_ENDPOINT

        client = ISAPIClient(ip=device_ip, username=username, password=password, port=port)
        if not client.verify_credentials():
            return {"success": False, "message": "设备认证失败"}

        # 调用设备恢复默认 API
        result = client.put(RESTORE_DEFAULTS_ENDPOINT,
            '<?xml version="1.0" encoding="UTF-8"?><restore xmlns="http://www.hikvision.com/ver20/XMLSchema"/>')

        return {
            "success": result.status_code == 200,
            "message": "设备参数已尝试恢复",
            "http_status": result.status_code,
        }
    except Exception as e:
        return {"success": False, "message": f"恢复异常: {e}"}


# --- Limit 限位测试 ---

@api_router.post("/advanced/limit/run", summary="运行限位测试", tags=["Advanced"])
async def advanced_limit_run(req: AdvancedLimitRunRequest) -> dict:
    """运行设备限位测试 (P6.0-P6.4)。"""
    try:
        from src.ptz.isapi.client import ISAPIClient
        from src.advanced.limit import LimitTester

        mgr: "PTZManager | None" = _managers.get("ptz_manager")  # type: ignore[assignment]
        username = req.username or "admin"
        password = req.password
        port = req.port or 80
        if not password:
            creds = mgr.get_credentials(req.device_ip) if mgr else None
            if creds:
                username = creds.get("username", username)
                password = creds.get("password", "")
                port = creds.get("port", port)

        client = ISAPIClient(
            ip=req.device_ip,
            username=username,
            password=password,
            port=port,
        )
        if not client.verify_credentials():
            return {"success": False, "message": "设备认证失败"}

        ptz_mgr_lm: "PTZManager | None" = _managers.get("ptz_manager")  # type: ignore[assignment]
        mac = _resolve_mac_from_ip(req.device_ip, ptz_mgr=ptz_mgr_lm)
        
        # 从MAC获取device_id
        store = get_store()
        registry = store.get_registry()
        mac_key = mac.upper().replace(":", "-") if mac else "unknown"
        device_id = registry.get("devices", {}).get(mac_key, {}).get("id", "dev_001")
        
        tester = LimitTester(client, device_id=device_id)
        results = tester.run_all_tests()

        # Auto-save to DataStore (按设计文档)
        config_saved = False
        try:
            store.save_limit_results(device_id, results)
            config_saved = True
        except Exception:
            pass

        return {
            "success": results.get("success", False),
            "message": f"限位测试完成: {req.device_ip}",
            "results": results,
            "csv_path": results.get("csv_path", ""),
            "config_saved": config_saved,
            "mac": mac,
        }
    except Exception as e:
        return {"success": False, "message": f"限位测试异常: {e}"}


@api_router.get("/advanced/limit/status", summary="获取限位测试状态", tags=["Advanced"])
async def advanced_limit_status(device_ip: str = Query(default="")) -> dict:
    """获取设备限位测试状态。"""
    if not device_ip:
        return {"success": True, "status": {}}
    try:
        from src.ptz.isapi.client import ISAPIClient
        from src.advanced.limit import LimitTester

        ptz_mgr: PTZManager | None = _managers.get("ptz_manager")  # type: ignore[assignment]
        creds = ptz_mgr.get_credentials(device_ip) if ptz_mgr else None
        if not creds:
            return {"success": False, "message": "设备未保存凭据，请先注册设备"}
        client = ISAPIClient(
            ip=device_ip,
            username=creds["username"],
            password=creds["password"],
            port=creds.get("port", 80),
        )
        tester = LimitTester(client, device_id="status_check")

        return {
            "success": True,
            "status": tester.get_status(),
        }
    except Exception as e:
        return {"success": False, "message": f"获取状态异常: {e}"}


# --- P5.1/P5.2 Move Tests ---

class AdvancedMoveTestRequest(BaseModel):
    """移动测试请求 (P5.1/P5.2)。"""
    device_ip: str = ""
    username: str = "admin"
    password: str = ""
    port: int = 80


@api_router.post("/advanced/move/continuous", summary="P5.1 Continuous Move测试", tags=["Advanced"])
async def advanced_continuous_move_test(req: AdvancedMoveTestRequest) -> dict:
    """P5.1: 测试持续运动能力。"""
    try:
        from src.ptz.isapi.client import ISAPIClient
        from src.advanced.function import test_continuous_move

        client = ISAPIClient(ip=req.device_ip, username=req.username, password=req.password, port=req.port)
        result = test_continuous_move(client)
        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "message": str(e)}


@api_router.post("/advanced/move/absolute", summary="P5.2 Absolute Move测试", tags=["Advanced"])
async def advanced_absolute_move_test(req: AdvancedMoveTestRequest) -> dict:
    """P5.2: 测试绝对运动能力（评审必须）。"""
    try:
        from src.ptz.isapi.client import ISAPIClient
        from src.advanced.function import test_absolute_move

        client = ISAPIClient(ip=req.device_ip, username=req.username, password=req.password, port=req.port)
        result = test_absolute_move(client)
        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "message": str(e)}


# --- Speed 速度测试 ---

@api_router.post("/advanced/speed/run", summary="运行速度测试", tags=["Advanced"])
async def advanced_speed_run(req: AdvancedSpeedRunRequest) -> dict:
    """运行设备速度测试 (P5.4)。"""
    try:
        from src.ptz.isapi.client import ISAPIClient
        from src.ptz.isapi.ptz import PTZController
        from src.advanced.speed import SpeedTester

        # 使用传入的凭据
        username = req.username or "admin"
        password = req.password
        port = req.port or 80

        # 如果密码为空，尝试从PTZManager获取
        if not password:
            mgr: PTZManager | None = _managers.get("ptz_manager")  # type: ignore[assignment]
            if mgr:
                creds = mgr.get_credentials(req.device_ip)
                if creds:
                    username = creds.get("username", username)
                    password = creds.get("password", "")
                    port = creds.get("port", port)

        client = ISAPIClient(ip=req.device_ip, username=username, password=password, port=port)
        ptz = PTZController(client)

        # 获取限位数据
        from src.storage.store import get_store
        store = get_store()
        device_id = "dev_001"
        limit_data = store.get_limit_results(device_id)
        limit_map = limit_data.get("results") if limit_data else None

        # 先获取MAC
        ptz_mgr_sp: "PTZManager | None" = _managers.get("ptz_manager")  # type: ignore[assignment]
        mac = _resolve_mac_from_ip(req.device_ip, ptz_mgr=ptz_mgr_sp) or "unknown"
        mac_key = mac.upper().replace(":", "-")

        tester = SpeedTester(ptz)
        results = tester.run_all_tests(config=None, mac=mac_key, device_id=device_id, speed_profile=req.speed_profile)

        # Auto-save to DataStore
        config_saved = False
        try:
            store = get_store()
            registry = store.get_registry()
            device_id = registry.get("devices", {}).get(mac_key, {}).get("id", "dev_001")
            store.save_speed_results(device_id, results)
            config_saved = True
        except Exception:
            pass

        return {
            "success": results.get("success", False),
            "message": f"速度测试完成: {req.device_ip}",
            "results": results,
            "config_saved": config_saved,
            "mac": mac,
        }
    except Exception as e:
        return {"success": False, "message": f"速度测试异常: {e}"}


@api_router.get("/advanced/speed/status", summary="获取速度测试状态", tags=["Advanced"])
async def advanced_speed_status(device_ip: str = Query(default="")) -> dict:
    """获取设备速度测试状态。"""
    if not device_ip:
        return {"success": True, "status": {}}
    try:
        from src.ptz.isapi.client import ISAPIClient
        from src.advanced.speed import SpeedTester

        ptz_mgr: PTZManager | None = _managers.get("ptz_manager")  # type: ignore[assignment]
        creds = ptz_mgr.get_credentials(device_ip) if ptz_mgr else None
        if not creds:
            return {"success": False, "message": "设备未保存凭据，请先注册设备"}
        client = ISAPIClient(
            ip=device_ip,
            username=creds["username"],
            password=creds["password"],
            port=creds.get("port", 80),
        )
        tester = SpeedTester(client)

        return {
            "success": True,
            "status": tester.get_status(),
        }
    except Exception as e:
        return {"success": False, "message": f"获取状态异常: {e}"}


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
            from src.advanced.function import FunctionDetector, FUNCTION_ENDPOINTS
            from src.advanced.limit import LimitTester
            from src.advanced.speed import SpeedTester
            from src.advanced.config_writer import write_device_config

            mgr: PTZManager | None = _managers.get("ptz_manager")
            if not mgr:
                detect_tasks[task_id].update(status="failed", current_step="PTZManager not initialized")
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
                detect_tasks[task_id].update(progress=0.0, current_step="function_detection")
                detector = FunctionDetector(client)
                func_result = {}
                for idx, item_key in enumerate(FUNCTION_ENDPOINTS):
                    func_result[item_key] = detector.detect_single(item_key)
                    detect_tasks[task_id]["progress"] = round(10.0 + (idx / len(FUNCTION_ENDPOINTS)) * 20.0, 1)
                detector.restore_all()
                results["function"] = func_result
                write_device_config(mac=_resolve_mac_from_ip(req.device_ip, ptz_mgr=mgr), capabilities=func_result, ip=req.device_ip)

            if "limit" in req.items:
                detect_tasks[task_id].update(progress=35.0, current_step="limit_test")
                mac = _resolve_mac_from_ip(req.device_ip, ptz_mgr=mgr)
                device_id = mac.upper().replace(":", "-") if mac else "onboarding"
                limit_tester = LimitTester(client, device_id=device_id)
                limit_result = limit_tester.run_all_tests()
                results["limit"] = limit_result
                detect_tasks[task_id]["progress"] = 60.0
                write_device_config(mac=mac, limits=limit_result, ip=req.device_ip)

            if "speed" in req.items:
                detect_tasks[task_id].update(progress=65.0, current_step="speed_test")
                speed_tester = SpeedTester(ctrl)
                speed_result = speed_tester.run_all_tests(speed_profile=req.speed_profile)
                results["speed"] = speed_result
                detect_tasks[task_id]["progress"] = 95.0
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

    mgr = _managers.get("ptz_manager")
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

    # Find device IP from PTZManager
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
        return {"success": False, "message": "设备未保存凭据，请先连接设备"}

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
    """获取设备凭据（用于 WASM SDK 登录）
    先查内存，再回退读 data/devices/{MAC}.json
    """
    ptz_mgr = _managers.get("ptz_manager")
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
    # 回退：从 data/devices/{MAC}.json 文件读取
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
    3. 优先最新时间戳文件，其次固定名称
    4. MAC 不匹配则返回错误
    """
    import json
    mgr: PTZManager | None = _managers.get("ptz_manager")
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化", "data": None}
    
    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}", "data": None}
    
    # v6.33: 通过 IP 找到 MAC，确保数据匹配正确设备
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
    
    # v6.33: 使用 MAC 读取功能探测数据（优先时间戳文件）
    func_file = get_data_path_read(None, target_mac, "function")
    if func_file and func_file.exists():
        try:
            func_data = json.loads(func_file.read_text(encoding="utf-8"))
            return {"success": True, "data": func_data}
        except Exception as e:
            return {"success": False, "message": f"读取功能探测数据失败: {e}", "data": None}
    else:
        return {"success": False, "message": "未找到功能探测数据，请先完成功能测试", "data": None}




@api_router.get("/ptz/{device_id}/image/whitebalance", summary="获取白平衡设置", tags=["Image"])
async def get_whitebalance(device_id: str) -> dict:
    """获取设备白平衡当前设置。"""
    import xml.etree.ElementTree as ET
    mgr: PTZManager | None = _managers.get("ptz_manager")
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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

        root = ET.fromstring(resp.xml)
        result = {"success": True, "data": {}}
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "WhiteBalanceStyle":
                result["data"]["mode"] = (elem.text or "manual").lower()
            elif tag == "WhiteBalanceRed":
                result["data"]["red_gain"] = int((elem.text or "50").strip())
            elif tag == "WhiteBalanceBlue":
                result["data"]["blue_gain"] = int((elem.text or "50").strip())
            elif tag == "whiteBalanceRed":
                result["data"]["red_gain"] = int((elem.text or "50").strip())
            elif tag == "whiteBalanceBlue":
                result["data"]["blue_gain"] = int((elem.text or "50").strip())

        result["data"]["min"] = 0
        result["data"]["max"] = 255
        result["data"]["supported_modes"] = ["manual", "auto"]
        return result
    except Exception as e:
        return {"success": False, "message": f"获取白平衡异常: {e}"}


@api_router.post("/ptz/{device_id}/image/whitebalance", summary="设置白平衡", tags=["Image"])
async def set_whitebalance(device_id: str, data: dict) -> dict:
    """设置白平衡参数（模式或R/B增益）。"""
    import xml.etree.ElementTree as ET
    mgr: PTZManager | None = _managers.get("ptz_manager")
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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
            return {"success": True, "message": "白平衡已更新", "data": {"mode": mode_val, "red_gain": red_val, "blue_gain": blue_val}}
        return {"success": False, "message": f"更新失败: HTTP {put_resp.status_code}"}
    except Exception as e:
        return {"success": False, "message": f"设置白平衡异常: {e}"}


@api_router.get("/ptz/{device_id}/image/noisereduce", summary="获取降噪设置", tags=["Image"])
async def get_noisereduce(device_id: str) -> dict:
    """获取设备降噪当前设置。"""
    import xml.etree.ElementTree as ET
    mgr: PTZManager | None = _managers.get("ptz_manager")
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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
    mgr: PTZManager | None = _managers.get("ptz_manager")
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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
            return {"success": True, "message": "降噪已更新", "data": {"spatial_level": spatial, "temporal_level": temporal}}
        return {"success": False, "message": f"更新失败: HTTP {put_resp.status_code}"}
    except Exception as e:
        return {"success": False, "message": f"设置降噪异常: {e}"}


@api_router.post("/ptz/{device_id}/image/reset", summary="重置画面控制到默认值", tags=["Image"])
async def reset_image_controls(device_id: str) -> dict:
    """v6.51: 重置设备画面控制到默认值（不调用设备系统重置）。"""
    import xml.etree.ElementTree as ET
    mgr: PTZManager | None = _managers.get("ptz_manager")
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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
    mgr: PTZManager | None = _managers.get("ptz_manager")
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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

        # 如果没有找到曝光模式，默认 auto
        if "mode" not in result["data"]:
            result["data"]["mode"] = "auto"
        return result
    except Exception as e:
        return {"success": False, "message": f"获取曝光模式异常: {e}"}


@api_router.post("/ptz/{device_id}/image/exposure", summary="设置曝光模式", tags=["Image"])
async def set_exposure(device_id: str, data: dict) -> dict:
    """设置曝光模式 - v7.03: 使用 ExposureType 字段"""
    import xml.etree.ElementTree as ET
    mgr: PTZManager | None = _managers.get("ptz_manager")
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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
            return {"success": True, "message": f"曝光模式已设置为 {mode}"}
        return {"success": False, "message": f"更新失败: HTTP {put_resp.status_code}"}
    except Exception as e:
        return {"success": False, "message": f"设置曝光模式异常: {e}"}


@api_router.get("/ptz/{device_id}/image/shutter", summary="获取快门设置", tags=["Image"])
async def get_shutter(device_id: str) -> dict:
    """获取设备快门当前设置。"""
    import xml.etree.ElementTree as ET
    mgr: PTZManager | None = _managers.get("ptz_manager")
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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
    mgr: PTZManager | None = _managers.get("ptz_manager")
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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
            return {"success": True, "message": f"快门已设置为 {level}"}
        return {"success": False, "message": f"更新失败: HTTP {put_resp.status_code}"}
    except Exception as e:
        return {"success": False, "message": f"设置快门异常: {e}"}


@api_router.get("/ptz/{device_id}/image/iris", summary="获取光圈设置", tags=["Image"])
async def get_iris(device_id: str) -> dict:
    """获取设备光圈当前设置。"""
    import xml.etree.ElementTree as ET
    mgr: PTZManager | None = _managers.get("ptz_manager")
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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
    mgr: PTZManager | None = _managers.get("ptz_manager")
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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
            return {"success": True, "message": f"光圈已设置"}
        return {"success": False, "message": f"更新失败: HTTP {put_resp.status_code}"}
    except Exception as e:
        return {"success": False, "message": f"设置光圈异常: {e}"}


# v7.03: 增益 (Gain) API
@api_router.get("/ptz/{device_id}/image/gain", summary="获取增益设置", tags=["Image"])
async def get_gain(device_id: str) -> dict:
    """获取设备增益当前设置。"""
    import xml.etree.ElementTree as ET
    mgr: PTZManager | None = _managers.get("ptz_manager")
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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
    mgr: PTZManager | None = _managers.get("ptz_manager")
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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
            return {"success": True, "message": f"增益已设置为 {level}"}
        return {"success": False, "message": f"更新失败: HTTP {put_resp.status_code}"}
    except Exception as e:
        return {"success": False, "message": f"设置增益异常: {e}"}


@api_router.get("/ptz/{device_id}/image/sharpness", summary="获取锐度设置", tags=["Image"])
async def get_sharpness(device_id: str) -> dict:
    """获取设备锐度当前设置。"""
    import xml.etree.ElementTree as ET
    mgr: PTZManager | None = _managers.get("ptz_manager")
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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
    mgr: PTZManager | None = _managers.get("ptz_manager")
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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
            return {"success": True, "message": f"锐度已设置为 {level}"}
        return {"success": False, "message": f"更新失败: HTTP {put_resp.status_code}"}
    except Exception as e:
        return {"success": False, "message": f"设置锐度异常: {e}"}


@api_router.get("/ptz/{device_id}/image/color", summary="获取颜色设置", tags=["Image"])
async def get_color(device_id: str) -> dict:
    """获取设备颜色（亮度/对比度/饱和度）当前设置。"""
    import xml.etree.ElementTree as ET
    mgr: PTZManager | None = _managers.get("ptz_manager")
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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


@api_router.get("/ptz/{device_id}/osd/ptz", summary="获取PTZ OSD状态", tags=["OSD"])
async def get_osd_ptz(device_id: str) -> dict:
    """获取PTZ OSD显示状态。"""
    import xml.etree.ElementTree as ET
    mgr: PTZManager | None = _managers.get("ptz_manager")
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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
    mgr: PTZManager | None = _managers.get("ptz_manager")
    if not mgr:
        return {"success": False, "message": "PTZManager 未初始化"}

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

@api_router.post("/system/restart", summary="重启 AstroHub", tags=["System"])
async def restart_astrohub() -> dict:
    """重启 AstroHub 服务。"""
    import subprocess
    import os
    import platform
    
    cwd = os.getcwd()
    
    # v6.43: 简化重启逻辑
    if platform.system() == "Windows":
        # Windows: 延迟10秒启动新进程，等待期间前端刷新
        ps_script = f'''
Start-Sleep -Seconds 10
Set-Location "{cwd}"
Start-Process python -ArgumentList "src/main/main.py" -WindowStyle Hidden
'''
        subprocess.Popen(["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_script], cwd=cwd)
    else:
        # Linux/macOS
        subprocess.Popen(f'sleep 10 && cd "{cwd}" && python src/main/main.py &', shell=True, cwd=cwd)
    
    # 立即退出当前进程
    os._exit(0)



