"""
M4 Calibration Service v1.0 - 校准数据存储模块

提供基于JSON的持久化存储，支持原子写入、线程安全、数据校验。
校准参数持久化(P5.1)、校准历史查询(P5.2)。
参考 M2: src/device/core/storage.py
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from src.calibration.core.logger import LOG
from src.calibration.constants import DATA_DIR, CALIBRATION_DATA_FILE


def _ensure_json(path: str | Path) -> Path:
    """确保传入的是Path对象。"""
    return path if isinstance(path, Path) else Path(path)


def _atomic_write(path: Path, data: Any) -> None:
    """通过 tempfile + os.replace() 安全写入JSON文件，保证原子性。

    Args:
        path: 目标文件路径
        data: 要序列化写入的数据
    """
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


class CalibrationStore:
    """校准数据JSON存储，支持线程安全的读写、原子写入。

    数据结构:
        {
            "meta": {"created_at": ..., "updated_at": ..., "version": 1},
            "records": {
                "<device_mac>": [
                    {
                        "calibration_id": ...,
                        "timestamp": ...,
                        "auto_focus": {...},
                        "color_balance": {...},
                        "speed_mapping": {...},
                        "position_calibration": {...},
                        "overall_result": "pass|fail",
                    },
                    ...
                ],
                ...
            }
        }
    """

    def __init__(self, file_path: str | Path | None = None) -> None:
        self.path = _ensure_json(file_path or CALIBRATION_DATA_FILE).resolve()
        self._lock = Lock()
        self._ensure_file()

    # ------------------------------------------------------------------ #
    #  文件初始化
    # ------------------------------------------------------------------ #
    def _ensure_file(self) -> None:
        if not self.path.exists():
            default = {"meta": {}, "records": {}}
            _atomic_write(self.path, default)
            LOG.info(f"初始化校准数据存储: {self.path}")

    # ------------------------------------------------------------------ #
    #  读写
    # ------------------------------------------------------------------ #
    def _read(self) -> dict:
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write(self, data: dict) -> None:
        data["meta"] = data.get("meta", {})
        data["meta"]["updated_at"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        if "created_at" not in data["meta"]:
            data["meta"]["created_at"] = data["meta"]["updated_at"]
        _atomic_write(self.path, data)

    # ------------------------------------------------------------------ #
    #  P5.1 - 校准参数持久化
    # ------------------------------------------------------------------ #
    def save_calibration(
        self,
        device_mac: str,
        calibration_data: dict,
    ) -> dict:
        """保存校准结果到持久化存储。

        Args:
            device_mac: 设备MAC地址
            calibration_data: 校准参数字典，包含auto_focus/color_balance/speed_mapping/position_calibration

        Returns:
            保存的记录字典
        """
        with self._lock:
            data = self._read()
            records = data.setdefault("records", {})
            device_records = records.setdefault(device_mac, [])

            calibration_data["timestamp"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
            if "calibration_id" not in calibration_data:
                calibration_data["calibration_id"] = f"{device_mac}_{calibration_data['timestamp']}"

            device_records.append(calibration_data)
            self._write(data)
            LOG.info(f"校准数据已保存: device={device_mac}, id={calibration_data['calibration_id']}")
            return calibration_data

    # ------------------------------------------------------------------ #
    #  P5.2 - 校准历史查询
    # ------------------------------------------------------------------ #
    def get_calibration_history(
        self,
        device_mac: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """按设备/时间范围查询校准历史。

        Args:
            device_mac: 设备MAC地址，不指定则查询所有设备
            start_time: 起始时间（ISO格式）
            end_time: 结束时间（ISO格式）
            limit: 返回记录数限制

        Returns:
            校准历史记录列表
        """
        with self._lock:
            data = self._read()
            records = data.get("records", {})
            results = []

            if device_mac:
                # 查询指定设备
                device_records = records.get(device_mac, [])
                results.extend(device_records)
            else:
                # 查询所有设备
                for mac, device_records in records.items():
                    for record in device_records:
                        record_copy = record.copy()
                        record_copy["device_mac"] = mac
                        results.append(record_copy)

            # 时间过滤
            if start_time:
                results = [r for r in results if r.get("timestamp", "") >= start_time]
            if end_time:
                results = [r for r in results if r.get("timestamp", "") <= end_time]

            # 限制数量
            if limit:
                results = results[-limit:]

            LOG.info(f"校准历史查询: results={len(results)}")
            return results

    def get_latest_calibration(self, device_mac: str) -> dict | None:
        """获取设备最新的校准记录。

        Args:
            device_mac: 设备MAC地址

        Returns:
            最新校准记录，不存在返回None
        """
        with self._lock:
            data = self._read()
            records = data.get("records", {})
            device_records = records.get(device_mac, [])
            if device_records:
                latest = device_records[-1]
                LOG.info(f"最新校准查询: device={device_mac}, timestamp={latest.get('timestamp')}")
                return latest
            LOG.info(f"最新校准查询: device={device_mac}, 无记录")
            return None

    def get_calibration_by_id(self, calibration_id: str) -> dict | None:
        """通过校准ID查询记录。

        Args:
            calibration_id: 校准唯一标识

        Returns:
            校准记录，不存在返回None
        """
        with self._lock:
            data = self._read()
            records = data.get("records", {})
            for mac, device_records in records.items():
                for record in device_records:
                    if record.get("calibration_id") == calibration_id:
                        result = record.copy()
                        result["device_mac"] = mac
                        LOG.info(f"校准ID查询命中: id={calibration_id}")
                        return result
            LOG.info(f"校准ID查询未命中: id={calibration_id}")
            return None

    # ------------------------------------------------------------------ #
    #  辅助方法
    # ------------------------------------------------------------------ #
    def get_all_devices(self) -> list[str]:
        """获取所有有校准记录的设备MAC列表。"""
        with self._lock:
            data = self._read()
            return list(data.get("records", {}).keys())

    def get_device_calibration_count(self, device_mac: str) -> int:
        """获取设备的校准记录数。"""
        with self._lock:
            data = self._read()
            records = data.get("records", {})
            return len(records.get(device_mac, []))
