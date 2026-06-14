"""
M4 Calibration Service v1.0 - 校准恢复模块

校准参数恢复(P7.1)、异常回滚(P7.2)。
校准失败时恢复设备参数到校准前状态，确保回滚操作本身记录日志。

Author: 雅痞张@南方天文
"""

from datetime import datetime, timezone
from typing import Any

from src.calibration.core.logger import LOG
from src.calibration.core.calibration_storage import CalibrationStore


class CalibrationRecovery:
    """校准恢复管理器：参数恢复、异常回滚。

    在校准前保存设备参数快照，校准失败时回滚到原始状态。
    """

    def __init__(self, store: CalibrationStore | None = None) -> None:
        self._store = store or CalibrationStore()
        self._snapshot: dict[str, Any] = {}  # device_mac -> snapshot
        self._rollback_logs: list[dict] = []

    # ------------------------------------------------------------------ #
    #  参数快照
    # ------------------------------------------------------------------ #
    def save_snapshot(self, device_mac: str, params: dict) -> None:
        """校准前保存设备参数快照。

        Args:
            device_mac: 设备MAC地址
            params: 设备当前参数字典
        """
        self._snapshot[device_mac] = {
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "params": params.copy(),
        }
        LOG.info(f"校准快照已保存: device={device_mac}, keys={list(params.keys())}")

    def get_snapshot(self, device_mac: str) -> dict | None:
        """获取设备参数快照。

        Args:
            device_mac: 设备MAC地址

        Returns:
            快照字典，不存在返回None
        """
        return self._snapshot.get(device_mac)

    def clear_snapshot(self, device_mac: str) -> None:
        """清除设备参数快照。

        Args:
            device_mac: 设备MAC地址
        """
        if device_mac in self._snapshot:
            del self._snapshot[device_mac]
            LOG.info(f"校准快照已清除: device={device_mac}")

    # ------------------------------------------------------------------ #
    #  P7.2 - 异常回滚
    # ------------------------------------------------------------------ #
    def rollback(
        self,
        device_mac: str,
        restore_fn: callable | None = None,
    ) -> dict:
        """校准失败时回滚到校准前状态。

        将已修改的参数恢复到校准前状态，回滚操作本身记录日志。

        Args:
            device_mac: 设备MAC地址
            restore_fn: 恢复函数，接收参数字典，返回 {"success": bool}
                       为None时仅记录回滚意图（模拟模式）

        Returns:
            回滚结果 {"success": bool, "message": str, "logs": list}
        """
        LOG.warning(f"开始回滚: device={device_mac}")

        snapshot = self._snapshot.get(device_mac)
        if snapshot is None:
            msg = f"无校准快照，无法回滚: device={device_mac}"
            LOG.warning(msg)
            rollback_entry = {
                "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                "device_mac": device_mac,
                "action": "rollback",
                "status": "skipped",
                "reason": "no_snapshot",
                "message": msg,
            }
            self._rollback_logs.append(rollback_entry)
            return {"success": False, "message": msg, "logs": self._rollback_logs}

        original_params = snapshot["params"]
        LOG.info(f"回滚参数: device={device_mac}, keys={list(original_params.keys())}")

        # 执行恢复
        if restore_fn:
            try:
                result = restore_fn(original_params)
                if result.get("success"):
                    msg = f"回滚成功: device={device_mac}"
                    LOG.done(msg)
                    rollback_status = "success"
                else:
                    msg = f"回滚失败: device={device_mac} - {result.get('error')}"
                    LOG.error(msg)
                    rollback_status = "failed"
            except Exception as e:
                msg = f"回滚异常: device={device_mac} - {str(e)}"
                LOG.error(msg)
                rollback_status = "error"
                result = {"success": False, "error": str(e)}
        else:
            # 模拟模式 - 仅记录回滚意图
            msg = f"回滚已记录(模拟模式): device={device_mac}, params={list(original_params.keys())}"
            LOG.info(msg)
            rollback_status = "logged"
            result = {"success": True, "message": msg}

        rollback_entry = {
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "device_mac": device_mac,
            "action": "rollback",
            "status": rollback_status,
            "params_restored": list(original_params.keys()) if result.get("success") else [],
            "message": msg,
        }
        self._rollback_logs.append(rollback_entry)

        # 清除快照
        self.clear_snapshot(device_mac)

        return {"success": result.get("success", False), "message": msg, "entry": rollback_entry}

    # ------------------------------------------------------------------ #
    #  P7.1 - 校准参数恢复
    # ------------------------------------------------------------------ #
    def restore_calibration(
        self,
        device_mac: str,
        calibration_id: str | None = None,
        restore_fn: callable | None = None,
    ) -> dict:
        """从保存的校准参数恢复设备。

        读取校准参数文件，逐项写入设备。不支持的参数跳过并记录。

        Args:
            device_mac: 设备MAC地址
            calibration_id: 校准ID，不指定则使用最新记录
            restore_fn: 恢复函数，接收参数字典，返回 {"success": bool, "restored": list, "skipped": list}

        Returns:
            恢复结果 {"success": bool, "restored": list, "skipped": list}
        """
        LOG.info(f"开始校准恢复: device={device_mac}, calibration_id={calibration_id}")

        # 获取校准数据
        if calibration_id:
            calibration_data = self._store.get_calibration_by_id(calibration_id)
        else:
            calibration_data = self._store.get_latest_calibration(device_mac)

        if calibration_data is None:
            msg = f"无校准数据可恢复: device={device_mac}"
            LOG.warning(msg)
            return {"success": False, "message": msg, "restored": [], "skipped": []}

        # 执行恢复
        if restore_fn:
            try:
                result = restore_fn(calibration_data)
                restored = result.get("restored", [])
                skipped = result.get("skipped", [])

                if result.get("success"):
                    LOG.done(f"校准恢复成功: device={device_mac}, restored={restored}, skipped={skipped}")
                else:
                    LOG.error(f"校准恢复部分失败: device={device_mac}")

                return {
                    "success": result.get("success", False),
                    "restored": restored,
                    "skipped": skipped,
                    "message": calibration_data.get("calibration_id", ""),
                }
            except Exception as e:
                msg = f"校准恢复异常: {str(e)}"
                LOG.error(msg)
                return {"success": False, "message": msg, "restored": [], "skipped": []}
        else:
            # 模拟模式
            restored_params = list(calibration_data.keys())
            msg = f"校准恢复已记录(模拟模式): device={device_mac}, params={restored_params}"
            LOG.info(msg)
            return {"success": True, "message": msg, "restored": restored_params, "skipped": []}

    def get_rollback_history(self, device_mac: str | None = None) -> list[dict]:
        """获取回滚历史记录。

        Args:
            device_mac: 设备MAC，不指定则返回所有

        Returns:
            回滚记录列表
        """
        if device_mac:
            return [r for r in self._rollback_logs if r.get("device_mac") == device_mac]
        return self._rollback_logs
