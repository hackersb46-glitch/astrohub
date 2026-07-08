"""
M9 ASCOM v1.0 - Platform Detection

Detects whether ASCOM Platform is installed on Windows (registry check)
or if Alpaca server is available (cross-platform fallback).

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import logging
import platform
import socket
from typing import Any

from src.ascom.constants import (
    ASCOM_PLATFORM_REG_KEY,
    ASCOM_PLATFORM_MIN_VERSION,
)

logger = logging.getLogger("ascom.platform")


def detect_ascom_platform() -> dict[str, Any]:
    """Detect the available ASCOM platform.

    Checks in order:
    1. Windows Registry for ASCOM Platform installation
    2. Alpaca server at localhost:5555
    3. Linux alternative (no Windows COM available)

    Returns:
        {
            "detected": bool,
            "platform": "windows_com" | "alpaca" | "linux" | "none",
            "version": str,
            "details": str,
        }
    """
    system = platform.system()

    # On Windows, check registry first
    if system == "Windows":
        result = _check_windows_registry()
        if result["detected"]:
            return result

        # Windows without COM -> fallback to Alpaca
        return _check_alpaca_server()

    # On Linux/macOS, only Alpaca is available
    return _check_alpaca_server()


def _check_windows_registry() -> dict[str, Any]:
    """Check Windows registry for ASCOM Platform installation."""
    try:
        import winreg  # type: ignore

        # Try to open ASCOM registry key
        key_path = ASCOM_PLATFORM_REG_KEY
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_READ)
            version, _ = winreg.QueryValueEx(key, "Version")  # type: ignore
            winreg.CloseKey(key)

            # Validate minimum version
            if _version_gte(version, ASCOM_PLATFORM_MIN_VERSION):
                logger.info("ASCOM Platform %s detected (registry)", version)
                return {
                    "detected": True,
                    "platform": "windows_com",
                    "version": version,
                    "details": f"ASCOM Platform {version} found in Windows registry",
                }
            else:
                logger.warning(
                    "ASCOM Platform %s found but version too old (min %s)",
                    version,
                    ASCOM_PLATFORM_MIN_VERSION,
                )
                return {
                    "detected": False,
                    "platform": "none",
                    "version": version,
                    "details": f"ASCOM Platform {version} is too old (min {ASCOM_PLATFORM_MIN_VERSION})",
                }

        except FileNotFoundError:
            logger.debug("ASCOM registry key not found at %s", key_path)
            return {
                "detected": False,
                "platform": "none",
                "version": "",
                "details": "ASCOM Platform not found in Windows registry",
            }

    except ImportError:
        logger.warning("winreg not available (not on Windows?)")
        return {
            "detected": False,
            "platform": "none",
            "version": "",
            "details": "Windows registry access not available",
        }
    except Exception as e:
        logger.error("Registry check failed: %s", e)
        return {
            "detected": False,
            "platform": "none",
            "version": "",
            "details": f"Registry check failed: {str(e)}",
        }


def _check_alpaca_server(host: str = "localhost", port: int = 5555) -> dict[str, Any]:
    """Check if Alpaca server is available at the given address."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        result = sock.connect_ex((host, port))
        sock.close()

        if result == 0:
            # Try to get device list from Alpaca management API
            try:
                import urllib.request
                url = f"http://{host}:{port}/management/v1/apidevices"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=5) as resp:
                    import json
                    data = json.loads(resp.read())
                    devices = data.get("Value", [])
                    device_names = [d.get("DeviceName", "Unknown") for d in devices]

                    logger.info(
                        "Alpaca server detected at %s:%d with %d device(s): %s",
                        host, port, len(devices), ", ".join(device_names),
                    )
                    return {
                        "detected": True,
                        "platform": "alpaca",
                        "version": "alpaca",
                        "details": f"Alpaca server at {host}:{port}, devices: {device_names}",
                    }
            except Exception as api_err:
                logger.info("Alpaca port open but API check failed: %s", api_err)
                return {
                    "detected": True,
                    "platform": "alpaca",
                    "version": "alpaca",
                    "details": f"Alpaca server at {host}:{port} (port open, API unavailable)",
                }
        else:
            logger.debug("No Alpaca server at %s:%d", host, port)

    except Exception as e:
        logger.debug("Alpaca check failed: %s", e)

    return {
        "detected": False,
        "platform": "none",
        "version": "",
        "details": f"No Alpaca server found at {host}:{port}",
    }


def _version_gte(version: str, min_version: str) -> bool:
    """Check if version string >= minimum version."""
    try:
        v_parts = [int(x) for x in version.split(".")[:3]]
        m_parts = [int(x) for x in min_version.split(".")[:3]]

        # Pad to same length
        while len(v_parts) < 3:
            v_parts.append(0)
        while len(m_parts) < 3:
            m_parts.append(0)

        return v_parts >= m_parts
    except (ValueError, AttributeError):
        return False


def get_available_telescope_drivers() -> list[dict[str, str]]:
    """Get list of available telescope ASCOM drivers on Windows.

    Queries the Windows registry for installed ASCOM Telescope drivers.

    Returns:
        List of { "id": ProgID, "name": DriverName } dicts.
    """
    drivers = []

    if platform.system() != "Windows":
        return drivers

    try:
        import winreg  # type: ignore

        # ASCOM stores Telescope drivers at:
        # HKEY_LOCAL_MACHINE\SOFTWARE\ASCOM\Telescope\
        key_path = r"SOFTWARE\ASCOM\Telescope"
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_READ)

        i = 0
        while True:
            try:
                prog_id = winreg.EnumKey(key, i)
                # Try to get driver name
                try:
                    sub_key = winreg.OpenKey(key, prog_id)
                    name, _ = winreg.QueryValueEx(sub_key, "")  # Default value
                    winreg.CloseKey(sub_key)
                except FileNotFoundError:
                    name = prog_id

                drivers.append({"id": prog_id, "name": name})
                i += 1
            except OSError:
                break

        winreg.CloseKey(key)
        logger.info("Found %d ASCOM Telescope drivers", len(drivers))

    except Exception as e:
        logger.error("Failed to enumerate ASCOM drivers: %s", e)

    return drivers
