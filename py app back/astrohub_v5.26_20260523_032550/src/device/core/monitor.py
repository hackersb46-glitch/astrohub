"""
M2 Device Manager v1.0 - 设备状态监控

实现设备在线检测(P1.1)、心跳探测(P1.2)、心跳间隔配置(P1.3)、
状态变更通知(P1.4)、异常分类告警(P1.5)。

提供 DeviceMonitor 类，负责：
- 对多个设备进行周期性心跳探测
- 连续3次检测确认状态变更(防抖动)
- 状态变化时触发回调通知
- 异常类型分类(认证失败/连接超时/设备故障/网络不可达)
- 可配置心跳周期(5-300秒)，运行时即时生效

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, Thread, Event
from typing import Callable, Any

from device.constants import (
    ONLINE_CHECK_TIMEOUT,
    ONLINE_CHECK_ENDPOINT,
    HEARTBEAT_DEFAULT_INTERVAL,
    HEARTBEAT_MIN_INTERVAL,
    HEARTBEAT_MAX_INTERVAL,
    HEARTBEAT_CONSECUTIVE_THRESHOLD,
    AnomalyType,
    AlertLevel,
    HeartbeatStatus,
)
from device.core.logger import LOG
from device.core.status_history import StatusHistory
from device.core.storage import JsonStore, _atomic_write
from device.isapi.client import ISAPIClient, ISAPIResponse
from device.models.schemas import HeartbeatConfig, HeartbeatStatusResponse, AlertResponse


# ------------------------------------------------------------------ #
#  异常告警分类 (P1.5)
# ------------------------------------------------------------------ #

class AnomalyClassifier:
    """异常分类器(P1.5)。

    根据HTTP状态码和错误信息，将异常映射为告警级别和异常类型。

    分类规则:
        - 401 → AlertLevel.ERROR,  AnomalyType.AUTH_FAILED
        - 500 → AlertLevel.ERROR,  AnomalyType.DEVICE_FAULT
        - 503 → AlertLevel.WARNING, AnomalyType.DEVICE_FAULT
        - 0 (超时/连接失败) → AlertLevel.CRITICAL, AnomalyType.CONNECTION_TIMEOUT
        - 其他 → AlertLevel.WARNING, AnomalyType.NETWORK_UNREACHABLE
    """

    # HTTP状态码 → (告警级别, 异常类型) 映射
    _MAPPING: dict[int, tuple[AlertLevel, AnomalyType]] = {
        401: (AlertLevel.ERROR, AnomalyType.AUTH_FAILED),
        403: (AlertLevel.ERROR, AnomalyType.AUTH_FAILED),
        500: (AlertLevel.ERROR, AnomalyType.DEVICE_FAULT),
        502: (AlertLevel.WARNING, AnomalyType.DEVICE_FAULT),
        503: (AlertLevel.WARNING, AnomalyType.DEVICE_FAULT),
        0: (AlertLevel.CRITICAL, AnomalyType.CONNECTION_TIMEOUT),
    }

    @classmethod
    def classify(cls, status_code: int, error_string: str = "") -> tuple[AlertLevel, AnomalyType, str]:
        """分类异常，返回告警级别、异常类型、详细描述。

        Args:
            status_code: HTTP状态码，0=超时/连接失败
            error_string: 错误描述字符串

        Returns:
            (AlertLevel, AnomalyType, description) 三元组
        """
        alert_level, anomaly_type = cls._MAPPING.get(
            status_code,
            (AlertLevel.WARNING, AnomalyType.NETWORK_UNREACHABLE),
        )

        description = cls._build_description(anomaly_type, status_code, error_string)
        return alert_level, anomaly_type, description

    @staticmethod
    def _build_description(anomaly_type: AnomalyType, status_code: int, error_string: str) -> str:
        """构建异常描述。

        Args:
            anomaly_type: 异常类型
            status_code: HTTP状态码
            error_string: 错误描述

        Returns:
            人类可读的异常描述
        """
        descriptions = {
            AnomalyType.AUTH_FAILED: f"认证失败 (HTTP {status_code}) - 请检查用户名/密码",
            AnomalyType.CONNECTION_TIMEOUT: f"连接超时 - 设备无响应 (error: {error_string or 'timeout'})",
            AnomalyType.DEVICE_FAULT: f"设备故障 (HTTP {status_code}) - {error_string or '设备内部错误'}",
            AnomalyType.NETWORK_UNREACHABLE: f"网络不可达 (HTTP {status_code}) - {error_string or '路由不通'}",
        }
        return descriptions.get(anomaly_type, f"未知异常 (HTTP {status_code})")


# ------------------------------------------------------------------ #
#  心跳设备状态追踪
# ------------------------------------------------------------------ #

class DeviceHeartbeatState:
    """单个设备的心跳状态追踪器。

    维护设备的心跳检测历史、连续在线/离线计数器、最近响应时间等。
    线程安全，通过 Lock 保护。

    Attributes:
        mac: 设备MAC地址
        consecutive_online: 连续在线检测次数
        consecutive_offline: 连续离线检测次数
        last_status: 当前确认的心跳状态(online/offline)
        last_check_time: 上次心跳检查时间(ISO格式)
        last_response_time_ms: 上次响应时间(毫秒)
        status_since: 当前状态生效的时间(ISO格式)
    """

    def __init__(self, mac: str) -> None:
        self.mac = mac
        self.consecutive_online: int = 0
        self.consecutive_offline: int = 0
        self.last_status: HeartbeatStatus = HeartbeatStatus.OFFLINE
        self.last_check_time: str = ""
        self.last_response_time_ms: float = 0.0
        self.status_since: str = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        self._lock = Lock()

    def record_check(self, online: bool, response_time_ms: float) -> tuple[bool, HeartbeatStatus | None]:
        """记录一次心跳检测结果。

        Args:
            online: 本次检测是否在线
            response_time_ms: 本次响应时间(毫秒)

        Returns:
            (状态是否变更, 新状态或None) 二元组。状态变更指跨越了连续阈值。
        """
        with self._lock:
            self.last_check_time = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
            self.last_response_time_ms = response_time_ms

            if online:
                self.consecutive_online += 1
                self.consecutive_offline = 0
            else:
                self.consecutive_offline += 1
                self.consecutive_online = 0

            new_status: HeartbeatStatus | None = None

            # 连续阈值触发状态变更
            if online and self.consecutive_online >= HEARTBEAT_CONSECUTIVE_THRESHOLD:
                if self.last_status != HeartbeatStatus.ONLINE:
                    self.last_status = HeartbeatStatus.ONLINE
                    self.status_since = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
                    new_status = HeartbeatStatus.ONLINE
            elif not online and self.consecutive_offline >= HEARTBEAT_CONSECUTIVE_THRESHOLD:
                if self.last_status != HeartbeatStatus.OFFLINE:
                    self.last_status = HeartbeatStatus.OFFLINE
                    self.status_since = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
                    new_status = HeartbeatStatus.OFFLINE

            return new_status is not None, new_status

    def get_consecutive_count(self) -> int:
        """获取当前方向(确认状态的方向)的连续计数。

        Returns:
            在线方向返回 consecutive_online，离线方向返回 consecutive_offline
        """
        with self._lock:
            return self.consecutive_online if self.last_status == HeartbeatStatus.ONLINE else self.consecutive_offline

    def get_status_response(self) -> HeartbeatStatusResponse:
        """构建 HeartbeatStatusResponse(P1.4)。

        Returns:
            心跳状态响应对象
        """
        with self._lock:
            return HeartbeatStatusResponse(
                mac=self.mac,
                status=self.last_status.value,
                since=self.status_since,
                last_check=self.last_check_time,
                consecutive_checks=self.get_consecutive_count(),
            )

    def to_dict(self) -> dict:
        """序列化状态为字典。

        Returns:
            状态字典(用于持久化)
        """
        return {
            "mac": self.mac,
            "consecutive_online": self.consecutive_online,
            "consecutive_offline": self.consecutive_offline,
            "last_status": self.last_status.value,
            "last_check_time": self.last_check_time,
            "last_response_time_ms": self.last_response_time_ms,
            "status_since": self.status_since,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DeviceHeartbeatState:
        """从字典反序列化状态。

        Args:
            data: 状态字典

        Returns:
            恢复的 DeviceHeartbeatState 实例
        """
        state = cls(data["mac"])
        state.consecutive_online = data.get("consecutive_online", 0)
        state.consecutive_offline = data.get("consecutive_offline", 0)
        state.last_status = HeartbeatStatus(data.get("last_status", "offline"))
        state.last_check_time = data.get("last_check_time", "")
        state.last_response_time_ms = data.get("last_response_time_ms", 0.0)
        state.status_since = data.get("status_since", state.status_since)
        return state


# ------------------------------------------------------------------ #
#  P1.1 ~ P1.5 - DeviceMonitor
# ------------------------------------------------------------------ #

class DeviceMonitor:
    """设备状态监控器(P1.1 ~ P1.5)。

    管理多个设备的心跳探测循环，提供：
        - 在线检测(P1.1): 通过 HTTP GET /ISAPI/System/deviceInfo 检测设备可达性
        - 心跳探测(P1.2): 周期性发送轻量请求，连续3次无响应标记离线
        - 心跳间隔配置(P1.3): 支持运行时调整，范围5-300秒
        - 状态变更通知(P1.4): 检测到状态变化时触发回调
        - 异常分类告警(P1.5): 区分认证失败/连接超时/设备故障/网络不可达

    Args:
        heartbeat_interval: 心跳检测间隔(秒)，默认30，范围5-300
        check_timeout: 单次检测超时时间(秒)，默认5
        status_history: 状态历史记录器实例(可选)
        heartbeat_state_file: 心跳状态持久化文件路径(可选)
    """

    def __init__(
        self,
        heartbeat_interval: int = HEARTBEAT_DEFAULT_INTERVAL,
        check_timeout: int = ONLINE_CHECK_TIMEOUT,
        status_history: StatusHistory | None = None,
        heartbeat_state_file: str | Path | None = None,
    ) -> None:
        self._heartbeat_interval = self._validate_interval(heartbeat_interval)
        self._check_timeout = check_timeout
        self._status_history = status_history or StatusHistory()

        # 心跳状态持久化
        self._state_path: Path = Path(heartbeat_state_file) if heartbeat_state_file else Path(__file__).resolve().parent / "data" / "heartbeat_states.json"
        self._state_path.parent.mkdir(parents=True, exist_ok=True)

        # 设备注册: mac -> (ip, username, password, port)
        self._devices: dict[str, dict[str, Any]] = {}
        # 设备心跳状态: mac -> DeviceHeartbeatState
        self._heartbeat_states: dict[str, DeviceHeartbeatState] = {}
        # 状态变更回调列表
        self._callbacks: list[Callable[[str, str, str, dict], None]] = []
        # 异常告警回调列表
        self._alert_callbacks: list[Callable[[AlertResponse], None]] = []

        # 线程控制
        self._monitor_thread: Thread | None = None
        self._stop_event = Event()
        self._lock = Lock()

        # 加载已持久化的心跳状态
        self._load_heartbeat_states()

        LOG.info(
            f"DeviceMonitor 初始化: interval={self._heartbeat_interval}s, "
            f"timeout={self._check_timeout}s"
        )

    # ------------------------------------------------------------------ #
    #  心跳间隔配置 (P1.3)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _validate_interval(interval: int) -> int:
        """验证心跳间隔是否在合法范围内。

        Args:
            interval: 心跳间隔(秒)

        Returns:
            合法的心跳间隔

        Raises:
            ValueError: 如果间隔不在5-300范围内
        """
        if interval < HEARTBEAT_MIN_INTERVAL or interval > HEARTBEAT_MAX_INTERVAL:
            raise ValueError(
                f"心跳间隔必须在 {HEARTBEAT_MIN_INTERVAL}-{HEARTBEAT_MAX_INTERVAL} 秒之间, 当前值: {interval}"
            )
        return interval

    @property
    def heartbeat_interval(self) -> int:
        """获取当前心跳间隔(秒)。"""
        return self._heartbeat_interval

    def update_heartbeat_interval(self, interval: int) -> int:
        """更新心跳间隔(P1.3)。修改后下次心跳立即按新间隔执行。

        Args:
            interval: 新的间隔(秒)

        Returns:
            更新后的间隔值

        Raises:
            ValueError: 间隔不合法
        """
        new_interval = self._validate_interval(interval)
        old_interval = self._heartbeat_interval
        with self._lock:
            self._heartbeat_interval = new_interval
        LOG.done(f"心跳间隔已更新: {old_interval}s → {new_interval}s")
        return new_interval

    def get_heartbeat_config(self) -> HeartbeatConfig:
        """获取当前心跳配置。

        Returns:
            心跳配置模型
        """
        return HeartbeatConfig(interval=self._heartbeat_interval)

    # ------------------------------------------------------------------ #
    #  设备注册/注销
    # ------------------------------------------------------------------ #

    def register_device(self, mac: str, ip: str, username: str, password: str, port: int = 80) -> None:
        """注册设备到监控列表。

        Args:
            mac: 设备MAC地址
            ip: 设备IP地址
            username: 登录用户名
            password: 登录密码
            port: HTTP端口，默认80
        """
        with self._lock:
            self._devices[mac] = {
                "ip": ip,
                "username": username,
                "password": password,
                "port": port,
            }
            # 恢复或初始化心跳状态
            if mac not in self._heartbeat_states:
                self._heartbeat_states[mac] = DeviceHeartbeatState(mac)

        LOG.info(f"设备已注册到监控: mac={mac}, ip={ip}:{port}")

    def unregister_device(self, mac: str) -> bool:
        """从监控列表移除设备。

        Args:
            mac: 设备MAC地址

        Returns:
            True=移除成功, False=设备不在监控列表中
        """
        with self._lock:
            if mac not in self._devices:
                return False
            del self._devices[mac]
            del self._heartbeat_states[mac]

        LOG.info(f"设备已从监控移除: mac={mac}")
        return True

    def is_monitored(self, mac: str) -> bool:
        """检查设备是否在监控列表中。

        Args:
            mac: 设备MAC地址

        Returns:
            True=在监控中, False=不在
        """
        return mac in self._devices

    # ------------------------------------------------------------------ #
    #  P1.1 - 在线检测
    # ------------------------------------------------------------------ #

    def check_device_online(self, mac: str) -> dict:
        """立即检测单个设备的在线状态(P1.1)。

        通过 HTTP GET /ISAPI/System/deviceInfo 检测设备可达性。

        Args:
            mac: 设备MAC地址

        Returns:
            检测结果:
            {
                "mac": str,
                "online": bool,
                "status_code": int,
                "response_time_ms": float,
                "details": str,
                "checked_at": str
            }

        Raises:
            ValueError: 设备不在监控列表中
        """
        with self._lock:
            device = self._devices.get(mac)
            if device is None:
                raise ValueError(f"设备未注册到监控: {mac}")

            client = self._build_client(mac)

        result = self._execute_check(mac, client)
        LOG.info(f"在线检测: {mac} → {'在线' if result['online'] else '离线'} ({result['response_time_ms']:.0f}ms)")
        return result

    def _build_client(self, mac: str) -> ISAPIClient:
        """为指定设备构建ISAPI客户端(在锁保护下调用)。

        Args:
            mac: 设备MAC地址

        Returns:
            配置好的ISAPIClient实例
        """
        device = self._devices[mac]
        return ISAPIClient(
            ip=device["ip"],
            username=device["username"],
            password=device["password"],
            port=device["port"],
            timeout=self._check_timeout,
        )

    def _execute_check(self, mac: str, client: ISAPIClient) -> dict:
        """执行单次在线检测。

        Args:
            mac: 设备MAC地址
            client: ISAPI客户端

        Returns:
            检测结果字典
        """
        response = client.get(ONLINE_CHECK_ENDPOINT)
        online = response.status_code == 200

        details = self._build_check_details(response, online)

        # 记录心跳并检测状态变更
        status_changed, new_status = self._heartbeat_states[mac].record_check(
            online=online,
            response_time_ms=response.response_time_ms,
        )

        if status_changed:
            self._on_status_change(mac, new_status)

        # 异常分类告警 (P1.5)
        if not online:
            self._classify_and_alert(mac, response)

        return {
            "mac": mac,
            "online": online,
            "status_code": response.status_code,
            "response_time_ms": response.response_time_ms,
            "details": details,
            "checked_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        }

    @staticmethod
    def _build_check_details(response: ISAPIResponse, online: bool) -> str:
        """构建检测详情字符串。

        Args:
            response: ISAPI响应
            online: 是否在线

        Returns:
            详情描述
        """
        if online:
            return "设备可达，响应正常"
        if response.status_code == 0:
            return f"设备不可达或超时: {response.error_string}"
        if response.status_code == 401:
            return "认证失败 - 用户名/密码错误"
        if response.status_code >= 500:
            return f"设备故障 (HTTP {response.status_code})"
        return f"HTTP {response.status_code}: {response.error_string}"

    # ------------------------------------------------------------------ #
    #  P1.2 - 心跳探测循环
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        """启动心跳监控后台线程。

        如果监控线程已在运行，则忽略调用。
        """
        if self._monitor_thread is not None and self._monitor_thread.is_alive():
            LOG.warning("心跳监控已在运行中")
            return

        self._stop_event.clear()
        self._monitor_thread = Thread(
            target=self._heartbeat_loop,
            name="m2-heartbeat-monitor",
            daemon=True,
        )
        self._monitor_thread.start()
        LOG.info(f"心跳监控已启动: interval={self._heartbeat_interval}s, devices={len(self._devices)}")

    def stop(self) -> None:
        """停止心跳监控后台线程。

        设置停止信号后等待线程退出(最多等待2倍心跳间隔)。
        """
        if self._monitor_thread is None:
            return

        self._stop_event.set()
        timeout = max(self._heartbeat_interval * 2, 10)
        self._monitor_thread.join(timeout=timeout)
        if self._monitor_thread.is_alive():
            LOG.warning("心跳监控线程未在预期时间内退出")
        else:
            LOG.info("心跳监控已停止")
        self._monitor_thread = None
        # 持久化当前状态
        self._save_heartbeat_states()

    @property
    def is_running(self) -> bool:
        """监控是否正在运行。

        Returns:
            True=运行中, False=已停止
        """
        return self._monitor_thread is not None and self._monitor_thread.is_alive()

    def _heartbeat_loop(self) -> None:
        """心跳探测主循环。

        每隔 heartbeat_interval 秒对所有注册设备执行一次在线检测。
        循环在 stop_event 被设置时退出。
        """
        LOG.info(f"心跳循环已启动，探测 {len(self._devices)} 台设备")

        while not self._stop_event.is_set():
            # 获取当前间隔快照(支持运行时更新)
            with self._lock:
                interval = self._heartbeat_interval
                device_macs = list(self._devices.keys())

            if not device_macs:
                # 没有设备需要监控，等待后继续
                self._stop_event.wait(timeout=interval)
                continue

            for mac in device_macs:
                if self._stop_event.is_set():
                    break

                try:
                    with self._lock:
                        client = self._build_client(mac)
                    self._execute_check(mac, client)
                except Exception as e:
                    LOG.error(f"心跳检测异常: {mac} - {e}")
                    # 将异常视为离线
                    try:
                        self._heartbeat_states[mac].record_check(online=False, response_time_ms=0.0)
                    except KeyError:
                        pass

            # 等待下一个周期(可被 stop_event 中断)
            self._stop_event.wait(timeout=interval)
            # 持久化状态
            self._save_heartbeat_states()

    # ------------------------------------------------------------------ #
    #  P1.4 - 状态变更通知
    # ------------------------------------------------------------------ #

    def on_status_change(self, callback: Callable[[str, str, str, dict], None]) -> None:
        """注册状态变更回调(P1.4)。

        Args:
            callback: 回调函数，签名: (mac, old_status, new_status, context)
                - mac: 设备MAC地址
                - old_status: 旧状态 ('online' / 'offline')
                - new_status: 新状态 ('online' / 'offline')
                - context: 附加上下文 dict (包含 checked_at, response_time_ms 等)
        """
        with self._lock:
            self._callbacks.append(callback)
        LOG.info(f"状态变更回调已注册: 当前共 {len(self._callbacks)} 个")

    def on_alert(self, callback: Callable[[AlertResponse], None]) -> None:
        """注册异常告警回调(P1.5)。

        Args:
            callback: 回调函数，签名: (AlertResponse)
        """
        with self._lock:
            self._alert_callbacks.append(callback)
        LOG.info(f"异常告警回调已注册: 当前共 {len(self._alert_callbacks)} 个")

    def _on_status_change(self, mac: str, new_status: HeartbeatStatus) -> None:
        """处理状态变更(P1.4)。

        触发所有已注册的回调，并写入状态历史。

        Args:
            mac: 设备MAC地址
            new_status: 新的状态
        """
        with self._lock:
            state = self._heartbeat_states.get(mac)
            if state is None:
                return
            old_status = HeartbeatStatus.OFFLINE if new_status == HeartbeatStatus.ONLINE else HeartbeatStatus.ONLINE

        LOG.warning(
            f"设备状态变更: {mac} {old_status.value} → {new_status.value}"
        )

        # 写入状态历史(P1.6)
        self._status_history.record_entry(
            mac=mac,
            old_status=old_status.value,
            new_status=new_status.value,
            reason=f"心跳检测连续{HEARTBEAT_CONSECUTIVE_THRESHOLD}次确认",
        )

        # 更新 DeviceManager 的 heartbeat_status
        try:
            from device.core.device_manager import DeviceManager
            dm = DeviceManager()
            dm._store._lock.acquire()
            try:
                data = dm._store._read()
                record = data.get("records", {}).get(mac)
                if record:
                    record["heartbeat_status"] = new_status.value
                    dm._store._write(data)
            finally:
                dm._store._lock.release()
        except Exception as e:
            LOG.warning(f"更新设备 heartbeat_status 失败: {mac} - {e}")

        context = {
            "checked_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "response_time_ms": state.last_response_time_ms,
            "consecutive_checks": state.get_consecutive_count(),
        }

        # 触发所有回调
        callback_str = new_status.value
        old_status_str = old_status.value
        with self._lock:
            callbacks = list(self._callbacks)

        for cb in callbacks:
            try:
                cb(mac, old_status_str, callback_str, context)
            except Exception as e:
                LOG.error(f"状态变更回调执行异常: {mac} - {e}")

    # ------------------------------------------------------------------ #
    #  P1.5 - 异常分类告警
    # ------------------------------------------------------------------ #

    def _classify_and_alert(self, mac: str, response: ISAPIResponse) -> None:
        """对异常进行分类并触发告警(P1.5)。

        Args:
            mac: 设备MAC地址
            response: ISAPI响应
        """
        alert_level, anomaly_type, description = AnomalyClassifier.classify(
            response.status_code,
            response.error_string,
        )

        alert = AlertResponse(
            mac=mac,
            level=alert_level.value,
            anomaly_type=anomaly_type.value,
            timestamp=datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            description=description,
        )

        # 记录日志
        log_method = {
            AlertLevel.WARNING: LOG.warning,
            AlertLevel.ERROR: LOG.error,
            AlertLevel.CRITICAL: LOG.error,
        }.get(alert_level, LOG.warning)

        log_method(
            f"异常告警 [{alert_level.value}]: {alert.anomaly_type} - {mac} - {description}"
        )

        # 触发告警回调
        with self._lock:
            alert_callbacks = list(self._alert_callbacks)

        for cb in alert_callbacks:
            try:
                cb(alert)
            except Exception as e:
                LOG.error(f"异常告警回调执行异常: {mac} - {e}")

    # ------------------------------------------------------------------ #
    #  状态查询
    # ------------------------------------------------------------------ #

    def get_device_status(self, mac: str) -> HeartbeatStatusResponse:
        """获取设备的心跳状态。

        Args:
            mac: 设备MAC地址

        Returns:
            心跳状态响应

        Raises:
            ValueError: 设备不在监控列表中
        """
        with self._lock:
            if mac not in self._heartbeat_states:
                raise ValueError(f"设备不在监控中: {mac}")
            return self._heartbeat_states[mac].get_status_response()

    def get_all_statuses(self) -> list[HeartbeatStatusResponse]:
        """获取所有被监控设备的心跳状态。

        Returns:
            心跳状态响应列表
        """
        with self._lock:
            return [
                state.get_status_response()
                for state in self._heartbeat_states.values()
            ]

    def registered_count(self) -> int:
        """获取注册到监控的设备数量。

        Returns:
            设备数量
        """
        with self._lock:
            return len(self._devices)

    # ------------------------------------------------------------------ #
    #  持久化
    # ------------------------------------------------------------------ #

    def _save_heartbeat_states(self) -> None:
        """持久化当前心跳状态到磁盘。"""
        with self._lock:
            data = {
                mac: state.to_dict()
                for mac, state in self._heartbeat_states.items()
            }
        try:
            _atomic_write(self._state_path, data)
        except Exception as e:
            LOG.warning(f"心跳状态持久化失败: {e}")

    def _load_heartbeat_states(self) -> None:
        """从磁盘加载心跳状态。"""
        if not self._state_path.exists():
            return

        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            with self._lock:
                for mac, state_data in data.items():
                    self._heartbeat_states[mac] = DeviceHeartbeatState.from_dict(state_data)

            LOG.info(f"心跳状态已加载: {len(self._heartbeat_states)} 台设备")
        except Exception as e:
            LOG.warning(f"心跳状态加载失败: {e}")
