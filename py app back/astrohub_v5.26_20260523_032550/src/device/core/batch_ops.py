"""
M2 Device Manager v1.0 - 批量导入/导出操作

实现设备批量导入(P0.5)与导出(P0.6)。
支持 JSON/CSV 文件解析、MAC格式校验、必填字段校验、部分失败容错。
返回 success_count/failure_count/failure_details。

Author: 雅痞张@南方天文
"""

import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from device.core.device_manager import DeviceManager
from device.core.logger import LOG
from device.core.mac_utils import normalize_mac, validate_mac
from device.models.schemas import BatchImportResult, DeviceCreate


# === 必填字段 (对应 DeviceCreate) ===
REQUIRED_FIELDS = {"mac", "ip", "model", "username", "password"}


# === 异常定义 ===

class BatchImportError(Exception):
    """批量导入基础异常。"""
    pass


class FileReadError(BatchImportError):
    """文件读取失败。"""
    pass


class ParseError(BatchImportError):
    """文件格式解析失败。"""
    pass


# === 数据类 ===

@dataclass
class BatchImportReport:
    """批量导入详细报告。"""
    total: int = 0
    success_count: int = 0
    failure_count: int = 0
    failure_details: list[dict] = field(default_factory=list)

    def add_success(self) -> None:
        self.success_count += 1

    def add_failure(self, row_index: int, mac: str, error: str) -> None:
        self.failure_count += 1
        self.failure_details.append({
            "row": row_index,
            "mac": mac or "(missing)",
            "error": error,
        })

    def to_result(self) -> BatchImportResult:
        """转换为 Pydantic 模型。"""
        return BatchImportResult(
            success_count=self.success_count,
            failure_count=self.failure_count,
            failures=self.failure_details,
        )


# === 文件解析 ===

def _parse_json_file(file_path: Path) -> list[dict[str, Any]]:
    """解析 JSON 批量导入文件。

    支持格式:
        - 对象数组: [{mac, ip, ...}, ...]
        - 含 meta/records 结构: {"records": {...}}（转换为 records values）

    Args:
        file_path: JSON 文件路径

    Returns:
        设备数据字典列表

    Raises:
        ParseError: 当 JSON 结构不符合预期
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        raise ParseError(f"JSON 解析失败: {e}")

    if isinstance(raw, list):
        return raw

    if isinstance(raw, dict):
        # 支持 {"records": {mac: record, ...}} 格式
        if "records" in raw and isinstance(raw["records"], dict):
            return list(raw["records"].values())
        # 支持 {"devices": [...]} 格式
        if "devices" in raw and isinstance(raw["devices"], list):
            return raw["devices"]

    raise ParseError("JSON 格式不支持：需要对象数组或含 records/devices 键的对象")


def _parse_csv_file(file_path: Path) -> list[dict[str, Any]]:
    """解析 CSV 批量导入文件。

    要求首行为列头（mac, ip, model, username, password, port, notes）。

    Args:
        file_path: CSV 文件路径

    Returns:
        设备数据字典列表
    """
    try:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            content = f.read()
    except UnicodeDecodeError:
        with open(file_path, "r", encoding="gbk") as f:
            content = f.read()

    try:
        reader = csv.DictReader(io.StringIO(content))
        rows: list[dict[str, Any]] = []
        for row in reader:
            # CSV 值全部为字符串，需要类型转换
            converted: dict[str, Any] = {}
            for k, v in row.items():
                if k is None:
                    continue
                key = k.strip()
                value = v.strip() if v else ""
                converted[key] = value

            # port 转 int
            if "port" in converted and converted["port"]:
                try:
                    converted["port"] = int(converted["port"])
                except ValueError:
                    converted["port"] = 80  # 默认值，后续校验会处理
            else:
                converted["port"] = 80

            rows.append(converted)
        return rows
    except csv.Error as e:
        raise ParseError(f"CSV 解析失败: {e}")


def parse_import_file(file_path: str | Path) -> list[dict[str, Any]]:
    """根据文件扩展名自动选择解析器。

    Args:
        file_path: 导入文件路径

    Returns:
        设备数据字典列表

    Raises:
        FileReadError: 文件不存在或格式不支持
        ParseError: 文件内容解析失败
    """
    path = Path(file_path)

    if not path.exists():
        raise FileReadError(f"导入文件不存在: {path}")

    suffix = path.suffix.lower()
    if suffix == ".json":
        return _parse_json_file(path)
    if suffix == ".csv":
        return _parse_csv_file(path)

    raise FileReadError(f"不支持的文件格式: '{suffix}'，仅支持 .json / .csv")


# === 校验逻辑 ===

def _validate_row(row: dict[str, Any], row_index: int) -> tuple[bool, str]:
    """校验单行数据的必填字段与 MAC 格式。

    Args:
        row: 设备数据行
        row_index: 行号（用于错误报告）

    Returns:
        (is_valid, error_message)
    """
    # 必填字段
    missing = REQUIRED_FIELDS - set(row.keys()) - {k for k, v in row.items() if v}
    # 更精确的缺失检测：key 不存在或值为空字符串
    missing = set()
    for f in REQUIRED_FIELDS:
        val = row.get(f)
        if val is None or (isinstance(val, str) and not val.strip()):
            missing.add(f)

    if missing:
        return False, f"缺少必填字段: {', '.join(sorted(missing))}"

    # MAC 格式校验
    mac_raw = str(row.get("mac", "")).strip()
    is_valid, error = validate_mac(mac_raw)
    if not is_valid:
        return False, error

    # IP 基本校验（非空）
    ip = row.get("ip", "").strip() if isinstance(row.get("ip"), str) else str(row.get("ip", ""))
    if not ip:
        return False, "IP 地址不能为空"

    return True, ""


# === 导出逻辑 ===

def export_devices(
    file_path: str | Path,
    fmt: str = "json",
    devices: list[dict] | None = None,
    db_file: str | Path | None = None,
) -> dict:
    """导出设备数据到文件 (P0.6)。

    Args:
        file_path: 导出文件路径
        fmt: 导出格式 ('json' | 'csv')
        devices: 设备列表，为 None 时导出全部设备
        db_file: 设备数据库文件路径

    Returns:
        {"success": True, "count": N, "file_path": str}
    """
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # 获取设备数据
    if devices is None:
        manager = DeviceManager(db_file=db_file)
        devices = manager.list_devices()

    # 过滤内部字段（不导出 password）
    safe_devices = []
    for dev in devices:
        safe = {k: v for k, v in dev.items() if k != "password"}
        safe_devices.append(safe)

    fmt = fmt.lower()

    if fmt == "json":
        with open(path, "w", encoding="utf-8") as f:
            json.dump(safe_devices, f, indent=2, ensure_ascii=False)
    elif fmt == "csv":
        if not safe_devices:
            # 空数据写入空 CSV（仅列头）
            headers = ["mac", "ip", "model", "username", "port", "notes", "status", "heartbeat_status"]
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
        else:
            headers = list(safe_devices[0].keys())
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                writer.writerows(safe_devices)
    else:
        return {"success": False, "error": f"不支持的导出格式: '{fmt}'，仅支持 json/csv"}

    LOG.done(f"设备导出成功: {path} ({len(safe_devices)} 条, format={fmt})")
    return {"success": True, "count": len(safe_devices), "file_path": str(path)}


# === 批量导入 ===

def batch_import(
    file_path: str | Path,
    db_file: str | Path | None = None,
    skip_duplicates: bool = True,
) -> BatchImportResult:
    """批量导入设备 (P0.5)。

    流程:
        1. 解析 JSON/CSV 文件
        2. 逐行校验必填字段与 MAC 格式
        3. 跳过已存在的 MAC（skip_duplicates=True）或报错
        4. 批量写入，部分失败不退卷
        5. 返回 success_count/failure_count/failure_details

    Args:
        file_path: 批量导入文件路径
        db_file: 设备数据库文件路径
        skip_duplicates: 是否跳过已存在的 MAC（True=跳过计入 failure；False=报错计入 failure）

    Returns:
        BatchImportResult(success_count, failure_count, failures)
    """
    path = Path(file_path)
    LOG.info(f"开始批量导入: {path}")

    # 1. 解析文件
    try:
        rows = parse_import_file(path)
    except (FileReadError, ParseError) as e:
        LOG.failed(f"批量导入文件解析失败: {e}")
        return BatchImportResult(
            success_count=0,
            failure_count=0,
            failures=[{"row": 0, "mac": "(file)", "error": str(e)}],
        )

    if not rows:
        LOG.warning("批量导入文件为空，无数据可导入")
        return BatchImportResult(success_count=0, failure_count=0, failures=[])

    # 2. 初始化设备管理器
    manager = DeviceManager(db_file=db_file)
    report = BatchImportReport(total=len(rows))

    # 3. 逐行校验并导入
    for idx, row in enumerate(rows, start=1):
        # 字段校验
        is_valid, error = _validate_row(row, idx)
        if not is_valid:
            mac_raw = str(row.get("mac", "")).strip() if row.get("mac") else ""
            report.add_failure(idx, mac_raw, error)
            continue

        # MAC 标准化
        mac_normalized = normalize_mac(str(row["mac"]).strip())
        row["mac"] = mac_normalized

        # MAC 唯一性校验
        if skip_duplicates and manager.mac_exists(mac_normalized):
            report.add_failure(idx, mac_normalized, f"MAC 已存在，跳过")
            continue

        if manager.mac_exists(mac_normalized):
            report.add_failure(idx, mac_normalized, "MAC 已存在")
            continue

        # 构建 DeviceCreate 并写入
        try:
            device_data = DeviceCreate(
                mac=row["mac"],
                ip=str(row["ip"]).strip(),
                model=str(row["model"]).strip(),
                username=str(row["username"]).strip(),
                password=str(row.get("password", "")).strip(),
                port=int(row.get("port", 80)),
                notes=str(row.get("notes", "")).strip() if row.get("notes") else "",
            )
            result = manager.create_device(device_data)
            if result.get("success"):
                report.add_success()
            else:
                report.add_failure(idx, mac_normalized, result.get("error", "未知错误"))
        except Exception as e:
            report.add_failure(idx, mac_normalized, str(e))

    # 4. 输出报告
    result = report.to_result()
    LOG.done(
        f"批量导入完成: {path} | "
        f"总计={report.total}, 成功={result.success_count}, "
        f"失败={result.failure_count}"
    )
    if result.failure_details:
        for f_detail in result.failure_details:
            LOG.warning(f"  行 {f_detail['row']} | MAC={f_detail['mac']} | {f_detail['error']}")

    return result
