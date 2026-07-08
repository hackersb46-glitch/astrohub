"""
M3 Stream Service v1.0 - video stream pull/transcode/distribute/preview.

Wave 4: RTSP streaming/image capture/recording/interval capture.

Author: 雅痞张@南方天文
"""

__version__ = "1.0"
__author__ = "雅痞张@南方天文"

# Wave 4 exports
from src.stream.core.stream import (
    RtspUrlParser,
    StreamConnectionState,
    StreamSession,
    StreamPool,
    RtspConnector,
    ScreenshotCapture,
    VideoRecorder,
    IntervalCapture,
)


# Export Manager
from src.core.stream_manager import StreamManager
__all__ = ['StreamManager']