"""
M2 Device Manager v1.0 - JSON 存储模块

提供基于JSON的持久化存储，支持原子写入、线程安全、数据校验。
参考 M1: src/ptz/core/config.py 的 _atomic_write 和 ConfigManager 模式。
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from device.core.logger import LOG
from device.constants import DATA_DIR


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


class JsonStore:
    """通用JSON存储，支持线程安全的读写、原子写入。

    数据结构:
        {
            "meta": {"created_at": ..., "updated_at": ..., "version": 1},
            "records": {key: record, ...}
        }
    """

    def __init__(self, file_path: str | Path, default: dict | None = None) -> None:
        self.path = _ensure_json(file_path).resolve()
        self._default = default or {"records": {}}
        self._lock = Lock()
        self._ensure_file()

    # ------------------------------------------------------------------ #
    #  文件初始化
    # ------------------------------------------------------------------ #
    def _ensure_file(self) -> None:
        if not self.path.exists():
            _atomic_write(self.path, self._default)
            LOG.info(f"初始化 JSON 存储: {self.path}")

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
    #  CRUD 操作
    # ------------------------------------------------------------------ #
    def get(self, key: str) -> dict | None:
        """通过键获取记录。

        Args:
            key: 记录的唯一键

        Returns:
            记录字典，不存在则返回None
        """
        with self._lock:
            data = self._read()
            record = data.get("records", {}).get(key)
            if record:
                LOG.info(f"存储查询命中: key={key}")
            else:
                LOG.info(f"存储查询未命中: key={key}")
            return record

    def list_all(self) -> list[dict]:
        """获取所有记录的列表。

        Returns:
            包含所有记录的列表
        """
        with self._lock:
            data = self._read()
            records = list(data.get("records", {}).values())
            LOG.info(f"存储查询全部: count={len(records)}")
            return records

    def all_keys(self) -> list[str]:
        """获取所有记录的键列表。

        Returns:
            包含所有键的列表
        """
        with self._lock:
            data = self._read()
            return list(data.get("records", {}).keys())

    def set(self, key: str, record: dict) -> None:
        """设置或更新记录（非原子创建/更新）。

        Args:
            key: 记录的唯一键
            record: 记录字典
        """
        with self._lock:
            data = self._read()
            records = data.setdefault("records", {})
            record["updated_at"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
            if key not in records:
                record["created_at"] = record.get("created_at", record["updated_at"])
            records[key] = record
            self._write(data)
            LOG.info(f"存储写入: key={key}")

    def delete(self, key: str) -> bool:
        """删除指定键的记录。

        Args:
            key: 记录的唯一键

        Returns:
            True=删除成功, False=记录不存在
        """
        with self._lock:
            data = self._read()
            records = data.get("records", {})
            if key not in records:
                LOG.info(f"存储删除: 记录不存在 key={key}")
                return False
            del records[key]
            data["records"] = records
            self._write(data)
            LOG.info(f"存储删除成功: key={key}")
            return True

    def has(self, key: str) -> bool:
        """检查键是否存在。

        Args:
            key: 记录的唯一键

        Returns:
            True=存在, False=不存在
        """
        with self._lock:
            data = self._read()
            return key in data.get("records", {})

    def get_meta(self) -> dict:
        """获取存储元数据。

        Returns:
            元数据字典
        """
        with self._lock:
            data = self._read()
            return data.get("meta", {})

    def count(self) -> int:
        """获取记录总数。

        Returns:
            记录数
        """
        with self._lock:
            data = self._read()
            return len(data.get("records", {}))

    def clear(self) -> None:
        """清空所有记录。"""
        with self._lock:
            data = self._read()
            data["records"] = {}
            self._write(data)
            LOG.info("存储清空: 所有记录已删除")
