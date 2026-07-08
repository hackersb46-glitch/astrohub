"""AstroHub v8.10 - 星点对齐叠加引擎
帧采集 → 星点检测 → 三角匹配对齐 → Sigma Clip 叠加 → 预览推送
"""
import time
import base64
import io
import numpy as np
import cv2

from src.vision.star_detector import extract_stars, match_stars


def _to_jpg_base64(bgr: np.ndarray, quality: int = 85) -> str:
    """BGR numpy array → JPEG base64 string."""
    _, buf = cv2.imencode('.jpg', bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return base64.b64encode(buf).decode('utf-8')


def _sigma_clip_mean(stack: np.ndarray, sigma: float = 2.0) -> np.ndarray:
    """Sigma Clip 均值叠加。N×H×W×C → H×W×C"""
    mean = np.mean(stack, axis=0)
    std = np.std(stack, axis=0)
    lower = mean - sigma * std
    upper = mean + sigma * std
    valid = (stack >= lower) & (stack <= upper)
    result = np.sum(stack * valid, axis=0) / np.maximum(np.sum(valid, axis=0), 1)
    return result


def _auto_stretch(bgr: np.ndarray, black_clip: float = 0.01, white_clip: float = 0.995) -> np.ndarray:
    """自动直方图拉伸。"""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
    cdf = hist.cumsum()
    cdf = cdf / cdf[-1]
    black = int(np.searchsorted(cdf, black_clip))
    white = max(black + 1, int(np.searchsorted(cdf, white_clip)))
    scale = 255.0 / max(white - black, 1)
    result = np.clip((bgr.astype(np.float32) - black) * scale, 0, 255).astype(np.uint8)
    return result


class StackEngine:
    """实时星点对齐叠加引擎。

    用法:
        engine = StackEngine(client)
        engine.start(total_frames=300)
        for i in range(300):
            bgr = capture_frame()
            result = engine.add_frame(bgr)
        final = engine.finish()
    """

    def __init__(self, client):
        self.client = client
        self._ref_frame: np.ndarray | None = None
        self._ref_stars: list[dict] = []
        self._stack_buffer: list[np.ndarray] = []
        self._total_frames: int = 0
        self._running: bool = False
        self._cancelled: bool = False

    def start(self, total_frames: int) -> dict:
        self._total_frames = total_frames
        self._stack_buffer = []
        self._running = True
        self._cancelled = False
        self._ref_frame = None
        self._ref_stars = []
        return {"total_frames": total_frames, "state": "acquiring_reference"}

    def add_frame(self, bgr: np.ndarray) -> dict | None:
        """添加一帧, 返回 {"index", "aligned", "preview_jpg_base64"}"""
        if not self._running or self._cancelled:
            return None

        idx = len(self._stack_buffer)

        if self._ref_frame is None:
            self._ref_frame = bgr.astype(np.float32)
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            self._ref_stars = extract_stars(gray.astype(np.float64))
            self._stack_buffer.append(self._ref_frame)
            return {"index": idx, "aligned": True, "preview_jpg_base64": _to_jpg_base64(bgr)}

        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        src_stars = extract_stars(gray.astype(np.float64))
        result = match_stars(self._ref_stars, src_stars)

        if result is not None:
            M, _, _, _ = result
            h, w = self._ref_frame.shape[:2]
            aligned = cv2.warpAffine(bgr.astype(np.float32), M, (w, h))
            self._stack_buffer.append(aligned)
            aligned_flag = True
        else:
            self._stack_buffer.append(bgr.astype(np.float32))
            aligned_flag = False

        preview = None
        if len(self._stack_buffer) % 5 == 0:
            preview = self._build_preview()

        return {"index": idx, "aligned": aligned_flag, "preview_jpg_base64": preview}

    def _build_preview(self) -> str:
        stack = np.stack(self._stack_buffer, axis=0)
        result = np.mean(stack, axis=0)
        result = np.clip(result, 0, 255).astype(np.uint8)
        result = _auto_stretch(result)
        return _to_jpg_base64(result)

    def finish(self) -> dict:
        self._running = False
        if not self._stack_buffer:
            return {"success": False, "message": "无帧数据"}

        n = len(self._stack_buffer)
        stack = np.stack(self._stack_buffer, axis=0)
        result = _sigma_clip_mean(stack, sigma=2.0)
        result = np.clip(result, 0, 255).astype(np.uint8)
        stretched = _auto_stretch(result)

        return {
            "success": True,
            "total_frames": n,
            "snr_improvement": round(np.sqrt(n), 1),
            "result_jpg_base64": _to_jpg_base64(stretched),
        }

    def cancel(self):
        self._cancelled = True
        self._running = False
