"""
M4 Calibration Service v1.0 - 校准流程管理

校准流程管理(P0.1)、校准状态机(P0.2)、校准日志(P0.3)。
管理校准各阶段执行顺序、状态流转、操作日志记录。

Author: 雅痞张@南方天文
"""

from datetime import datetime, timezone
from typing import Any, Callable

from src.calibration.constants import (
    CalibrationState,
    CalibrationStep,
    VALID_CALIBRATION_TRANSITIONS,
    CalibrationResult,
)
from src.calibration.core.logger import LOG


class CalibrationStepLog:
    """单步校准操作日志记录。"""

    def __init__(
        self,
        step: str,
        level: str,
        message: str,
        params: dict | None = None,
        result: str | None = None,
    ) -> None:
        self.timestamp = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        self.step = step
        self.level = level
        self.message = message
        self.params = params or {}
        self.result = result


class CalibrationManager:
    """校准流程管理器：状态机、步骤执行、日志记录。

    状态流转: idle → preparing → calibrating → verifying → completed/failed

    Args:
        step_handlers: 各校准步骤的处理器字典
    """

    def __init__(self, step_handlers: dict[str, Callable] | None = None) -> None:
        self._state = CalibrationState.IDLE
        self._logs: list[CalibrationStepLog] = []
        self._step_handlers = step_handlers or {}
        self._current_step: str | None = None
        self._pre_calibration_snapshot: dict = {}

    # ------------------------------------------------------------------ #
    #  P0.2 - 状态机
    # ------------------------------------------------------------------ #
    @property
    def state(self) -> str:
        """当前校准状态。"""
        return self._state.value

    def _transition(self, new_state: CalibrationState) -> bool:
        """尝试状态流转。

        Args:
            new_state: 目标状态

        Returns:
            流转是否成功
        """
        current = self._state.value
        if new_state.value in VALID_CALIBRATION_TRANSITIONS.get(current, []):
            old_state = current
            self._state = new_state
            LOG.info(f"状态流转: {old_state} → {new_state.value}")
            self._add_log("state_machine", "info", f"状态 {old_state} → {new_state.value}")
            return True
        LOG.warning(f"无效状态流转: {current} → {new_state.value}")
        self._add_log(
            "state_machine", "warning",
            f"无效状态流转: {current} → {new_state.value}"
        )
        return False

    def _fail(self, reason: str) -> None:
        """进入失败状态。

        Args:
            reason: 失败原因
        """
        self._state = CalibrationState.FAILED
        LOG.error(f"校准失败: {reason}")
        self._add_log("state_machine", "error", f"校准失败: {reason}")

    # ------------------------------------------------------------------ #
    #  P0.3 - 校准日志
    # ------------------------------------------------------------------ #
    def _add_log(
        self,
        step: str,
        level: str,
        message: str,
        params: dict | None = None,
        result: str | None = None,
    ) -> None:
        """记录一步操作日志。

        Args:
            step: 步骤名称
            level: 日志级别
            message: 日志内容
            params: 参数信息
            result: 结果信息
        """
        entry = CalibrationStepLog(
            step=step, level=level, message=message,
            params=params, result=result,
        )
        self._logs.append(entry)
        LOG.info(f"[{step}] {message}")

    def get_logs(self) -> list[dict]:
        """获取所有校准日志。

        Returns:
            日志条目列表（字典格式）
        """
        return [
            {
                "timestamp": log.timestamp,
                "step": log.step,
                "level": log.level,
                "message": log.message,
                "params": log.params,
                "result": log.result,
            }
            for log in self._logs
        ]

    def get_summary(self) -> dict:
        """生成校准汇总信息。

        Returns:
            包含成功/失败项的汇总
        """
        total = len(self._logs)
        errors = sum(1 for l in self._logs if l.level == "error")
        warnings = sum(1 for l in self._logs if l.level == "warning")
        success = total - errors - warnings

        return {
            "state": self._state.value,
            "total_logs": total,
            "success_count": success,
            "warning_count": warnings,
            "error_count": errors,
            "current_step": self._current_step,
        }

    # ------------------------------------------------------------------ #
    #  P0.1 - 校准流程管理
    # ------------------------------------------------------------------ #
    def register_step(self, step_name: str, handler: Callable) -> None:
        """注册校准步骤处理器。

        Args:
            step_name: 步骤名称
            handler: 处理函数，返回 {"success": bool, "data": dict, "error": str}
        """
        self._step_handlers[step_name] = handler
        LOG.info(f"注册校准步骤: {step_name}")

    def pre_check(self) -> dict:
        """前置校验(P0.1)。

        执行校准前的所有检查。

        Returns:
            {"success": bool, "errors": list[str]}
        """
        LOG.info("执行前置校验...")
        self._add_log("pre_check", "info", "开始前置校验")

        errors = []

        # 检查状态
        if self._state != CalibrationState.IDLE:
            errors.append(f"当前状态{self._state.value}，需要idle状态才能开始校准")

        # 检查步骤处理器
        if not self._step_handlers:
            errors.append("未注册任何校准步骤处理器")

        if errors:
            self._add_log("pre_check", "error", f"前置校验失败: {errors}")
            return {"success": False, "errors": errors}

        self._add_log("pre_check", "info", "前置校验通过")
        return {"success": True, "errors": []}

    def start_calibration(self, steps: list[str] | None = None) -> dict:
        """启动校准流程(P0.1)。

        按定义顺序执行校准步骤：preparing → calibrating → verifying → completed

        Args:
            steps: 要执行的步骤列表，不指定则执行所有已注册步骤

        Returns:
            校准结果 {"success": bool, "state": str, "logs": list}
        """
        # 前置校验
        check = self.pre_check()
        if not check["success"]:
            return {"success": False, "error": check["errors"], "logs": self.get_logs()}

        # 进入 preparing
        self._transition(CalibrationState.PREPARING)
        self._logs.clear()

        steps_to_run = steps or list(self._step_handlers.keys())
        self._add_log("workflow", "info", f"开始校准流程，步骤: {steps_to_run}")

        results: dict[str, Any] = {}
        success = True

        # 进入 calibrating
        self._transition(CalibrationState.CALIBRATING)

        # 执行各步骤
        for step_name in steps_to_run:
            self._current_step = step_name
            self._add_log(step_name, "info", f"执行步骤: {step_name}")

            handler = self._step_handlers.get(step_name)
            if handler is None:
                self._add_log(step_name, "error", f"步骤处理器未注册: {step_name}")
                success = False
                break

            try:
                result = handler()
                results[step_name] = result
                if result.get("success"):
                    self._add_log(step_name, "done", f"步骤完成: {step_name}")
                else:
                    self._add_log(step_name, "error", f"步骤失败: {step_name} - {result.get('error')}")
                    success = False
                    break
            except Exception as e:
                self._add_log(step_name, "error", f"步骤异常: {step_name} - {str(e)}")
                results[step_name] = {"success": False, "error": str(e)}
                success = False
                break

        if not success:
            self._fail(f"校准步骤执行失败")
            return {"success": False, "state": self._state.value, "results": results, "logs": self.get_logs()}

        # 进入 verifying
        self._transition(CalibrationState.VERIFYING)
        self._add_log("workflow", "info", "进入验证阶段")

        # 进入 completed
        self._transition(CalibrationState.COMPLETED)
        self._current_step = None

        summary = self.get_summary()
        self._add_log("workflow", "done", f"校准完成 - {summary}")

        return {"success": True, "state": self._state.value, "results": results, "summary": summary, "logs": self.get_logs()}

    def reset(self) -> None:
        """重置校准状态到idle。"""
        self._state = CalibrationState.IDLE
        self._current_step = None
        self._add_log("state_machine", "info", "状态重置为 idle")

    def get_status(self) -> dict:
        """获取当前校准状态。

        Returns:
            状态信息字典
        """
        return {
            "state": self._state.value,
            "current_step": self._current_step,
            "registered_steps": list(self._step_handlers.keys()),
        }
