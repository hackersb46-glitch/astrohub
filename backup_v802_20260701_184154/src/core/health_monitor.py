"""
AstroHub v2.0 - 系统健康监控

提供 CPU、内存、磁盘、端口及各模块的健康状态检查。
"""

from __future__ import annotations

import socket
from typing import Any

import psutil

from src.config import PROJECT_NAME, VERSION
from src.logger import get_logger

log = get_logger("health_monitor")

# === 阈值定义 ===
CPU_THRESHOLD = 80       # CPU 使用率告警阈值 (%)
MEMORY_THRESHOLD = 85    # 内存使用率告警阈值 (%)
DISK_THRESHOLD = 90      # 磁盘使用率告警阈值 (%)


class HealthMonitor:
    """系统健康监控器。

    提供资源使用率检查、端口探测及模块状态汇总。
    """

    def __init__(self) -> None:
        """初始化健康监控。"""
        self._alerts: list[dict[str, Any]] = []
        self._module_status: dict[str, dict[str, Any]] = {}
        log.info("HealthMonitor initialized")

    # ──────────────────────────────
    #  资源检查
    # ──────────────────────────────

    def check_cpu(self) -> dict[str, Any]:
        """检查 CPU 使用率。

        Returns:
            包含 usage_percent、threshold、status 的字典。
        """
        usage = psutil.cpu_percent(interval=1)
        status = "critical" if usage > CPU_THRESHOLD else "healthy"

        if status == "critical":
            alert = {
                "type": "cpu",
                "message": f"CPU 使用率 {usage:.1f}% 超过阈值 {CPU_THRESHOLD}%",
                "severity": "critical",
            }
            self._alerts.append(alert)
            log.warning(alert["message"])

        return {
            "usage_percent": round(usage, 1),
            "threshold": CPU_THRESHOLD,
            "status": status,
        }

    def check_memory(self) -> dict[str, Any]:
        """检查内存使用率。

        Returns:
            包含 total、used、available、usage_percent、threshold、status 的字典。
        """
        mem = psutil.virtual_memory()
        usage = mem.percent
        status = "critical" if usage > MEMORY_THRESHOLD else "healthy"

        if status == "critical":
            alert = {
                "type": "memory",
                "message": f"内存使用率 {usage:.1f}% 超过阈值 {MEMORY_THRESHOLD}%",
                "severity": "critical",
            }
            self._alerts.append(alert)
            log.warning(alert["message"])

        return {
            "total": round(mem.total / (1024**3), 2),    # GB
            "used": round(mem.used / (1024**3), 2),      # GB
            "available": round(mem.available / (1024**3), 2),
            "usage_percent": round(usage, 1),
            "threshold": MEMORY_THRESHOLD,
            "status": status,
        }

    def check_disk(self, path: str = "/") -> dict[str, Any]:
        """检查磁盘使用率。

        Args:
            path: 要检查的挂载点路径，默认为根目录。

        Returns:
            包含 total、used、free、usage_percent、threshold、status 的字典。
        """
        try:
            disk = psutil.disk_usage(path)
        except FileNotFoundError:
            log.error("Disk path not found: %s", path)
            return {
                "total": 0,
                "used": 0,
                "free": 0,
                "usage_percent": 0,
                "threshold": DISK_THRESHOLD,
                "status": "unknown",
            }

        usage = disk.percent
        status = "critical" if usage > DISK_THRESHOLD else "healthy"

        if status == "critical":
            alert = {
                "type": "disk",
                "message": f"磁盘 {path} 使用率 {usage:.1f}% 超过阈值 {DISK_THRESHOLD}%",
                "severity": "critical",
            }
            self._alerts.append(alert)
            log.warning(alert["message"])

        return {
            "path": path,
            "total": round(disk.total / (1024**3), 2),   # GB
            "used": round(disk.used / (1024**3), 2),     # GB
            "free": round(disk.free / (1024**3), 2),     # GB
            "usage_percent": round(usage, 1),
            "threshold": DISK_THRESHOLD,
            "status": status,
        }

    def check_port(self, port: int) -> dict[str, Any]:
        """检查端口可用性。

        Args:
            port: 要检查的端口号。

        Returns:
            包含 port、status、message 的字典。
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            result = sock.connect_ex(("127.0.0.1", port))

        if result == 0:
            status = "open"
            message = f"端口 {port} 已开放"
            log.debug(message)
        else:
            status = "closed"
            message = f"端口 {port} 未开放或无法访问"
            log.debug(message)

        return {
            "port": port,
            "status": status,
            "message": message,
        }

    # ──────────────────────────────
    #  综合检查
    # ──────────────────────────────

    def check_all(self) -> dict[str, Any]:
        """执行全面系统检查（CPU + 内存 + 磁盘）。

        Returns:
            包含 cpu、memory、disk 各检查结果的字典。
        """
        self._alerts.clear()

        result = {
            "cpu": self.check_cpu(),
            "memory": self.check_memory(),
            "disk": self.check_disk(),
        }

        overall = "healthy"
        for check in result.values():
            if check.get("status") == "critical":
                overall = "critical"
                break

        return {
            "overall": overall,
            **result,
        }

    def get_system_health(self) -> dict[str, Any]:
        """获取系统健康状态快照。

        Returns:
            包含系统元信息及当前资源状态的字典。
        """
        cpu = self.check_cpu()
        memory = self.check_memory()
        disk = self.check_disk()

        overall = "healthy"
        if cpu["status"] == "critical" or memory["status"] == "critical" or disk["status"] == "critical":
            overall = "critical"

        return {
            "project": PROJECT_NAME,
            "version": VERSION,
            "overall": overall,
            "cpu": cpu,
            "memory": memory,
            "disk": disk,
            "active_alerts": len(self._alerts),
        }

    def get_alerts(self) -> list[dict[str, Any]]:
        """获取当前告警列表。

        Returns:
            告警字典列表，每项包含 type、message、severity。
        """
        return self._alerts.copy()

    # ──────────────────────────────
    #  模块状态
    # ──────────────────────────────

    def check_module_status(self, module_name: str) -> dict[str, Any]:
        """检查指定模块的运行状态。

        Args:
            module_name: 模块名称。

        Returns:
            包含 module_name、status、last_check 的字典。
        """
        import datetime

        status_info = self._module_status.get(module_name, {
            "module_name": module_name,
            "status": "unknown",
            "last_check": datetime.datetime.now().isoformat(),
        })

        log.debug("Query module status: %s -> %s", module_name, status_info["status"])
        return status_info

    def get_all_module_status(self) -> dict[str, dict[str, Any]]:
        """获取所有已注册模块的状态。

        Returns:
            模块名称到状态字典的映射。
        """
        return self._module_status.copy()
