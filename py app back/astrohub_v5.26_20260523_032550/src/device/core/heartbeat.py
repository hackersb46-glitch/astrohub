"""
M2 Device Manager v1.0 - 心跳检测与恢复系统

实现基于 asyncio 的周期性心跳检测(P1.2/P1.3)。
支持可配置间隔(5-300秒)、连续失败判定(3次标记离线)、恢复自动上线。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from device.constants import (
    DeviceStatus,
    HEARTBEAT_CONSECUTIVE_THRESHOLD,
    HEARTBEAT_DEFAULT_INTERVAL,
    HEARTBEAT_MAX_INTERVAL,
    HEARTBEAT_MIN_INTERVAL,
    HeartbeatStatus,
    ONLINE_CHECK_ENDPOINT,
)
from device.core.logger import LOG
from device.core.storage import JsonStore
from device.isapi.client import ISAPIClient
from device.models.schemas import HeartbeatConfig, HeartbeatStatusResponse


# ------------------------------------------------------------------ #
#  HeartbeatStore - 心跳状态持久化
# ------------------------------------------------------------------ #

class HeartbeatStore:
    """心跳状态持久化存储，基于 JsonStore 封装。

    数据结构:
        {
            "meta": { ... },
            "records": {
                "{mac}": {
                    "mac": "...",
                    "status": "online|offline",
                    "last_heartbeat_at": "2026-05-05T10:00:00",
                    "consecutive_failures": 0,
                    "last_recovery_at": "2026-05-05T09:55:00",
                    "last_offline_at": "2026-05-05T09:54:30",
                },
                ...
            }
        }
    """

    def __init__(self, db_file: str | Path | None = None) -> None:
        """初始化心跳存储。

        Args:
            db_file: JSON数据库文件路径，默认使用 data/heartbeat.json
        """
        path = db_file or (Path(__file__).resolve().parent.parent / "data" / "heartbeat.json")
        self._store = JsonStore(path, default={"records": {}})
        LOG.info(f"HeartbeatStore 初始化完成: {path}")

    def get(self, mac: str) -> dict | None:
        """获取设备心跳状态记录。

        Args:
            mac: 设备的MAC地址

        Returns:
            心跳记录字典，不存在时返回 None
        """
        record = self._store.get(mac)
        if record is None:
            return None
        return {
            "mac": record.get("mac", mac),
            "status": record.get("status", HeartbeatStatus.OFFLINE.value),
            "last_heartbeat_at": record.get("last_heartbeat_at"),
            "consecutive_failures": record.get("consecutive_failures", 0),
            "last_recovery_at": record.get("last_recovery_at"),
            "last_offline_at": record.get("last_offline_at"),
        }

    def upsert(self, mac: str, **kwargs: Any) -> dict:
        """创建或更新设备心跳记录。

        Args:
            mac: 设备的MAC地址
            **kwargs: 要更新/设置的字段

        Returns:
            更新后的完整记录字典
        """
        existing = self._store.get(mac) or {}
        record: dict[str, Any] = {
            "mac": mac,
            "status": existing.get("status", HeartbeatStatus.OFFLINE.value),
            "last_heartbeat_at": existing.get("last_heartbeat_at"),
            "consecutive_failures": existing.get("consecutive_failures", 0),
            "last_recovery_at": existing.get("last_recovery_at"),
            "last_offline_at": existing.get("last_offline_at"),
        }
        record.update(kwargs)
        record["updated_at"] = datetime.now().isoformat()
        self._store.set(mac, record)
        return self.get(mac)

    def list_all(self) -> list[dict]:
        """获取所有设备的心跳记录。

        Returns:
            心跳记录列表
        """
        all_records = self._store.list_all()
        results: list[dict] = []
        for record in all_records:
            mac = record.get("mac", "")
            results.append({
                "mac": mac,
                "status": record.get("status", HeartbeatStatus.OFFLINE.value),
                "last_heartbeat_at": record.get("last_heartbeat_at"),
                "consecutive_failures": record.get("consecutive_failures", 0),
                "last_recovery_at": record.get("last_recovery_at"),
                "last_offline_at": record.get("last_offline_at"),
            })
        return results


# ------------------------------------------------------------------ #
#  HeartbeatEngine - 心跳引擎
# ------------------------------------------------------------------ #

class HeartbeatEngine:
    """心跳引擎：基于 asyncio 的周期性心跳检测与恢复管理。

    - 使用 ISAPI 接口探测设备在线状态
    - 连续 N 次失败后标记设备为 offline (N=HEARTBEAT_CONSECUTIVE_THRESHOLD)
    - 设备从 offline 恢复到 online 时记录 recovery time
    - 支持动态调整心跳间隔 (5-300秒)

    Args:
        interval: 心跳检测间隔(秒)，范围5-300，默认30
        store: HeartbeatStore 实例，默认创建新实例
        device_manager: DeviceManager 实例，用于同步 heartbeat_status
    """

    def __init__(
        self,
        interval: int = HEARTBEAT_DEFAULT_INTERVAL,
        store: HeartbeatStore | None = None,
        device_manager: Any = None,
    ) -> None:
        """初始化心跳引擎。

        Args:
            interval: 心跳间隔(秒)，范围5-300
            store: 心跳存储实例
            device_manager: 设备管理器实例（可选，用于同步设备状态）
        """
        self._interval = self._validate_interval(interval)
        self._store = store or HeartbeatStore()
        self._device_manager = device_manager
        self._running = False
        self._task: asyncio.Task | None = None
        LOG.info(
            f"HeartbeatEngine 初始化完成: "
            f"interval={self._interval}s, threshold={HEARTBEAT_CONSECUTIVE_THRESHOLD}"
        )

    @staticmethod
    def _validate_interval(interval: int) -> int:
        """校验心跳间隔是否在允许范围内。

        Args:
            interval: 待校验的间隔值

        Returns:
            校验后的合法间隔值

        Raises:
            ValueError: 当间隔值超出范围时
        """
        if interval < HEARTBEAT_MIN_INTERVAL or interval > HEARTBEAT_MAX_INTERVAL:
            raise ValueError(
                f"心跳间隔必须在 {HEARTBEAT_MIN_INTERVAL}-{HEARTBEAT_MAX_INTERVAL} 秒之间，"
                f"当前值: {interval}"
            )
        return interval

    # ------------------------------------------------------------------ #
    #  配置管理
    # ------------------------------------------------------------------ #

    @property
    def interval(self) -> int:
        """当前心跳间隔(秒)"""
        return self._interval

    def update_interval(self, interval: int) -> None:
        """更新心跳间隔。

        Args:
            interval: 新的间隔值(秒)，范围5-300

        Raises:
            ValueError: 当间隔值超出范围时
        """
        self._interval = self._validate_interval(interval)
        LOG.done(f"心跳间隔已更新: {self._interval}s")

    def apply_config(self, config: HeartbeatConfig) -> None:
        """应用心跳配置。

        Args:
            config: HeartbeatConfig 实例
        """
        self.update_interval(config.interval)
        LOG.info("心跳配置已应用")

    # ------------------------------------------------------------------ #
    #  设备注册/注销
    # ------------------------------------------------------------------ #

    def register_device(self, mac: str) -> dict:
        """注册设备到心跳监控。

        Args:
            mac: 设备的MAC地址

        Returns:
            心跳记录字典
        """
        existing = self._store.get(mac)
        if existing is not None:
            LOG.info(f"设备已在心跳监控中: {mac}")
            return existing

        record = self._store.upsert(
            mac,
            status=HeartbeatStatus.OFFLINE.value,
            consecutive_failures=0,
        )
        LOG.done(f"设备已注册到心跳监控: {mac}")
        return record

    def unregister_device(self, mac: str) -> bool:
        """从心跳监控中移除设备。

        Args:
            mac: 设备的MAC地址

        Returns:
            True=移除成功, False=设备未注册
        """
        record = self._store.get(mac)
        if record is None:
            LOG.info(f"设备未在心跳监控中: {mac}")
            return False

        self._store._store.delete(mac)
        LOG.done(f"设备已从心跳监控中移除: {mac}")
        return True

    # ------------------------------------------------------------------ #
    #  心跳检测核心逻辑
    # ------------------------------------------------------------------ #

    async def _check_device(self, mac: str) -> bool:
        """检测单个设备是否在线。

        通过 ISAPI 接口探测设备响应。由于 ISAPIClient 是同步的，
        使用 asyncio.to_thread 在线程池中执行以避免阻塞事件循环。

        Args:
            mac: 设备的MAC地址

        Returns:
            True=在线, False=离线
        """

        def _do_check() -> bool:
            """在线程中执行同步 ISAPI 调用。"""
            # 从设备管理器获取设备连接信息
            if self._device_manager is None:
                LOG.warning("DeviceManager 未提供，无法获取设备连接信息: %s", mac)
                return False

            device = self._device_manager.get_device(mac)
            if device is None:
                LOG.warning("设备不存在，跳过心跳检测: %s", mac)
                return False

            ip = device.get("ip", "")
            port = device.get("port", 80)
            username = device.get("username", "")
            password = device.get("password", "")

            client = ISAPIClient(
                ip=ip,
                username=username,
                password=password,
                port=port,
                timeout=5,
            )
            response = client.get(ONLINE_CHECK_ENDPOINT)
            return response.status_code == 200

        try:
            return await asyncio.to_thread(_do_check)
        except Exception as e:
            LOG.error("心跳检测失败: %s - %s", mac, e)
            return False

    async def _process_heartbeat(self, mac: str, online: bool) -> dict:
        """处理单次心跳检测结果。

        Args:
            mac: 设备的MAC地址
            online: 设备是否在线

        Returns:
            更新后的心跳记录
        """
        record = self._store.get(mac) or {}
        now = datetime.now().isoformat()
        consecutive = record.get("consecutive_failures", 0)
        old_status = record.get("status", HeartbeatStatus.OFFLINE.value)

        if online:
            # 设备响应正常
            new_record = self._store.upsert(
                mac,
                status=HeartbeatStatus.ONLINE.value,
                last_heartbeat_at=now,
                consecutive_failures=0,
            )
            # 恢复上线：从 offline → online
            if old_status == HeartbeatStatus.OFFLINE.value:
                new_record = self._store.upsert(mac, last_recovery_at=now)
                LOG.done(
                    f"心跳恢复: {mac} offline→online, recovery_at={now}"
                )
                self._sync_device_status(mac, HeartbeatStatus.ONLINE.value, reason="heartbeat_recovery")
        else:
            # 设备无响应
            consecutive += 1
            new_record = self._store.upsert(
                mac,
                last_heartbeat_at=now,
                consecutive_failures=consecutive,
            )

            if consecutive >= HEARTBEAT_CONSECUTIVE_THRESHOLD and old_status == HeartbeatStatus.ONLINE.value:
                # 达到阈值，标记为 offline
                new_record = self._store.upsert(mac, status=HeartbeatStatus.OFFLINE.value, last_offline_at=now)
                LOG.failed(
                    f"心跳离线: {mac} online→offline, "
                    f"consecutive={consecutive}, offline_at={now}"
                )
                self._sync_device_status(mac, HeartbeatStatus.OFFLINE.value, reason="heartbeat_timeout")

        return new_record

    def _sync_device_status(self, mac: str, status: str, reason: str) -> None:
        """同步心跳状态到 DeviceManager 中的 heartbeat_status 字段。

        Args:
            mac: 设备的MAC地址
            status: 心跳状态(online/offline)
            reason: 状态变更原因
        """
        if self._device_manager is None:
            return

        try:
            device = self._device_manager.get_device(mac)
            if device is None:
                return

            record = self._device_manager._store.get(mac)
            if record is None:
                return

            old_hb_status = record.get("heartbeat_status", "")
            if old_hb_status != status:
                record["heartbeat_status"] = status
                record["updated_at"] = datetime.now().isoformat()
                self._device_manager._store.set(mac, record)
                LOG.info(
                    f"设备 heartbeat_status 已同步: {mac} {old_hb_status}→{status} ({reason})"
                )
        except Exception as e:
            LOG.error(f"同步 heartbeat_status 失败: {mac} - {e}")

    async def check_one(self, mac: str) -> dict:
        """手动触发单个设备的心跳检测。

        Args:
            mac: 设备的MAC地址

        Returns:
            更新后的心跳记录
        """
        self.register_device(mac)
        online = await self._check_device(mac)
        return await self._process_heartbeat(mac, online)

    # ------------------------------------------------------------------ #
    #  周期性运行
    # ------------------------------------------------------------------ #

    async def _loop(self, macs: list[str]) -> None:
        """心跳检测主循环。

        Args:
            macs: 需要监控的设备MAC列表
        """
        while self._running:
            LOG.info(f"心跳轮询开始: {len(macs)} 个设备, interval={self._interval}s")

            results = await asyncio.gather(
                *(self.check_one(mac) for mac in macs),
                return_exceptions=True,
            )

            # 记录异常
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    mac = macs[i] if i < len(macs) else "unknown"
                    LOG.error(f"心跳检测异常: {mac} - {result}")

            LOG.info(f"心跳轮询完成: {len(macs)} 个设备")

            # 等待下一轮
            await asyncio.sleep(self._interval)

    async def start(self, macs: list[str]) -> None:
        """启动周期性心跳检测。

        此方法会在后台创建 asyncio task 并立即返回。

        Args:
            macs: 需要监控的设备MAC列表
        """
        if self._running:
            LOG.warning("心跳引擎已在运行中")
            return

        self._running = True
        self._task = asyncio.create_task(self._loop(macs))
        LOG.done(f"心跳引擎已启动: {len(macs)} 个设备, interval={self._interval}s")

    async def stop(self) -> None:
        """停止周期性心跳检测。"""
        if not self._running:
            LOG.warning("心跳引擎未在运行")
            return

        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        LOG.done("心跳引擎已停止")

    @property
    def is_running(self) -> bool:
        """心跳引擎是否在运行"""
        return self._running

    # ------------------------------------------------------------------ #
    #  状态查询
    # ------------------------------------------------------------------ #

    def get_status(self, mac: str) -> HeartbeatStatusResponse | None:
        """获取设备心跳状态。

        Args:
            mac: 设备的MAC地址

        Returns:
            HeartbeatStatusResponse 实例，设备未注册时返回 None
        """
        record = self._store.get(mac)
        if record is None:
            return None

        return HeartbeatStatusResponse(
            mac=record.get("mac", mac),
            status=record.get("status", HeartbeatStatus.OFFLINE.value),
            since=record.get("last_recovery_at") or record.get("last_offline_at") or "",
            last_check=record.get("last_heartbeat_at") or "",
            consecutive_checks=record.get("consecutive_failures", 0),
        )

    def list_statuses(self) -> list[HeartbeatStatusResponse]:
        """获取所有设备的心跳状态。

        Returns:
            HeartbeatStatusResponse 列表
        """
        records = self._store.list_all()
        results: list[HeartbeatStatusResponse] = []
        for record in records:
            mac = record.get("mac", "")
            results.append(
                HeartbeatStatusResponse(
                    mac=mac,
                    status=record.get("status", HeartbeatStatus.OFFLINE.value),
                    since=record.get("last_recovery_at") or record.get("last_offline_at") or "",
                    last_check=record.get("last_heartbeat_at") or "",
                    consecutive_checks=record.get("consecutive_failures", 0),
                )
            )
        return results
