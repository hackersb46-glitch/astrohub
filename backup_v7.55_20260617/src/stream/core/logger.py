"""
M3 Stream Service v1.0 - 全局日志模块

提供 Logger 单例，支持5种日志级别(info/warning/error/done/failed)，
毫秒级时间戳，自动目录创建，日志文件按日期+序号轮转。
参考 M2: src/device/core/logger.py
"""

from datetime import datetime
from pathlib import Path

from src.stream.constants import LOG_DIR, ACCEPTED_LOG_LEVELS


class Logger:
    """全局日志器：自动创建目录、生成日志文件、输出到文件与控制台。"""

    def __init__(self, log_dir: Path | None = None, prefix: str = "log") -> None:
        self.log_dir = log_dir or LOG_DIR
        self.prefix = prefix
        self._ensure_directory()
        self.log_file = self._create_log_file()

    # ------------------------------------------------------------------ #
    #  目录创建
    # ------------------------------------------------------------------ #
    def _ensure_directory(self) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    #  日志文件生成 - 按日期+序号轮转
    # ------------------------------------------------------------------ #
    def _create_log_file(self) -> Path:
        today = datetime.now().strftime("%Y%m%d")

        # 查找今天已有的日志文件，确定最大序号
        existing = list(self.log_dir.glob(f"{self.prefix}_{today}-*.md"))
        max_seq = 0
        for f in existing:
            stem = f.stem
            parts = stem.rsplit("-", 1)
            if len(parts) == 2:
                try:
                    seq = int(parts[1])
                    if seq > max_seq:
                        max_seq = seq
                except ValueError:
                    continue

        seq = max_seq + 1
        filename = f"{self.prefix}_{today}-{seq:03d}.md"
        return self.log_dir / filename

    # ------------------------------------------------------------------ #
    #  日志写入
    # ------------------------------------------------------------------ #
    def log(self, level: str, message: str) -> None:
        level_lower = level.lower()
        if level_lower not in ACCEPTED_LOG_LEVELS:
            raise ValueError(
                f"未知日志级别 '{level}'，支持的级别: {', '.join(sorted(ACCEPTED_LOG_LEVELS))}"
            )

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S.%f")[:-3]  # yyyymmdd-hhmmss.mmm
        line = f"[{level_lower}] {timestamp} - {message}"

        # 写文件 (追加模式)
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")

        # 输出到控制台
        print(line)

    # ------------------------------------------------------------------ #
    #  便捷方法
    # ------------------------------------------------------------------ #
    def info(self, message: str) -> None:
        self.log("info", message)

    def warning(self, message: str) -> None:
        self.log("warning", message)

    def error(self, message: str) -> None:
        self.log("error", message)

    def done(self, message: str) -> None:
        self.log("done", message)

    def failed(self, message: str) -> None:
        self.log("failed", message)

    def rotate(self) -> None:
        """强制轮转，创建新日志文件。"""
        self.log_file = self._create_log_file()
        self.info(f"日志轮转: {self.log_file.name}")

    @property
    def current_log_file(self) -> Path:
        return self.log_file

    def get_log_files(self) -> list[Path]:
        """获取所有日志文件列表，按时间排序。"""
        files = list(self.log_dir.glob(f"{self.prefix}_*.md"))
        return sorted(files, key=lambda f: f.name)


# === 模块级单例 ===
LOG = Logger(prefix="log")
