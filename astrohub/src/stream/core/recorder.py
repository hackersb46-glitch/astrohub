"""
M3 Stream Service v1.0 - 录制模块 (P5)

本地录制、录制控制、录像检索。

P5.1: 本地录制
P5.2: 录制控制
P5.3: 录像检索

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from datetime import datetime

from src.stream.constants import (
    DEFAULT_RECORD_FORMAT,
    MAX_RECORD_FILES,
    RECORD_DIR,
    RECORD_SEGMENT_DURATION,
    RECORD_SEGMENT_SIZE,
    RecordFormat,
    RecordStatus,
)
from src.stream.core.logger import LOG


# ------------------------------------------------------------------ #
#  P5.1 + P5.2 + P5.3 - 录像管理器
# ------------------------------------------------------------------ #

class RecordEntry:
    """录像记录。"""

    def __init__(self, stream_id: str, filepath: str, format: str,
                 start_time: str, size: int = 0, duration: float = 0) -> None:
        self.stream_id = stream_id
        self.filepath = filepath
        self.format = format
        self.start_time = start_time
        self.end_time = ""
        self.size = size
        self.duration = duration
        self.created_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "stream_id": self.stream_id,
            "filepath": self.filepath,
            "format": self.format,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "size_bytes": self.size,
            "duration_seconds": self.duration,
            "created_at": self.created_at,
        }


class RecordingManager:
    """本地录制管理器。

    P5.1: 将视频流录制到本地文件(MP4/FLV)，支持按时间或大小分段。
    P5.2: 启动/停止/暂停录制API。
    P5.3: 按时间/设备检索已录制文件。
    """

    def __init__(self, output_dir: str | None = None,
                 format: str = DEFAULT_RECORD_FORMAT.value) -> None:
        from src.stream.constants import DOWNLOAD_DIR
        self._output_dir = output_dir or str(DOWNLOAD_DIR)
        os.makedirs(self._output_dir, exist_ok=True)
        self._format = RecordFormat(format)
        self._index_file = os.path.join(self._output_dir, "record_index.json")
        self._index: list[dict] = []
        self._active_records: dict[str, dict] = {}
        self._index_lock = threading.Lock()
        self._load_index()

    def _load_index(self) -> None:
        """加载录像索引。"""
        if os.path.exists(self._index_file):
            try:
                with open(self._index_file, "r", encoding="utf-8") as f:
                    self._index = json.load(f)
                LOG.info(f"录像索引已加载: {len(self._index)} 条记录")
            except Exception as e:
                LOG.error(f"录像索引加载失败: {e}")
                self._index = []

    def _save_index(self) -> None:
        """保存录像索引到JSON文件(原子写入)。"""
        import tempfile as _tempfile

        dir_path = os.path.dirname(self._index_file)
        fd, tmp_path = _tempfile.mkstemp(dir=dir_path, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._index, f, indent=2, ensure_ascii=False)
                f.write("\n")
            os.replace(tmp_path, self._index_file)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    # ------------------------------------------------------------------ #
    #  P5.1 - 本地录制
    # ------------------------------------------------------------------ #

    def start_recording(self, stream_id: str, stream_url: str,
                        format: str | None = None,
                        segment_duration: int = RECORD_SEGMENT_DURATION,
                        segment_size: int = RECORD_SEGMENT_SIZE) -> dict:
        """启动录像。

        Args:
            stream_id: 流唯一标识
            stream_url: 流地址
            format: 录制格式 (mp4/flv, 默认MP4)
            segment_duration: 按时间分段间隔(秒)
            segment_size: 按大小分段阈值(字节)

        Returns:
            启动结果: {"success": True/False, "record_id": "...", "filepath": "..."}
        """
        if stream_id in self._active_records:
            return {"success": False, "error": f"录制已在进行: stream_id={stream_id}"}

        fmt = format or self._format.value
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{stream_id}_{timestamp}.{fmt}"
        filepath = os.path.join(self._output_dir, filename)

        cmd = [
            "ffmpeg",
            "-fflags", "nobuffer",
            "-flags", "low_delay",
            "-i", stream_url,
            "-c:v", "copy",
            "-c:a", "copy",
            "-f", fmt if fmt == "flv" else "mp4",
            "-movflags", "+faststart",
            "-y",
            filepath,
        ]

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
            )

            record_entry = RecordEntry(
                stream_id=stream_id,
                filepath=filepath,
                format=fmt,
                start_time=datetime.now().isoformat(),
            )

            self._active_records[stream_id] = {
                "process": proc,
                "entry": record_entry,
                "format": fmt,
                "status": RecordStatus.RECORDING.value,
                "segment_duration": segment_duration,
                "segment_size": segment_size,
            }

            LOG.done(f"录制已启动: stream_id={stream_id}, file={filename}")
            return {
                "success": True,
                "record_id": stream_id,
                "filepath": filepath,
                "status": RecordStatus.RECORDING.value,
            }

        except FileNotFoundError:
            return {"success": False, "error": "ffmpeg未安装或不在PATH中"}
        except Exception as e:
            return {"success": False, "error": f"录制启动异常: {e}"}

    # ------------------------------------------------------------------ #
    #  P5.2 - 录制控制
    # ------------------------------------------------------------------ #

    def stop_recording(self, stream_id: str) -> dict:
        """停止指定流的录制。

        Args:
            stream_id: 流唯一标识

        Returns:
            停止结果
        """
        record_info = self._active_records.pop(stream_id, None)
        if not record_info:
            return {"success": False, "error": f"未找到录制任务: stream_id={stream_id}"}

        proc = record_info.get("process")
        entry = record_info.get("entry")

        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=10)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

        # 更新文件信息
        if entry and os.path.exists(entry.filepath):
            entry.end_time = datetime.now().isoformat()
            entry.size = os.path.getsize(entry.filepath)
            # 估算持续时间
            start_dt = datetime.fromisoformat(entry.start_time)
            end_dt = datetime.fromisoformat(entry.end_time)
            entry.duration = (end_dt - start_dt).total_seconds()

            # 写入索引
            with self._index_lock:
                self._index.append(entry.to_dict())
                # 限制最大文件数
                if len(self._index) > MAX_RECORD_FILES:
                    self._index = self._index[-MAX_RECORD_FILES:]
                self._save_index()

            LOG.info(f"录制已停止: stream_id={stream_id}, "
                     f"size={entry.size}B, duration={entry.duration:.0f}s")
        else:
            LOG.warning(f"录制文件不存在: stream_id={stream_id}")

        return {
            "success": True,
            "stream_id": stream_id,
            "status": "stopped",
            "filepath": entry.filepath if entry else "",
            "size": entry.size if entry else 0,
            "duration": entry.duration if entry else 0,
        }

    def pause_recording(self, stream_id: str) -> dict:
        """暂停录制(流数据不写入文件)。

        Args:
            stream_id: 流唯一标识

        Returns:
            暂停结果
        """
        record_info = self._active_records.get(stream_id)
        if not record_info:
            return {"success": False, "error": f"未找到录制任务: stream_id={stream_id}"}

        proc = record_info.get("process")
        if proc:
            try:
                # 发送SIGSTOP暂停进程
                import signal
                os.kill(proc.pid, signal.SIGSTOP)
                record_info["status"] = RecordStatus.PAUSED.value
                LOG.info(f"录制已暂停: stream_id={stream_id}")
                return {"success": True, "stream_id": stream_id, "status": RecordStatus.PAUSED.value}
            except Exception as e:
                return {"success": False, "error": f"暂停异常: {e}"}

        return {"success": False, "error": "无活跃进程"}

    def resume_recording(self, stream_id: str) -> dict:
        """恢复录制的。

        Args:
            stream_id: 流唯一标识

        Returns:
            恢复结果
        """
        record_info = self._active_records.get(stream_id)
        if not record_info:
            return {"success": False, "error": f"未找到录制任务: stream_id={stream_id}"}

        proc = record_info.get("process")
        if proc:
            try:
                import signal
                os.kill(proc.pid, signal.SIGCONT)
                record_info["status"] = RecordStatus.RECORDING.value
                LOG.info(f"录制已恢复: stream_id={stream_id}")
                return {"success": True, "stream_id": stream_id, "status": RecordStatus.RECORDING.value}
            except Exception as e:
                return {"success": False, "error": f"恢复异常: {e}"}

        return {"success": False, "error": "无活跃进程"}

    # ------------------------------------------------------------------ #
    #  P5.3 - 录像检索
    # ------------------------------------------------------------------ #

    def search_records(self, stream_id: str | None = None,
                       start_time: str | None = None,
                       end_time: str | None = None) -> list[dict]:
        """按时间/设备检索已录制文件。

        Args:
            stream_id: 设备(流)标识过滤
            start_time: 起始时间 (ISO格式)
            end_time: 结束时间 (ISO格式)

        Returns:
            匹配的文件列表，包含时长/大小/设备信息
        """
        with self._index_lock:
            results = list(self._index)

        # 按设备(stream_id)过滤
        if stream_id:
            results = [r for r in results if r.get("stream_id") == stream_id]

        # 按时间范围过滤
        if start_time:
            results = [r for r in results if r.get("start_time", "") >= start_time]
        if end_time:
            results = [r for r in results if r.get("start_time", "") <= end_time]

        # 附加文件存在性检查
        for r in results:
            filepath = r.get("filepath", "")
            r["file_exists"] = os.path.exists(filepath) if filepath else False

        LOG.info(f"录像检索: stream_id={stream_id}, start={start_time}, end={end_time}, 匹配{len(results)}条")
        return results

    def get_record_info(self, filepath: str) -> dict | None:
        """获取单个录像文件详情。"""
        with self._index_lock:
            for record in self._index:
                if record.get("filepath") == filepath:
                    return record
        return None

    def delete_record(self, filepath: str) -> dict:
        """删除录像文件及索引记录。

        Args:
            filepath: 录像文件路径

        Returns:
            删除结果
        """
        with self._index_lock:
            self._index = [r for r in self._index if r.get("filepath") != filepath]
            self._save_index()

        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                LOG.info(f"录像已删除: filepath={filepath}")
                return {"success": True, "deleted": filepath}
        except Exception as e:
            return {"success": False, "error": f"删除异常: {e}"}

        return {"success": False, "error": f"文件不存在: {filepath}"}

    def list_records(self) -> list[dict]:
        """获取所有已录制文件。

        Returns:
            录像文件列表
        """
        with self._index_lock:
            return list(self._index)
