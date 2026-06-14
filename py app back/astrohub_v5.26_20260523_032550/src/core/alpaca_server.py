"""
src/core/alpaca_server.py - ASCOM Alpaca Server

AstroHub 作为 Alpaca Server 输出 PTZ/焦点/日夜切换为 ASCOM 设备。
- PTZ Pan/Tilt → ASCOM Telescope（指向、跟踪）
- 焦点控制 → ASCOM Focuser（调焦器）
- 日夜切换 → ASCOM FilterWheel（滤镜轮）

外部软件（NINA、ASCOM Platform）通过 http://localhost:5555/management/v1/apidevices 发现设备。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import json
import threading
import time
import traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Callable
import logging

logger = logging.getLogger("alpaca_server")

# ASCOM Alpaca 标准响应格式
class AlpacaResponse:
    @staticmethod
    def ok(value: Any = None, server_transaction_id: int = 0) -> dict:
        return {
            "Value": value,
            "ServerTransactionID": server_transaction_id,
            "ClientTransactionID": 0,
            "ErrorNumber": 0,
            "ErrorMessage": "",
        }

    @staticmethod
    def error(error_number: int, error_message: str, server_transaction_id: int = 0) -> dict:
        return {
            "Value": None,
            "ServerTransactionID": server_transaction_id,
            "ClientTransactionID": 0,
            "ErrorNumber": error_number,
            "ErrorMessage": error_message,
        }


class AlpacaState:
    """线程安全的 ASCOM 设备状态管理。"""

    def __init__(self, ptz_manager: Any = None) -> None:
        self._ptz_manager = ptz_manager
        self._lock = threading.RLock()

        # Telescope 状态
        self._scope_connected = False
        self._scope_slewing = False
        self._scope_ra = 12.0  # 赤经 (小时)
        self._scope_dec = 45.0  # 赤纬 (度)
        self._scope_tracking = False  # False = trackOff
        self._scope_name = "AstroHub PTZ Telescope"
        self._scope_description = "AstroHub PTZ Pan/Tilt mapped to ASCOM Telescope"
        self._scope_driver_version = "2.0.0"
        self._scope_target_ra = 12.0
        self._scope_target_dec = 45.0
        # Slew async thread
        self._slew_thread: threading.Thread | None = None

        # Focuser 状态
        self._focuser_connected = False
        self._focuser_position = 100  # 当前焦点位置
        self._focuser_max_step = 320
        self._focuser_is_moving = False
        self._focuser_name = "AstroHub PTZ Focuser"
        self._focuser_description = "AstroHub PTZ Zoom mapped to ASCOM Focuser"
        self._focuser_driver_version = "2.0.0"
        self._focuser_temp_comp = False

        # FilterWheel 状态
        self._filter_connected = False
        self._filter_position = 0  # 0=day(IR-cut off), 1=night(IR-cut on)
        self._filter_num_positions = 2
        self._filter_name = "AstroHub PTZ IRCut"
        self._filter_description = "AstroHub PTZ IRCUT 日夜切换 mapped to ASCOM FilterWheel"
        self._filter_driver_version = "2.0.0"

        # Tracking mode
        # TrackSidereal=1, TrackLunar=2, TrackSolar=3, TrackOff=0
        self._scope_tracking_mode = 0

    # ---- Helpers ----
    def _resolve_device_ip(self) -> str | None:
        """从 PTZ manager 获取当前连接设备的 IP。"""
        if self._ptz_manager is None:
            return None
        try:
            for dev in self._ptz_manager.list_controllers():
                return dev
            return None
        except Exception:
            return None

    def _ptz_move_if_connected(self, func: Callable) -> bool:
        """If PTZ manager + device connected, call func, else just update state."""
        if self._ptz_manager is not None:
            try:
                ip = self._resolve_device_ip()
                if ip:
                    # Try to get a controller
                    ctrl, err = self._ptz_manager._get_controller(ip)
                    if ctrl is not None:
                        result = func(self._ptz_manager, ip)
                        return result
            except Exception as e:
                logger.warning("PTZ call via manager failed: %s", e)
        # Fallback: just update internal state
        return True

    # ---- Telescope methods ----
    def scope_slew_to_coordinates(self, ra: float, dec: float) -> None:
        """异步 Slew 到目标坐标。"""
        with self._lock:
            self._scope_target_ra = ra
            self._scope_target_dec = dec
            self._scope_slewing = True

        def _do_slew():
            try:
                result = self._ptz_move_if_connected(
                    lambda mgr, ip: mgr.ptz_absolute(
                        ip, pan=ra * 200.0, tilt=dec * 10.0, speed=50
                    )
                )
                if result:
                    with self._lock:
                        self._scope_ra = ra
                        self._scope_dec = dec
                        self._scope_slewing = False
                else:
                    with self._lock:
                        self._scope_slewing = False
            except Exception as e:
                logger.error("Slew failed: %s", e)
                with self._lock:
                    self._scope_slewing = False

        self._slew_thread = threading.Thread(target=_do_slew, daemon=True)
        self._slew_thread.start()

    def scope_abort_slew(self) -> bool:
        with self._lock:
            self._scope_slewing = False
        return True

    def scope_set_tracking(self, mode: int) -> None:
        """Set tracking mode: 0=Off, 1=Sidereal, 2=Lunar, 3=Solar."""
        with self._lock:
            self._scope_tracking_mode = mode
            self._scope_tracking = (mode != 0)
        if mode != 0 and self._ptz_manager:
            try:
                ip = self._resolve_device_ip()
                if ip:
                    # Enable PTZ continuous tracking simulation
                    pass  # PTZ tracking not directly supported via ISAPI
            except Exception as e:
                logger.warning("Set tracking mode failed: %s", e)

    # ---- Focuser methods ----
    def focuser_move(self, position: int) -> bool:
        """Move focuser to position."""
        with self._lock:
            if position < 0 or position > self._focuser_max_step:
                return False
            self._focuser_position = position
            self._focuser_is_moving = True

        def _do_move():
            try:
                result = self._ptz_move_if_connected(
                    lambda mgr, ip: mgr.ptz_absolute(
                        ip, zoom=position, speed=50
                    )
                )
                with self._lock:
                    self._focuser_is_moving = False
            except Exception as e:
                logger.error("Focuser move failed: %s", e)
                with self._lock:
                    self._focuser_is_moving = False

        threading.Thread(target=_do_move, daemon=True).start()
        return True

    # ---- FilterWheel methods ----
    def filter_set_position(self, position: int) -> bool:
        """Set filter position: 0=day mode, 1=night mode."""
        with self._lock:
            if position < 0 or position >= self._filter_num_positions:
                return False
            self._filter_position = position
        return True


class AlpacaHandler(BaseHTTPRequestHandler):
    """ASCOM Alpaca HTTP 请求处理器。"""

    state: AlpacaState = None  # type: ignore[assignment]

    def log_message(self, format, *args):  # noqa: A002
        logger.debug("Alpaca: %s", format % args)

    def _send_json(self, data: dict, status_code: int = 200) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        response_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.wfile.write(response_bytes)

    def _get_client_transaction_id(self) -> int:
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                body = self.rfile.read(content_length)
                data = json.loads(body)
                return data.get("ClientTransactionID", 0)
        except Exception:
            pass
        return 0

    def _read_body(self) -> dict:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 0:
            body = self.rfile.read(content_length)
            return json.loads(body)
        return {}

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, PUT, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        path = self.path.rstrip("/")
        path_parts = path.lstrip("/").split("/")

        try:
            # /management/v1/api
            if path == "/management/v1/api":
                self._send_json({
                    "Value": {
                        "DeviceRouteNotSupported": False,
                        "MaximumServerTransactions": 100,
                        "ServerDescription": "AstroHub v2.0 Alpaca Server",
                    },
                    "ServerTransactionID": 0,
                    "ClientTransactionID": 0,
                    "ErrorNumber": 0,
                    "ErrorMessage": "",
                })
                return

            # /management/v1/apidevices
            if path == "/management/v1/apidevices":
                self._handle_api_devices()
                return

            # DeviceType-specific routes
            if len(path_parts) >= 3:
                device_type = path_parts[0]
                device_number = int(path_parts[1])
                action = "/".join(path_parts[2:])
                client_tid = self._get_client_transaction_id()
                self._handle_device_get(device_type, device_number, action, client_tid)
                return

            # Fallback: unsupported route
            self._send_json(AlpacaResponse.error(
                1025, "Route not supported", 0
            ), 404)

        except Exception as e:
            logger.error("Alpaca GET error: %s\n%s", e, traceback.format_exc())
            self._send_json(AlpacaResponse.error(1024, str(e), 0), 500)

    def do_PUT(self) -> None:
        path = self.path.rstrip("/")
        path_parts = path.lstrip("/").split("/")

        try:
            if len(path_parts) >= 3:
                device_type = path_parts[0]
                device_number = int(path_parts[1])
                action = "/".join(path_parts[2:])
                body = self._read_body()
                client_tid = body.get("ClientTransactionID", 0)
                self._handle_device_put(device_type, device_number, action, body, client_tid)
                return

            self._send_json(AlpacaResponse.error(1025, "Route not supported", 0), 404)

        except Exception as e:
            logger.error("Alpaca PUT error: %s\n%s", e, traceback.format_exc())
            self._send_json(AlpacaResponse.error(1024, str(e), 0), 500)

    # ---- Management routes ----
    def _handle_api_devices(self) -> None:
        state = self.server.state
        devices = []

        if state._scope_connected:
            devices.append({
                "DeviceType": "Telescope",
                "DeviceNumber": 0,
                "DeviceName": state._scope_name,
                "DriverVersion": state._scope_driver_version,
            })

        if state._focuser_connected:
            devices.append({
                "DeviceType": "Focuser",
                "DeviceNumber": 0,
                "DeviceName": state._focuser_name,
                "DriverVersion": state._focuser_driver_version,
            })

        if state._filter_connected:
            devices.append({
                "DeviceType": "FilterWheel",
                "DeviceNumber": 0,
                "DeviceName": state._filter_name,
                "DriverVersion": state._filter_driver_version,
            })

        self._send_json(AlpacaResponse.ok(value=devices))

    # ---- Telescope commands ----
    def _handle_device_get(self, device_type: str, device_number: int, action: str, client_tid: int) -> None:
        state = self.server.state

        if device_type == "telescope":
            self._handle_telescope_get(action, client_tid)
        elif device_type == "focuser":
            self._handle_focuser_get(action, client_tid)
        elif device_type == "filterwheel":
            self._handle_filterwheel_get(action, client_tid)
        else:
            self._send_json(AlpacaResponse.error(1025, f"Unknown device type: {device_type}", client_tid), 404)

    def _handle_device_put(self, device_type: str, device_number: int, action: str, body: dict, client_tid: int) -> None:
        state = self.server.state

        if device_type == "telescope":
            self._handle_telescope_put(action, body, client_tid)
        elif device_type == "focuser":
            self._handle_focuser_put(action, body, client_tid)
        elif device_type == "filterwheel":
            self._handle_filterwheel_put(action, body, client_tid)
        else:
            self._send_json(AlpacaResponse.error(1025, f"Unknown device type: {device_type}", client_tid), 404)

    # ---- Telescope ----
    def _handle_telescope_get(self, action: str, client_tid: int) -> None:
        state = self.server.state
        with state._lock:
            if not state._scope_connected:
                self._send_json(AlpacaResponse.error(1031, "Device not connected", client_tid))
                return

        actions = {
            "connected": lambda: AlpacaResponse.ok(state._scope_connected, client_tid),
            "name": lambda: AlpacaResponse.ok(state._scope_name, client_tid),
            "description": lambda: AlpacaResponse.ok(state._scope_description, client_tid),
            "driverversion": lambda: AlpacaResponse.ok(state._scope_driver_version, client_tid),
            "slewing": lambda: AlpacaResponse.ok(state._scope_slewing, client_tid),
            "rightascension": lambda: AlpacaResponse.ok(state._scope_ra, client_tid),
            "declination": lambda: AlpacaResponse.ok(state._scope_dec, client_tid),
            "targetrightascension": lambda: AlpacaResponse.ok(state._scope_target_ra, client_tid),
            "targetdeclination": lambda: AlpacaResponse.ok(state._scope_target_dec, client_tid),
            "tracking": lambda: AlpacaResponse.ok(state._scope_tracking, client_tid),
            "trackingmode": lambda: AlpacaResponse.ok(state._scope_tracking_mode, client_tid),
            "canpark": lambda: AlpacaResponse.ok(False, client_tid),
            "canslew": lambda: AlpacaResponse.ok(True, client_tid),
            "canslewasync": lambda: AlpacaResponse.ok(True, client_tid),
            "cansettrack": lambda: AlpacaResponse.ok(True, client_tid),
            "canfindhome": lambda: AlpacaResponse.ok(False, client_tid),
            "canpause": lambda: AlpacaResponse.ok(False, client_tid),
            "atpark": lambda: AlpacaResponse.ok(False, client_tid),
            "alignmentmode": lambda: AlpacaResponse.ok(0, client_tid),
            "aperturearea": lambda: AlpacaResponse.ok(0.0, client_tid),
            "aperturediameter": lambda: AlpacaResponse.ok(0.0, client_tid),
            "focallength": lambda: AlpacaResponse.ok(0.0, client_tid),
            "sitelatitude": lambda: AlpacaResponse.ok(39.9042, client_tid),
            "sitelongitude": lambda: AlpacaResponse.ok(116.4074, client_tid),
            "siteelevation": lambda: AlpacaResponse.ok(50.0, client_tid),
            "sideofpier": lambda: AlpacaResponse.ok(1, client_tid),
        }

        handler = actions.get(action.lower())
        if handler:
            self._send_json(handler())
        else:
            self._send_json(AlpacaResponse.error(1025, f"Unknown telescope action: {action}", client_tid), 404)

    def _handle_telescope_put(self, action: str, body: dict, client_tid: int) -> None:
        state = self.server.state
        with state._lock:
            if not state._scope_connected and action.lower() != "connected":
                self._send_json(AlpacaResponse.error(1031, "Device not connected", client_tid))
                return

        action_lower = action.lower()
        if action_lower == "connected":
            with state._lock:
                state._scope_connected = bool(body.get("Connected", False))
            self._send_json(AlpacaResponse.ok(state._scope_connected, client_tid))
        elif action_lower == "slewtoaltaz":
            alt = body.get("Altitude", 45.0)
            az = body.get("Azimuth", 180.0)
            ra = az / 15.0  # rough conversion
            dec = alt
            state.scope_slew_to_coordinates(max(0, ra), max(-90, min(90, dec)))
            self._send_json(AlpacaResponse.ok(True, client_tid))
        elif action_lower == "slewtocoordinates":
            ra = body.get("RightAscension", 12.0)
            dec = body.get("Declination", 45.0)
            state.scope_slew_to_coordinates(ra, dec)
            self._send_json(AlpacaResponse.ok(True, client_tid))
        elif action_lower == "abortslew":
            state.scope_abort_slew()
            self._send_json(AlpacaResponse.ok(True, client_tid))
        elif action_lower == "track":
            enable = body.get("Track", True)
            tracking_mode = state._scope_tracking_mode if enable else 0
            state.scope_set_tracking(tracking_mode)
            self._send_json(AlpacaResponse.ok(True, client_tid))
        elif action_lower == "trackingmode":
            mode = body.get("TrackRate", 1)
            state.scope_set_tracking(mode)
            self._send_json(AlpacaResponse.ok(True, client_tid))
        else:
            self._send_json(AlpacaResponse.error(1025, f"Unknown telescope PUT: {action}", client_tid), 404)

    # ---- Focuser ----
    def _handle_focuser_get(self, action: str, client_tid: int) -> None:
        state = self.server.state
        with state._lock:
            if not state._focuser_connected:
                self._send_json(AlpacaResponse.error(1031, "Device not connected", client_tid))
                return

        actions = {
            "connected": lambda: AlpacaResponse.ok(state._focuser_connected, client_tid),
            "name": lambda: AlpacaResponse.ok(state._focuser_name, client_tid),
            "description": lambda: AlpacaResponse.ok(state._focuser_description, client_tid),
            "driverversion": lambda: AlpacaResponse.ok(state._focuser_driver_version, client_tid),
            "position": lambda: AlpacaResponse.ok(state._focuser_position, client_tid),
            "ismoving": lambda: AlpacaResponse.ok(state._focuser_is_moving, client_tid),
            "maxstep": lambda: AlpacaResponse.ok(state._focuser_max_step, client_tid),
            "maxincrement": lambda: AlpacaResponse.ok(state._focuser_max_step, client_tid),
            "stepsize": lambda: AlpacaResponse.ok(1, client_tid),
            "canabsolutemove": lambda: AlpacaResponse.ok(True, client_tid),
            "canrelativemove": lambda: AlpacaResponse.ok(True, client_tid),
            "tempcomp": lambda: AlpacaResponse.ok(state._focuser_temp_comp, client_tid),
            "tempcompavailable": lambda: AlpacaResponse.ok(False, client_tid),
        }

        handler = actions.get(action.lower())
        if handler:
            self._send_json(handler())
        else:
            self._send_json(AlpacaResponse.error(1025, f"Unknown focuser action: {action}", client_tid), 404)

    def _handle_focuser_put(self, action: str, body: dict, client_tid: int) -> None:
        state = self.server.state
        with state._lock:
            if not state._focuser_connected and action.lower() != "connected":
                self._send_json(AlpacaResponse.error(1031, "Device not connected", client_tid))
                return

        action_lower = action.lower()
        if action_lower == "connected":
            with state._lock:
                state._focuser_connected = bool(body.get("Connected", False))
            self._send_json(AlpacaResponse.ok(state._focuser_connected, client_tid))
        elif action_lower == "move":
            position = body.get("Position", 0)
            with state._lock:
                position = max(0, min(position, state._focuser_max_step))
            success = state.focuser_move(position)
            self._send_json(AlpacaResponse.ok(success, client_tid))
        elif action_lower == "tempcomp":
            with state._lock:
                state._focuser_temp_comp = bool(body.get("TempComp", False))
            self._send_json(AlpacaResponse.ok(True, client_tid))
        else:
            self._send_json(AlpacaResponse.error(1025, f"Unknown focuser PUT: {action}", client_tid), 404)

    # ---- FilterWheel ----
    def _handle_filterwheel_get(self, action: str, client_tid: int) -> None:
        state = self.server.state
        with state._lock:
            if not state._filter_connected:
                self._send_json(AlpacaResponse.error(1031, "Device not connected", client_tid))
                return

        actions = {
            "connected": lambda: AlpacaResponse.ok(state._filter_connected, client_tid),
            "name": lambda: AlpacaResponse.ok(state._filter_name, client_tid),
            "description": lambda: AlpacaResponse.ok(state._filter_description, client_tid),
            "driverversion": lambda: AlpacaResponse.ok(state._filter_driver_version, client_tid),
            "position": lambda: AlpacaResponse.ok(state._filter_position, client_tid),
            "numpositions": lambda: AlpacaResponse.ok(state._filter_num_positions, client_tid),
            "cansetoffset": lambda: AlpacaResponse.ok(False, client_tid),
            "offsets": lambda: AlpacaResponse.ok([], client_tid),
        }

        handler = actions.get(action.lower())
        if handler:
            self._send_json(handler())
        else:
            self._send_json(AlpacaResponse.error(1025, f"Unknown filterwheel action: {action}", client_tid), 404)

    def _handle_filterwheel_put(self, action: str, body: dict, client_tid: int) -> None:
        state = self.server.state
        with state._lock:
            if not state._filter_connected and action.lower() != "connected":
                self._send_json(AlpacaResponse.error(1031, "Device not connected", client_tid))
                return

        action_lower = action.lower()
        if action_lower == "connected":
            with state._lock:
                state._filter_connected = bool(body.get("Connected", False))
            self._send_json(AlpacaResponse.ok(state._filter_connected, client_tid))
        elif action_lower == "position":
            position = body.get("Position", 0)
            success = state.filter_set_position(position)
            self._send_json(AlpacaResponse.ok(success, client_tid))
        else:
            self._send_json(AlpacaResponse.error(1025, f"Unknown filterwheel PUT: {action}", client_tid), 404)


def create_alpaca_server(host: str = "localhost", port: int = 5555,
                         ptz_manager: Any = None) -> HTTPServer:
    """创建 ASCOM Alpaca HTTP Server。"""
    server = HTTPServer((host, port), AlpacaHandler)
    state = AlpacaState(ptz_manager=ptz_manager)
    
    # Auto-connect all devices on server creation
    state._scope_connected = True
    state._focuser_connected = True
    state._filter_connected = True
    
    server.state = state
    logger.info("ASCOM Alpaca Server 已创建: http://%s:%d", host, port)
    return server


def run_alpaca_server(host: str = "localhost", port: int = 5555,
                      ptz_manager: Any = None, stop_event: threading.Event | None = None) -> None:
    """运行 ASCOM Alpaca HTTP Server。"""
    logger.info("ASCOM Alpaca Server 启动中: http://%s:%d", host, port)
    server = create_alpaca_server(host, port, ptz_manager)
    
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    logger.info("ASCOM Alpaca Server 已运行: http://%s:%d", host, port)
    
    if stop_event:
        try:
            while not stop_event.is_set():
                stop_event.wait(timeout=1)
        except KeyboardInterrupt:
            pass
        server.shutdown()
        logger.info("ASCOM Alpaca Server 已停止")
    else:
        server.serve_forever()
