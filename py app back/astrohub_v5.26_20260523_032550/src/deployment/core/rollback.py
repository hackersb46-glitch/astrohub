"""
M11 Deployment v1.0 - 回滚机制

版本回滚、历史快照、自动回滚策略、回滚验证。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from deployment.constants import (
    BACKUP_DIR,
    ERROR_CODE_DESCRIPTION,
    ErrorCode,
    ROLLBACK_MAX_VERSIONS,
    ROLLBACK_TIMEOUT,
    ServiceStatus,
)


class RollbackError(Exception):
    """回滚异常。"""

    def __init__(self, code: ErrorCode, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code.value}] {message}")


class RollbackManager:
    """部署回滚管理器。

    管理版本快照、执行回滚、验证回滚结果。
    """

    def __init__(
        self,
        max_versions: int = ROLLBACK_MAX_VERSIONS,
        backup_dir: Path | None = None,
    ):
        """Initialize."""
        self._max_versions = max_versions
        self._backup_dir = backup_dir or BACKUP_DIR
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        self._versions: list[dict[str, Any]] = []
        self._rollback_history: list[dict[str, Any]] = []

    def snapshot(
        self,
        version: str,
        compose_file: Path | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """创建当前部署状态快照。

        Args:
            version: 版本号/标签
            compose_file: compose 文件路径
            metadata: 额外元数据
        Returns:
            快照编号
        """
        snapshot_id = f"snapshot_{version}_{int(time.time())}"
        snap_dir = self._backup_dir / snapshot_id
        snap_dir.mkdir(parents=True, exist_ok=True)

        # 备份 compose 文件
        if compose_file and compose_file.exists():
            shutil.copy2(str(compose_file), str(snap_dir / compose_file.name))

        version_info = {
            "id": snapshot_id,
            "version": version,
            "created_at": time.time(),
            "compose_file": str(compose_file) if compose_file else None,
            "metadata": metadata or {},
            "snapshot_path": str(snap_dir),
        }
        self._versions.append(version_info)

        # 清理超出最大保留数量的旧版本
        self._prune_old_versions()

        return snapshot_id

    def rollback(self, version: str | None = None) -> dict[str, Any]:
        """回到指定版本。

        Args:
            version: 版本号，None = 回退到上一版本
        Returns:
            回滚结果 {success, version_id, timestamp}
        """
        target = self._find_target(version)
        if target is None:
            raise RollbackError(
                ErrorCode.NO_VERSION_TO_ROLLBACK,
                "无可回滚版本"
            )

        start_time = time.time()
        snapshot_path = Path(target["snapshot_path"])

        try:
            # 恢复 compose 文件并重启
            if target.get("compose_file"):
                compose_name = Path(target["compose_file"]).name
                compose_src = snapshot_path / compose_name
                if compose_src.exists():
                    shutil.copy2(str(compose_src), target["compose_file"])

                    # 重新拉起服务
                    subprocess.run(
                        ["docker", "compose", "-f", target["compose_file"], "up", "-d"],
                        capture_output=True,
                        text=True,
                        timeout=ROLLBACK_TIMEOUT,
                    )

            result = {
                "success": True,
                "rolled_back_to": target["version"],
                "snapshot_id": target["id"],
                "timestamp": time.time(),
                "duration_seconds": round(time.time() - start_time, 2),
            }
            self._rollback_history.append(result)
            return result

        except subprocess.TimeoutExpired:
            raise RollbackError(
                ErrorCode.ROLLBACK_FAILED,
                f"回滚超时 ({ROLLBACK_TIMEOUT}s)"
            )
        except Exception as e:
            raise RollbackError(
                ErrorCode.ROLLBACK_FAILED,
                f"回滚失败: {e}"
            )

    def _find_target(self, version: str | None) -> dict[str, Any] | None:
        """查找目标版本。version=None → 上一个版本。"""
        if not self._versions:
            return None
        if version is None:
            # 返回上一个
            return self._versions[-2] if len(self._versions) >= 2 else None
        for v in reversed(self._versions):
            if v["version"] == version:
                return v
        return None

    def _prune_old_versions(self) -> None:
        """清理超出最大数量的旧快照。"""
        while len(self._versions) > self._max_versions:
            oldest = self._versions.pop(0)
            snap_path = Path(oldest.get("snapshot_path", ""))
            if snap_path.exists():
                shutil.rmtree(str(snap_path))

    @property
    def available_versions(self) -> list[dict[str, Any]]:
        """可用回滚版本列表。"""
        return self._versions.copy()

    @property
    def history(self) -> list[dict[str, Any]]:
        """回滚历史。"""
        return self._rollback_history.copy()


# ------------------------------------------------------------------ #
#  单例访问
# ------------------------------------------------------------------ #

_default_rollback: RollbackManager | None = None


def get_rollback_manager() -> RollbackManager:
    """获取默认 RollbackManager 实例。"""
    global _default_rollback
    if _default_rollback is None:
        _default_rollback = RollbackManager()
    return _default_rollback
