"""
PTZ_ASTRO v1.1 - CSV 位置记录器
记录 PTZ 运动过程中的位置数据，采样间隔 0.1 秒。
支持多操作类型，每个操作独立生成 CSV 文件。

Author: 雅痞张@南方天文
"""

import csv
import threading
import time
from datetime import datetime
from pathlib import Path

from .logger import LOG
from src.ptz.constants import RECORD_DIR


class CSVRecorder:
    """CSV 位置记录器：按操作类型生成独立 CSV 文件，0.1s 间隔采样。"""

    csv_path: Path | None = None
    _running = False
    _thread: threading.Thread | None = None
    _lock = threading.Lock()
    _callback = None
    _seq = 0

    def __init__(self) -> None:
        self._today = datetime.now().strftime("%Y%m%d")
        self._find_max_seq()

    def _find_max_seq(self) -> None:
        """找到今天已有的最大序号。"""
        existing = list(RECORD_DIR.glob(f"record_*_{self._today}-*.csv"))
        max_seq = 0
        for f in existing:
            stem = f.stem
            # stem = "record_continuousMove_20260418-003"
            parts = stem.rsplit("-", 1)
            if len(parts) == 2:
                try:
                    seq = int(parts[1])
                    if seq > max_seq:
                        max_seq = seq
                except ValueError:
                    continue
        self._seq = max_seq

    def _next_filename(self, operation: str) -> Path:
        """生成下一个 CSV 文件名。"""
        self._seq += 1
        return RECORD_DIR / f"record_{operation}_{self._today}-{self._seq:03d}.csv"

    def start(self, operation: str, callback=None) -> Path:
        """启动录制。

        参数:
            operation: 操作类型名（如 continuousMove, absoluteMove, panLimit）
            callback: 可选的回调函数，返回 {"pan": x, "tilt": y, "zoom": z}
                     如果不提供，需要调用 write_row() 手动写入

        返回:
            CSV 文件路径
        """
        with self._lock:
            if self._running:
                LOG.log("warning", "录制器已在运行，先停止再启动新的")
                self.stop()

            self.csv_path = self._next_filename(operation)
            self._callback = callback
            self._running = True

            # 创建 CSV 文件并写入表头
            with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "pan", "tilt", "zoom"])

            LOG.log("done", f"CSV 录制启动: {self.csv_path}")

            # 如果有 callback，启动后台采样线程
            if callback:
                self._thread = threading.Thread(
                    target=self._record_loop, daemon=True
                )
                self._thread.start()
                LOG.log("info", "后台采样线程已启动 (0.1s 间隔)")

            return self.csv_path

    def _record_loop(self) -> None:
        """后台采样循环。"""
        while self._running:
            try:
                row = self._callback()
                if row:
                    self.write_row(row.get("pan", 0), row.get("tilt", 0), row.get("zoom", 0))
            except Exception as e:
                LOG.log("warning", f"CSV 采样异常: {e}")
            time.sleep(0.1)

    def write_row(self, pan: float, tilt: float, zoom: float) -> None:
        """手动写入一行数据。"""
        if not self._running or not self.csv_path:
            return

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S.%f")[:23]
        with self._lock:
            with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([timestamp, pan, tilt, zoom])

    def stop(self) -> None:
        """停止录制。"""
        with self._lock:
            self._running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
            self._thread = None

        if self.csv_path:
            LOG.log("done", f"CSV 录制停止: {self.csv_path}")
        else:
            LOG.log("info", "CSV 录制停止（无活动文件）")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def current_path(self) -> Path | None:
        return self.csv_path
