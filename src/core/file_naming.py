import threading
import os
from datetime import datetime
from typing import Optional

class DayCounter:
    """Thread-safe day-resetting counter for file naming.

    Naming format: {identifier}-YYYYMMDD-NNNN.{extension}
    - identifier: device IP (dots→underscores) or target name
    - NNNN: 4-digit sequence, resets daily
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # {date_str: {identifier: counter}}
        self._counters: dict[str, dict[str, int]] = {}

    def _get_date_key(self) -> str:
        return datetime.now().strftime("%Y%m%d")

    def next(self, identifier: str, extension: str = ".jpg") -> str:
        """Get next filename for given identifier.

        Args:
            identifier: device IP or target name
            extension: file extension (default '.jpg')

        Returns:
            Filename like "4k_32X_DC_20260507_120530_0001.jpg"
        """
        if not extension.startswith("."):
            extension = "." + extension

        # Normalize: dots/slashes/spaces -> underscores
        normalized = identifier.replace(".", "_").replace("/", "_").replace("\\", "_").replace(" ", "_")

        date_key = self._get_date_key()
        time_key = datetime.now().strftime("%H%M%S")

        with self._lock:
            if date_key not in self._counters:
                self._counters = {date_key: {}}

            day_counters = self._counters[date_key]
            current = day_counters.get(normalized, 0) + 1
            day_counters[normalized] = current

        return f"{normalized}_{date_key}_{time_key}_{current:04d}{extension}"


# Module-level singleton
_counter = DayCounter()

def generate_filename(
    target_name: Optional[str] = None,
    device_ip: Optional[str] = None,
    extension: str = ".jpg",
) -> str:
    """Generate a filename using the naming scheme.

    Priority: target_name > device_ip
    If neither provided, uses "unknown".

    Args:
        target_name: human-readable name (e.g., device name, "test_run")
        device_ip: device IP address (dots will be replaced with underscores)
        extension: file extension (default '.jpg' or '.mp4')

    Returns:
        Filename string.
    """
    identifier = target_name or device_ip or "unknown"
    return _counter.next(identifier, extension)