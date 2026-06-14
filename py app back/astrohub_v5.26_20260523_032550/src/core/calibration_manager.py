"""
AstroHub v2.0 - 校准管理器

统一管理设备校准流程，支持多校准类型、状态追踪、持久化恢复。
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any

from src.config import DATA_DIR
from src.logger import get_logger

logger = get_logger("calibration")


# === 状态机枚举 ===

class CalibrationStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CalibrationType(str, Enum):
    FOCUS = "focus"
    COLOR = "color"
    SPEED = "speed"
    POSITION = "position"


# === 数据模型 ===

@dataclass
class CalibrationState:
    """单次校准的状态快照。"""
    status: CalibrationStatus = CalibrationStatus.IDLE
    progress: float = 0.0  # 0.0 ~ 1.0
    started_at: float | None = None
    completed_at: float | None = None
    error: str | None = None
    result: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CalibrationState":
        data["status"] = CalibrationStatus(data["status"])
        return cls(**data)


@dataclass
class DeviceCalibrationProfile:
    """单个设备的完整校准档案。"""
    device_id: str
    calibrations: dict[CalibrationType, CalibrationState] = field(default_factory=dict)
    last_updated: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "calibrations": {
                k.value: v.to_dict() for k, v in self.calibrations.items()
            },
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeviceCalibrationProfile":
        calibrations = {
            CalibrationType(k): CalibrationState.from_dict(v)
            for k, v in data["calibrations"].items()
        }
        return cls(
            device_id=data["device_id"],
            calibrations=calibrations,
            last_updated=data.get("last_updated"),
        )


# === 状态机转换器 ===

_VALID_TRANSITIONS: dict[CalibrationStatus, list[CalibrationStatus]] = {
    CalibrationStatus.IDLE: [CalibrationStatus.RUNNING],
    CalibrationStatus.RUNNING: [
        CalibrationStatus.COMPLETED,
        CalibrationStatus.FAILED,
        CalibrationStatus.CANCELLED,
    ],
    CalibrationStatus.COMPLETED: [CalibrationStatus.IDLE],  # 可重新校准
    CalibrationStatus.FAILED: [CalibrationStatus.IDLE],      # 可重试
    CalibrationStatus.CANCELLED: [CalibrationStatus.IDLE],   # 可重试
}


def _validate_transition(current: CalibrationStatus, target: CalibrationStatus) -> bool:
    """验证状态转换是否合法。"""
    return target in _VALID_TRANSITIONS.get(current, [])


# === 持久化路径 ===

CALIBRATION_DIR = DATA_DIR / "calibration"
CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)


def _profile_path(device_id: str) -> Path:
    return CALIBRATION_DIR / f"{device_id}.json"


# === CalibrationManager ===

class CalibrationManager:
    """校准管理器。

    职责:
    - 管理设备校准的生命周期（状态机驱动）
    - 支持 focus / color / speed / position 四种校准类型
    - 持久化校准状态到磁盘，支持中断恢复
    - 线程安全（基于 asyncio.Lock）
    """

    def __init__(self) -> None:
        self._profiles: dict[str, DeviceCalibrationProfile] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._load_all_profiles()
        logger.info("CalibrationManager 初始化完成，已加载 %d 个设备档案", len(self._profiles))

    # ------------------------------------------------------------------
    # 内部：持久化
    # ------------------------------------------------------------------

    def _get_lock(self, device_id: str) -> asyncio.Lock:
        if device_id not in self._locks:
            self._locks[device_id] = asyncio.Lock()
        return self._locks[device_id]

    def _get_or_create_profile(self, device_id: str) -> DeviceCalibrationProfile:
        if device_id not in self._profiles:
            self._profiles[device_id] = DeviceCalibrationProfile(device_id=device_id)
        return self._profiles[device_id]

    def _load_all_profiles(self) -> None:
        if not CALIBRATION_DIR.exists():
            return
        for fp in CALIBRATION_DIR.glob("*.json"):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                profile = DeviceCalibrationProfile.from_dict(data)
                self._profiles[profile.device_id] = profile
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.warning("校准档案加载失败 %s: %s", fp.name, exc)

    def _save_profile(self, device_id: str) -> None:
        profile = self._profiles[device_id]
        profile.last_updated = time.time()
        path = _profile_path(device_id)
        path.write_text(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug("校准档案已保存: %s", device_id)

    # ------------------------------------------------------------------
    # 内部：状态机辅助
    # ------------------------------------------------------------------

    def _set_state(
        self, device_id: str, cal_type: CalibrationType,
        status: CalibrationStatus, progress: float = 0.0,
        error: str | None = None, result: dict[str, Any] | None = None,
    ) -> None:
        profile = self._get_or_create_profile(device_id)
        if cal_type not in profile.calibrations:
            profile.calibrations[cal_type] = CalibrationState()

        state = profile.calibrations[cal_type]
        if not _validate_transition(state.status, status):
            raise RuntimeError(
                f"非法状态转换: {device_id}/{cal_type.value} "
                f"{state.status.value} -> {status.value}"
            )

        state.status = status
        state.progress = progress

        if status == CalibrationStatus.RUNNING:
            state.started_at = time.time()
            state.error = None
        elif status in (CalibrationStatus.COMPLETED, CalibrationStatus.FAILED, CalibrationStatus.CANCELLED):
            state.completed_at = time.time()
            if error:
                state.error = error
            if result:
                state.result = result

        self._save_profile(device_id)

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    async def calibrate_focus(self, device_id: str, target: str = "infinity") -> dict[str, Any]:
        """自动对焦校准。

        Args:
            device_id: 设备标识。
            target: 对焦目标（默认无穷远）。

        Returns:
            校准结果字典。
        """
        lock = self._get_lock(device_id)
        async with lock:
            self._set_state(device_id, CalibrationType.FOCUS, CalibrationStatus.RUNNING)
            logger.info("开始对焦校准: device=%s, target=%s", device_id, target)

            try:
                # 模拟对焦流程（实际接入硬件时替换）
                steps = [0.2, 0.4, 0.6, 0.8, 1.0]
                for prog in steps:
                    self._profiles[device_id].calibrations[CalibrationType.FOCUS].progress = prog
                    await asyncio.sleep(0.05)  # 模拟耗时

                result = {"focus_offset": 0.0, "target": target, "sharpness_score": 0.95}
                self._set_state(
                    device_id, CalibrationType.FOCUS,
                    CalibrationStatus.COMPLETED, progress=1.0, result=result,
                )
                logger.info("对焦校准完成: device=%s", device_id)
                return result
            except asyncio.CancelledError:
                self._set_state(
                    device_id, CalibrationType.FOCUS, CalibrationStatus.CANCELLED,
                    error="用户取消",
                )
                logger.warning("对焦校准已取消: device=%s", device_id)
                raise
            except Exception as exc:
                self._set_state(
                    device_id, CalibrationType.FOCUS,
                    CalibrationStatus.FAILED, error=str(exc),
                )
                logger.error("对焦校准失败: device=%s, error=%s", device_id, exc)
                raise

    async def calibrate_color(self, device_id: str) -> dict[str, Any]:
        """色彩平衡校准。

        Args:
            device_id: 设备标识。

        Returns:
            校准结果字典。
        """
        lock = self._get_lock(device_id)
        async with lock:
            self._set_state(device_id, CalibrationType.COLOR, CalibrationStatus.RUNNING)
            logger.info("开始色彩平衡校准: device=%s", device_id)

            try:
                steps = [0.25, 0.5, 0.75, 1.0]
                for prog in steps:
                    self._profiles[device_id].calibrations[CalibrationType.COLOR].progress = prog
                    await asyncio.sleep(0.05)

                result = {"white_balance_r": 1.0, "white_balance_g": 1.0, "white_balance_b": 1.0}
                self._set_state(
                    device_id, CalibrationType.COLOR,
                    CalibrationStatus.COMPLETED, progress=1.0, result=result,
                )
                logger.info("色彩平衡校准完成: device=%s", device_id)
                return result
            except asyncio.CancelledError:
                self._set_state(
                    device_id, CalibrationType.COLOR, CalibrationStatus.CANCELLED,
                    error="用户取消",
                )
                raise
            except Exception as exc:
                self._set_state(
                    device_id, CalibrationType.COLOR,
                    CalibrationStatus.FAILED, error=str(exc),
                )
                raise

    async def calibrate_speed(self, device_id: str) -> dict[str, Any]:
        """速度映射校准。

        校准设备速度指令与实际物理速度之间的映射关系。

        Args:
            device_id: 设备标识。

        Returns:
            校准结果字典。
        """
        lock = self._get_lock(device_id)
        async with lock:
            self._set_state(device_id, CalibrationType.SPEED, CalibrationStatus.RUNNING)
            logger.info("开始速度映射校准: device=%s", device_id)

            try:
                steps = [0.2, 0.4, 0.6, 0.8, 1.0]
                for prog in steps:
                    self._profiles[device_id].calibrations[CalibrationType.SPEED].progress = prog
                    await asyncio.sleep(0.05)

                result = {"speed_factor": 1.0, "max_speed": 10.0, "min_speed": 0.1}
                self._set_state(
                    device_id, CalibrationType.SPEED,
                    CalibrationStatus.COMPLETED, progress=1.0, result=result,
                )
                logger.info("速度映射校准完成: device=%s", device_id)
                return result
            except asyncio.CancelledError:
                self._set_state(
                    device_id, CalibrationType.SPEED, CalibrationStatus.CANCELLED,
                    error="用户取消",
                )
                raise
            except Exception as exc:
                self._set_state(
                    device_id, CalibrationType.SPEED,
                    CalibrationStatus.FAILED, error=str(exc),
                )
                raise

    async def calibrate_position(self, device_id: str) -> dict[str, Any]:
        """位置校准。

        校准设备的零点位置与坐标映射。

        Args:
            device_id: 设备标识。

        Returns:
            校准结果字典。
        """
        lock = self._get_lock(device_id)
        async with lock:
            self._set_state(device_id, CalibrationType.POSITION, CalibrationStatus.RUNNING)
            logger.info("开始位置校准: device=%s", device_id)

            try:
                steps = [0.2, 0.4, 0.6, 0.8, 1.0]
                for prog in steps:
                    self._profiles[device_id].calibrations[CalibrationType.POSITION].progress = prog
                    await asyncio.sleep(0.05)

                result = {"home_position": [0.0, 0.0], "position_offset": [0.0, 0.0]}
                self._set_state(
                    device_id, CalibrationType.POSITION,
                    CalibrationStatus.COMPLETED, progress=1.0, result=result,
                )
                logger.info("位置校准完成: device=%s", device_id)
                return result
            except asyncio.CancelledError:
                self._set_state(
                    device_id, CalibrationType.POSITION, CalibrationStatus.CANCELLED,
                    error="用户取消",
                )
                raise
            except Exception as exc:
                self._set_state(
                    device_id, CalibrationType.POSITION,
                    CalibrationStatus.FAILED, error=str(exc),
                )
                raise

    def get_calibration_status(self, device_id: str) -> dict[str, Any]:
        """获取设备的校准状态摘要。

        Args:
            device_id: 设备标识。

        Returns:
            各校准类型的状态摘要。
        """
        profile = self._profiles.get(device_id)
        if not profile:
            return {"device_id": device_id, "calibrations": {}}

        summary = {}
        for cal_type, state in profile.calibrations.items():
            summary[cal_type.value] = {
                "status": state.status.value,
                "progress": state.progress,
                "error": state.error,
            }
        return {"device_id": device_id, "calibrations": summary}

    async def cancel_calibration(self, device_id: str, cal_type: str | None = None) -> dict[str, Any]:
        """取消校准。

        Args:
            device_id: 设备标识。
            cal_type: 校准类型。如果为 None，则取消该设备所有 RUNNING 状态的校准。

        Returns:
            取消操作的结果摘要。
        """
        lock = self._get_lock(device_id)
        async with lock:
            profile = self._profiles.get(device_id)
            if not profile:
                return {"cancelled": [], "reason": "设备无校准档案"}

            types_to_cancel = []
            if cal_type:
                try:
                    ct = CalibrationType(cal_type)
                    if ct in profile.calibrations and profile.calibrations[ct].status == CalibrationStatus.RUNNING:
                        types_to_cancel.append(ct)
                except ValueError:
                    return {"cancelled": [], "reason": f"未知校准类型: {cal_type}"}
            else:
                types_to_cancel = [
                    ct for ct, state in profile.calibrations.items()
                    if state.status == CalibrationStatus.RUNNING
                ]

            for ct in types_to_cancel:
                self._set_state(
                    device_id, ct, CalibrationStatus.CANCELLED,
                    error="用户主动取消",
                )
                logger.info("校准已取消: device=%s, type=%s", device_id, ct.value)

            return {"cancelled": [ct.value for ct in types_to_cancel]}

    def get_calibration_report(self, device_id: str) -> dict[str, Any]:
        """获取完整的校准报告。

        Args:
            device_id: 设备标识。

        Returns:
            包含完整历史与当前状态的报告。
        """
        profile = self._profiles.get(device_id)
        if not profile:
            return {"device_id": device_id, "found": False, "report": None}

        report = {
            "device_id": device_id,
            "found": True,
            "last_updated": profile.last_updated,
            "calibrations": {},
        }
        for cal_type, state in profile.calibrations.items():
            report["calibrations"][cal_type.value] = state.to_dict()
        return report

    def recovery_needed(self) -> list[dict[str, str]]:
        """检查是否有需要恢复的校准。

        Returns:
            需要恢复的校准列表，每项包含 device_id 和 cal_type。
        """
        needs_recovery = []
        for device_id, profile in self._profiles.items():
            for cal_type, state in profile.calibrations.items():
                if state.status == CalibrationStatus.RUNNING:
                    needs_recovery.append({
                        "device_id": device_id,
                        "cal_type": cal_type.value,
                        "reason": "校准进程中断（状态仍为 RUNNING）",
                    })
        if needs_recovery:
            logger.warning("检测到 %d 个需要恢复的校准进程", len(needs_recovery))
        return needs_recovery

    async def recover_calibrations(self) -> dict[str, Any]:
        """恢复中断的校准。

        将所有处于 RUNNING 状态的校准重置为 IDLE，以便重新触发。

        Returns:
            恢复操作摘要。
        """
        recovered = []
        lock_ids: set[str] = set()
        for device_id, profile in self._profiles.items():
            for cal_type, state in profile.calibrations.items():
                if state.status == CalibrationStatus.RUNNING:
                    lock = self._get_lock(device_id)
                    async with lock:
                        # 直接从 RUNNING -> IDLE（允许重新校准）
                        state.status = CalibrationStatus.IDLE
                        state.progress = 0.0
                        state.error = None
                        state.started_at = None
                        self._save_profile(device_id)
                    recovered.append({"device_id": device_id, "cal_type": cal_type.value})
                    logger.info("已恢复校准: device=%s, type=%s", device_id, cal_type.value)

        return {"recovered": recovered, "count": len(recovered)}
