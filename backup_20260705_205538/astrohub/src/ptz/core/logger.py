"""
PTZ_ASTRO v1.1 - 全局日志模块
提供 LOG 单例，负责目录创建、日志文件生成、毫秒级日志记录。
"""

from datetime import datetime
from pathlib import Path

from src.ptz.constants import (
    BASE_DIR,
    LOG_DIR,
    RECORD_DIR,
    REPORT_DIR,
    DOWNLOAD_DIR,
    DOWNLOAD_IMAGE_DIR,
    DOWNLOAD_H264_DIR,
    DOWNLOAD_H265_DIR,
)

_ACCEPTED_LEVELS = {"info", "warning", "error", "done", "failed"}


class PTZLogger:
    """PTZ模块全局日志器：自动创建目录、生成日志文件、输出到文件与控制台。"""

    silent = False  # 静默模式：True时只写文件不输出屏幕

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self._ensure_directories()
        self.log_file = self._create_log_file()

    # ------------------------------------------------------------------ #
    #  P0.1 - 目录创建
    # ------------------------------------------------------------------ #
    def _ensure_directories(self) -> None:
        dirs = [
            self.base_dir / "record",
            self.base_dir / "log",
            self.base_dir / "report",
            self.base_dir / "download",
            self.base_dir / "download" / "image",
            self.base_dir / "download" / "H264",
            self.base_dir / "download" / "H265",
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    #  P0.2 - 日志文件生成
    # ------------------------------------------------------------------ #
    def _create_log_file(self) -> Path:
        today = datetime.now().strftime("%Y%m%d")
        log_dir = self.base_dir / "log"

        # 查找今天已有的日志文件，确定最大序号
        existing = list(log_dir.glob(f"log_{today}-*.md"))
        max_seq = 0
        for f in existing:
            stem = f.stem  # e.g. "log_20260418-003"
            seq_str = stem.split("-")[-1]  # e.g. "003"
            try:
                seq = int(seq_str)
                if seq > max_seq:
                    max_seq = seq
            except ValueError:
                continue

        seq = max_seq + 1
        filename = f"log_{today}-{seq:03d}.md"
        return log_dir / filename

    # ------------------------------------------------------------------ #
    #  P0.3 - 日志写入
    # ------------------------------------------------------------------ #
    def log(self, level: str, message: str) -> None:
        level_lower = level.lower()
        if level_lower not in _ACCEPTED_LEVELS:
            raise ValueError(
                f"未知日志级别 '{level}'，接受的级别: {', '.join(sorted(_ACCEPTED_LEVELS))}"
            )

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:23]  # yyyy-mm-dd HH:MM:SS.mmm
        line = f"[{level_lower}] {timestamp} - {message}"

        # 写文件
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")

        # 输出到屏幕（静默模式时跳过）
        if not PTZLogger.silent:
            print(line)


# === 模块级单例 ===
LOG = PTZLogger(BASE_DIR)