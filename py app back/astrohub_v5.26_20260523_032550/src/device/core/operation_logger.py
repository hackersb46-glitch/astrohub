"""
M2 Device Manager v1.0 - 操作日志模块

提供完整的操作日志记录、查询、导出、清理功能。
日志级别：info/warning/error/done/failed (P4.1)
支持毫秒级时间戳、操作者追踪、自动轮转、分页查询(P4.2)、多格式导出(P4.3)、过期清理(P4.4)。
"""

import csv
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from device.constants import LOG_DIR, ACCEPTED_LOG_LEVELS, LOG_RETENTION_DAYS, DATA_DIR
from device.core.mac_utils import normalize_mac, validate_mac


class OperationLogger:
    """操作日志器：自动创建目录、生成日志文件、支持查询/导出/清理。

    日志格式: [level] yyyymmdd-hhmmss.mmm - operator - device_mac - operation - details
    存储目录: log/
    文件名: ops_yyyymmdd-NNN.md
    索引文件: data/ops_log_index.json (用于快速查询)
    """

    def __init__(self, log_dir: Path | None = None, retention_days: int = LOG_RETENTION_DAYS) -> None:
        self.log_dir = log_dir or LOG_DIR
        self.retention_days = retention_days
        self.index_path = DATA_DIR / "ops_log_index.json"
        self._log_file: Path | None = None
        self._ensure_directories()
        self._init_index()
        self._load_current_file()

    # ------------------------------------------------------------------ #
    #  初始化
    # ------------------------------------------------------------------ #
    def _ensure_directories(self) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    def _init_index(self) -> None:
        """初始化日志索引文件。"""
        if not self.index_path.exists():
            self._write_index({"logs": [], "meta": {"created_at": _now_iso()}})

    def _load_current_file(self) -> None:
        """加载或创建今天的最新日志文件。"""
        today = datetime.now().strftime("%Y%m%d")
        existing = list(self.log_dir.glob(f"ops_{today}-*.md"))

        if existing:
            # 找到序号最大的文件
            max_seq = 0
            max_file = None
            for f in existing:
                stem = f.stem
                parts = stem.rsplit("-", 1)
                if len(parts) == 2:
                    try:
                        seq = int(parts[1])
                        if seq > max_seq:
                            max_seq = seq
                            max_file = f
                    except ValueError:
                        continue
            self._log_file = max_file
        else:
            # 创建新文件 - 需要找到全局最大序号
            all_ops = list(self.log_dir.glob("ops_*.md"))
            global_max_seq = 0
            for f in all_ops:
                # 格式: ops_yyyymmdd-NNN.md
                stem = f.stem  # ops_yyyymmdd-NNN
                parts = stem.rsplit("-", 1)
                if len(parts) == 2:
                    try:
                        seq = int(parts[1])
                        if seq > global_max_seq:
                            global_max_seq = seq
                    except ValueError:
                        continue
            seq = global_max_seq + 1 if global_max_seq > 0 else 1
            self._log_file = self.log_dir / f"ops_{today}-{seq:03d}.md"

    # ------------------------------------------------------------------ #
    #  索引管理
    # ------------------------------------------------------------------ #
    def _read_index(self) -> dict:
        """读取索引文件。"""
        with open(self.index_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_index(self, data: dict) -> None:
        """写入索引文件。"""
        _atomic_write_json(self.index_path, data)

    # ------------------------------------------------------------------ #
    #  日志写入 (P4.1)
    # ------------------------------------------------------------------ #
    def log(self, level: str, operation: str, details: str,
            operator: str = "system", device_mac: str | None = None) -> None:
        """记录操作日志。

        Args:
            level: 日志级别 [info|warning|error|done|failed]
            operation: 操作名称 (如 "create_device", "delete_group")
            details: 操作详情描述
            operator: 操作者 (默认 "system")
            device_mac: 关联设备MAC (可选)
        """
        level_lower = level.lower()
        if level_lower not in ACCEPTED_LOG_LEVELS:
            raise ValueError(
                f"未知日志级别 '{level}'，支持的级别: {', '.join(sorted(ACCEPTED_LOG_LEVELS))}"
            )

        # 标准化MAC
        norm_mac = None
        if device_mac:
            is_valid, err = validate_mac(device_mac)
            if is_valid:
                norm_mac = normalize_mac(device_mac)
            else:
                norm_mac = device_mac  # 保留原始值用于错误追踪

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S.%f")[:-3]
        iso_timestamp = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        line = f"[{level_lower}] {timestamp} - {operator} - {operation} - {details}"
        if norm_mac:
            line = f"[{level_lower}] {timestamp} - {operator} - {norm_mac} - {operation} - {details}"

        # 确保日志文件存在
        if self._log_file is None or not self._log_file.exists():
            self._load_current_file()

        # 写文件 (追加模式)
        with open(self._log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")

        # 输出到控制台
        print(line)

        # 写入索引 (用于查询)
        index_entry = {
            "timestamp": iso_timestamp,
            "timestamp_display": timestamp,
            "level": level_lower,
            "operator": operator,
            "device_mac": norm_mac,
            "operation": operation,
            "details": details,
            "file": self._log_file.name,
        }
        index = self._read_index()
        index["logs"].append(index_entry)
        self._write_index(index)

    # ------------------------------------------------------------------ #
    #  便捷级别方法
    # ------------------------------------------------------------------ #
    def info(self, operation: str, details: str, operator: str = "system", device_mac: str | None = None) -> None:
        self.log("info", operation, details, operator, device_mac)

    def warning(self, operation: str, details: str, operator: str = "system", device_mac: str | None = None) -> None:
        self.log("warning", operation, details, operator, device_mac)

    def error(self, operation: str, details: str, operator: str = "system", device_mac: str | None = None) -> None:
        self.log("error", operation, details, operator, device_mac)

    def done(self, operation: str, details: str, operator: str = "system", device_mac: str | None = None) -> None:
        self.log("done", operation, details, operator, device_mac)

    def failed(self, operation: str, details: str, operator: str = "system", device_mac: str | None = None) -> None:
        self.log("failed", operation, details, operator, device_mac)

    # ------------------------------------------------------------------ #
    #  日志查询 (P4.2)
    # ------------------------------------------------------------------ #
    def query_logs(
        self,
        level: str | None = None,
        device_mac: str | None = None,
        operation: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        """按条件过滤查询日志，支持分页。

        Args:
            level: 日志级别过滤
            device_mac: 设备MAC过滤
            operation: 操作类型过滤
            start_date: 起始日期 (ISO格式: YYYY-MM-DD)
            end_date: 结束日期 (ISO格式)
            page: 页码 (从1开始)
            page_size: 每页条数

        Returns:
            {
                "total": int,
                "page": int,
                "page_size": int,
                "logs": [
                    {
                        "timestamp": str,
                        "level": str,
                        "operator": str,
                        "device_mac": str|None,
                        "operation": str,
                        "details": str,
                    }
                ]
            } (P4.2)
        """
        # 标准化MAC
        norm_mac = None
        if device_mac:
            is_valid, _ = validate_mac(device_mac)
            norm_mac = normalize_mac(device_mac) if is_valid else device_mac

        index = self._read_index()
        all_logs = index.get("logs", [])

        # 过滤
        filtered = []
        for entry in all_logs:
            # 级别过滤
            if level and entry.get("level") != level.lower():
                continue
            # 设备MAC过滤
            if norm_mac and entry.get("device_mac") != norm_mac:
                continue
            # 操作类型过滤
            if operation and entry.get("operation") != operation:
                continue
            # 时间范围过滤
            ts = entry.get("timestamp", "")
            if start_date and ts < start_date.replace("-", ""):
                continue
            if end_date and ts > end_date.replace("-", "") + "999999":
                continue
            filtered.append(entry)

        # 按时间倒序
        filtered.reverse()

        # 分页
        total = len(filtered)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_logs = filtered[start_idx:end_idx]

        # 清理输出格式
        output_logs = []
        for entry in page_logs:
            output_logs.append({
                "timestamp": entry.get("timestamp_display", entry.get("timestamp", "")),
                "level": entry.get("level", ""),
                "operator": entry.get("operator", ""),
                "device_mac": entry.get("device_mac"),
                "operation": entry.get("operation", ""),
                "details": entry.get("details", ""),
            })

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "logs": output_logs,
        }

    # ------------------------------------------------------------------ #
    #  日志导出 (P4.3)
    # ------------------------------------------------------------------ #
    def export_logs(
        self,
        output_path: str | Path,
        fmt: str = "json",
        level: str | None = None,
        device_mac: str | None = None,
        operation: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Path:
        """导出日志为文件（支持JSON/CSV/MD）。

        Args:
            output_path: 输出文件路径
            fmt: 导出格式 ("json", "csv", "md")
            level/device_mac/operation/start_date/end_date: 过滤条件

        Returns:
            输出文件路径
        """
        # 先获取所有数据（不分页）
        result = self.query_logs(
            level=level, device_mac=device_mac, operation=operation,
            start_date=start_date, end_date=end_date,
            page=1, page_size=999999  # 获取全部
        )
        logs = result["logs"]

        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if fmt.lower() == "json":
            self._export_json(out_path, logs)
        elif fmt.lower() == "csv":
            self._export_csv(out_path, logs)
        elif fmt.lower() == "md":
            self._export_md(out_path, logs)
        else:
            raise ValueError(f"不支持的导出格式: {fmt}，支持: json, csv, md")

        log_msg = f"日志导出: {fmt.upper()} {len(logs)}条 → {out_path.name}"
        self.done("export_logs", log_msg)
        return out_path

    def _export_json(self, path: Path, logs: list[dict]) -> None:
        _atomic_write_json(path, {"logs": logs, "exported_at": _now_iso()})

    def _export_csv(self, path: Path, logs: list[dict]) -> None:
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            # 表头
            writer.writerow(["timestamp", "level", "operator", "device_mac", "operation", "details"])
            for entry in logs:
                writer.writerow([
                    entry.get("timestamp", ""),
                    entry.get("level", ""),
                    entry.get("operator", ""),
                    entry.get("device_mac", ""),
                    entry.get("operation", ""),
                    entry.get("details", ""),
                ])

    def _export_md(self, path: Path, logs: list[dict]) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write("# 操作日志\n\n")
            f.write(f"导出时间: {datetime.now().isoformat()}\n")
            f.write(f"记录数: {len(logs)}\n\n")
            f.write("| 时间 | 级别 | 操作者 | 设备MAC | 操作 | 详情 |\n")
            f.write("|------|------|--------|---------|------|------|\n")
            for entry in logs:
                f.write(f"| {entry.get('timestamp', '')} | {entry.get('level', '')} | "
                        f"{entry.get('operator', '')} | {entry.get('device_mac', '')} | "
                        f"{entry.get('operation', '')} | {entry.get('details', '')} |\n")

    # ------------------------------------------------------------------ #
    #  日志清理 (P4.4)
    # ------------------------------------------------------------------ #
    def cleanup_logs(self, retention_days: int | None = None) -> dict:
        """清理过期日志。

        Args:
            retention_days: 保留天数，默认使用配置的retention_days（P4.4: 默认30天）

        Returns:
            {
                "cleaned_files": int,
                "cleaned_entries": int,
                "retention_days": int
            }
        """
        days = retention_days if retention_days is not None else self.retention_days
        cutoff_date = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff_date.strftime("%Y-%m-%d")

        index = self._read_index()
        all_logs = index.get("logs", [])

        # 过滤保留的日志
        preserved = []
        cleaned_count = 0
        for entry in all_logs:
            ts = entry.get("timestamp", "")
            if ts >= cutoff_str.replace("-", ""):
                preserved.append(entry)
            else:
                cleaned_count += 1

        # 更新索引
        index["logs"] = preserved
        index["meta"] = index.get("meta", {})
        index["meta"]["last_cleanup"] = _now_iso()
        index["meta"]["last_cleanup_days"] = days
        self._write_index(index)

        # 清理无用的日志文件
        cleaned_files = self._clean_empty_log_files()

        # 记录清理操作
        self.info("log_cleanup", f"清理 {days} 天前的日志: {cleaned_count}条记录, {cleaned_files}个文件")

        return {
            "cleaned_entries": cleaned_count,
            "cleaned_files": cleaned_files,
            "retention_days": days,
        }

    def _clean_empty_log_files(self) -> int:
        """删除无日志条目的日志文件。"""
        cleaned = 0
        # 获取索引中引用的文件名
        index = self._read_index()
        referenced_files = {entry.get("file") for entry in index.get("logs", [])}

        # 查找所有操作日志文件
        for log_file in self.log_dir.glob("ops_*.md"):
            if log_file.name not in referenced_files:
                # 检查文件是否为空
                if log_file.stat().st_size == 0:
                    log_file.unlink()
                    cleaned += 1

        return cleaned

    def rotate(self) -> None:
        """强制轮转，创建新的日志文件。"""
        self._log_file = None
        self._load_current_file()
        self.info("log_rotate", f"日志轮转到: {self._log_file.name}" if self._log_file else "日志轮转")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _atomic_write_json(path: Path, data: dict) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = str(path.parent / f".tmp_{path.name}")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# === 模块级单例 ===
OPS_LOG = OperationLogger()
