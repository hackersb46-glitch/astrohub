"""
PTZ_ASTRO v1.1 - 文件打包模块
将脚本和依赖打包到 D:/PY APP/TBD/v1.1/ 目录，仅包含运行文件，不含临时文件。

Author: 雅痞张@南方天文
"""

import shutil
from pathlib import Path

from src.ptz.core.logger import LOG
from src.ptz.constants import VERSION, PACKAGE_DEST, BASE_DIR


class ReportPackager:
    """文件打包器。"""

    def __init__(self) -> None:
        self.version = VERSION
        self.dest_dir = PACKAGE_DEST / f"v{self.version}"

    # --- 排除的文件/目录 ---
    EXCLUDE_DIRS = {
        "__pycache__", ".git", "log", "record", "report", "download",
        ".pytest_cache", ".mypy_cache", ".tox", "dist", "build",
        ".vscode", ".idea",
    }
    EXCLUDE_EXTENSIONS = {
        ".pyc", ".pyo", ".log", ".tmp", ".bak", ".swp", ".md",
    }

    def _should_include(self, file_path: Path, base: Path) -> bool:
        """判断文件是否应包含在包中。"""
        # 检查路径中是否有排除目录
        rel_parts = file_path.relative_to(base).parts
        for part in rel_parts:
            if part in self.EXCLUDE_DIRS:
                return False

        # 检查排除后缀
        if file_path.suffix in self.EXCLUDE_EXTENSIONS:
            return False

        return True

    def package(self) -> Path:
        """打包文件。

        返回:
            目标目录路径
        """
        LOG.log("info", f"=== 开始打包文件到 {self.dest_dir} ===")

        # 创建目标目录
        self.dest_dir.mkdir(parents=True, exist_ok=True)

        # 复制源文件
        src_dir = BASE_DIR
        copied_count = 0

        for item in src_dir.rglob("*"):
            if not item.is_file():
                continue

            if not self._should_include(item, src_dir):
                continue

            # 计算目标路径
            rel_path = item.relative_to(src_dir)
            dest_path = self.dest_dir / rel_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                shutil.copy2(item, dest_path)
                copied_count += 1
                LOG.log("info", f"  复制: {rel_path}")
            except Exception as e:
                LOG.log("warning", f"  复制失败: {rel_path} - {e}")

        LOG.log("done", f"打包完成: {copied_count} 个文件 → {self.dest_dir}")
        print(f"\n  打包完成:")
        print(f"  目标: {self.dest_dir}")
        print(f"  文件数: {copied_count}")

        return self.dest_dir
