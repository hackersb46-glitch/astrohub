"""
M2 Device Manager v1.0 - 状态历史记录

记录设备状态变化的完整历史(P1.6)。
追加写入，不可修改或删除。支持按时间范围和设备MAC查询。

Author: 雅痞张@南方天文
"""

from pathlib import Path
from datetime import datetime, timezone

from device.constants import STATUS_HISTORY_FILE
from device.core.storage import JsonStore
from device.core.logger import LOG


def _now_iso() -> str:
    """返回当前时间的ISO格式字符串（无时区信息）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


class StatusHistory:
    """设备状态变化历史记录器(P1.6)。

    追加写入模式，所有条目不可修改或删除。
    支持按设备MAC、时间范围查询。
    """

    def __init__(self, file_path: str | Path | None = None) -> None:
        path = file_path if file_path is not None else STATUS_HISTORY_FILE
        self._store = JsonStore(path, default={"records": {}})
        self._counter = 0

    def record_entry(self, mac: str, old_status: str, new_status: str, reason: str) -> dict:
        """记录一次设备状态变更(P1.6)。

        Args:
            mac: 设备MAC地址
            old_status: 变更前的状态
            new_status: 变更后的状态
            reason: 变更原因

        Returns:
            生成的历史记录条目字典
        """
        self._counter += 1
        entry_id = f"entry_{self._counter}_{mac}_{_now_iso()}"

        entry = {
            "entry_id": entry_id,
            "mac": mac,
            "old_status": old_status,
            "new_status": new_status,
            "reason": reason,
            "timestamp": _now_iso(),
        }

        self._store.set(entry_id, entry)
        LOG.info(f"状态历史: {mac} {old_status}→{new_status} ({reason})")
        return entry

    def query_history(
        self,
        mac: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        """查询状态历史记录(P1.6)。

        Args:
            mac: 设备MAC地址（精确匹配）
            start_date: 起始时间（ISO格式，包含）
            end_date: 结束时间（ISO格式，包含）

        Returns:
            过滤并排序后的历史记录列表
        """
        all_records = self._store.list_all()

        filtered = all_records
        if mac is not None:
            filtered = [r for r in filtered if r.get("mac") == mac]
        if start_date is not None:
            filtered = [r for r in filtered if r.get("timestamp", "") >= start_date]
        if end_date is not None:
            filtered = [r for r in filtered if r.get("timestamp", "") <= end_date]

        return sorted(filtered, key=lambda r: r.get("timestamp", ""))

    def get_latest_status(self, mac: str) -> str | None:
        """获取设备最新的状态。

        Args:
            mac: 设备MAC地址

        Returns:
            最新条目的new_status，若无记录则返回None
        """
        history = self.query_history(mac=mac)
        if not history:
            return None
        return history[-1].get("new_status")

    def get_count(self, mac: str | None = None) -> int:
        """获取历史记录总数或指定MAC的记录数。

        Args:
            mac: 设备MAC地址（可选）

        Returns:
            记录数量
        """
        if mac is None:
            return self._store.count()
        return len(self.query_history(mac=mac))
