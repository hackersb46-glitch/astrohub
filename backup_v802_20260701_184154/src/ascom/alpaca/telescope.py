"""
M9 ASCOM v1.0 - Alpaca Telescope Driver

Implements ASCOM Alpaca protocol for telescope control.
Compatible with NINA and other ASCOM Alpaca clients.

Alpaca Spec: https://ascom-standards.org/Developer/AlpacaStandard.htm
Responses use standard Alpaca format: { "Value": ..., "ErrorMessage": "", "CallerStacktrace": "" }

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger("ascom.alpaca.telescope")


# ================================================================== #
#  Alpaca Standard Response Helpers
# ================================================================== #

def alpaca_response(value: Any = None, error: str = "") -> dict[str, Any]:
    """Construct standard ASCOM Alpaca response."""
    return {
        "Value": value,
        "ErrorMessage": error,
        "CallerStacktrace": "",
    }


# ================================================================== #
#  Telescope Alpaca Driver
# ================================================================== #

class TelescopeAlpacaDriver:
    """ASCOM Alpaca Telescope driver wrapper.

    Wraps the underlying TelescopeDriver to expose Alpaca-compatible state
    and operations. Maintains its own connection state that mirrors the
    COM driver.
    """

    # Alpaca DeviceType ID for telescopes
    DEVICE_TYPE_ID = 1
    DEVICE_NUMBER = 0

    def __init__(self, telescope_driver: Any = None) -> None:
        """Initialize with optional underlying telescope driver.

        Args:
            telescope_driver: The underlying TelescopeDriver instance
                              (from ascom.core.telescope_driver).
                              If None, operates in standalone Alpaca mode.
        """
        self._telescope_driver = telescope_driver
        self._connected = False
        self._driver_id = ""
        self._ra = 0.0
        self._dec = 0.0
        self._tracking = False
        self._slewing = False
        self._target_ra = 0.0
        self._target_dec = 0.0
        self._tracking_mode = 1  # 1=sidereal (ASCOM standard)
        self._at_park = False
        self._lock = threading.Lock()

        # Tracking monitor
        self._tracking_monitor_thread: threading.Thread | None = None
        self._tracking_monitor_running = False
        self._coord_history: list[tuple[float, float, float]] = []  # (ra, dec, timestamp)
        self._max_drift_deg = 0.0  # arcseconds of drift

    # ================================================================== #
    #  Alpaca: Connected Property
    # ================================================================== #

    @property
    def connected(self) -> bool:
        """Alpaca: Is telescope connected?"""
        return self._connected

    @connected.setter
    def connected(self, value: bool) -> None:
        """Alpaca: Connect or disconnect telescope."""
        with self._lock:
            if value and not self._connected:
                self._do_connect()
            elif not value and self._connected:
                self._do_disconnect()

    def _do_connect(self) -> None:
        """Perform actual connection."""
        if self._telescope_driver:
            result = self._telescope_driver.connect(self._driver_id)
            if result.get("success"):
                self._connected = True
                data = result.get("data", {})
                self._ra = data.get("ra", 0.0)
                self._dec = data.get("dec", 0.0)
                self._tracking = data.get("tracking_mode", 1) == 1
                logger.info("Alpaca Telescope connected via underlying driver")
            else:
                logger.error("Alpaca Telescope connect failed: %s", result.get("message"))
        else:
            # Standalone mode: simulate connection
            self._connected = True
            logger.info("Alpaca Telescope connected (standalone mode)")

        # Start tracking monitor when connected
        self._start_tracking_monitor()

    def _do_disconnect(self) -> None:
        """Perform actual disconnection."""
        self._stop_tracking_monitor()

        if self._telescope_driver:
            self._telescope_driver.disconnect()

        self._connected = False
        self._slewing = False
        self._tracking = False
        logger.info("Alpaca Telescope disconnected")

    # ================================================================== #
    #  Alpaca: Action (generic method call)
    # ================================================================== #

    def action(self, action_name: str, action_params: str = "") -> dict:
        """Alpaca: Execute a named action."""
        logger.debug("Alpaca Action: %s, params=%s", action_name, action_params)
        return alpaca_response(value=f"Action '{action_name}' executed")

    # ================================================================== #
    #  Alpaca: CommandBlind / CommandString (direct serial commands)
    # ================================================================== #

    def command_blind(self, command: str) -> None:
        """Alpaca: Send command, no response expected."""
        logger.debug("Alpaca CommandBlind: %s", command)

    def command_string(self, command: str, raw: bool = False) -> str:
        """Alpaca: Send command, return response string."""
        logger.debug("Alpaca CommandString: %s", command)
        return ""

    # ================================================================== #
    #  Alpaca: SetupDialog
    # ================================================================== #

    def setup_dialog(self) -> None:
        """Alpaca: Show device setup dialog (stub - no GUI in headless mode)."""
        logger.info("Alpaca SetupDialog requested (headless mode - no dialog)")

    # ================================================================== #
    #  Alpaca: Description / DriverInfo / Name
    # ================================================================== #

    @property
    def description(self) -> str:
        """Alpaca: Device description."""
        return "AstroHub Alpaca Telescope Driver"

    @property
    def driver_info(self) -> str:
        """Alpaca: Driver information."""
        return "AstroHub M9 ASCOM v1.0 - Alpaca Telescope"

    @property
    def name(self) -> str:
        """Alpaca: Device name."""
        return "AstroHub Telescope"

    @property
    def driver_version(self) -> int:
        """Alpaca: Driver version number."""
        return 1

    @property
    def interface_version(self) -> int:
        """Alpaca: ASCOM interface version (must be >= 3 for telescope)."""
        return 3

    # ================================================================== #
    #  Alpaca: Telescope Properties
    # ================================================================== #

    @property
    def alignment_mode(self) -> int:
        """Alpaca: Alignment mode (0=unknown, 1=equatorial, 2=alt-az)."""
        return 1  # Equatorial

    @property
    def does_secondary_guiding(self) -> bool:
        """Alpaca: Does this telescope support secondary guiding?"""
        return False

    @property
    def is_pulse_guiding(self) -> bool:
        """Alpaca: Is pulse guiding active?"""
        return False

    @property
    def site_elevation(self) -> float:
        """Alpaca: Site elevation in meters."""
        return 0.0

    @site_elevation.setter
    def site_elevation(self, value: float) -> None:
        logger.debug("Alpaca site_elevation set to %.1f", value)

    @property
    def site_latitude(self) -> float:
        """Alpaca: Site latitude in degrees (+N, -S)."""
        return 0.0

    @site_latitude.setter
    def site_latitude(self, value: float) -> None:
        logger.debug("Alpaca site_latitude set to %.4f", value)

    @property
    def site_longitude(self) -> float:
        """Alpaca: Site longitude in degrees (+E, -W)."""
        return 0.0

    @site_longitude.setter
    def site_longitude(self, value: float) -> None:
        logger.debug("Alpaca site_longitude set to %.4f", value)

    @property
    def tracking_rate(self) -> float:
        """Alpaca: Current tracking rate multiplier (1.0 = sidereal)."""
        return 1.0

    @property
    def tracking_rates_available(self) -> list[float]:
        """Alpaca: Available tracking rates."""
        return [0.99727, 1.0, 1.00274, 1.36889]  # Sidereal, Lunar, Solar, King

    # ================================================================== #
    #  Alpaca: RightAscension
    # ================================================================== #

    @property
    def right_ascension(self) -> float:
        """Alpaca: Current RA in hours (0-24)."""
        with self._lock:
            if self._telescope_driver and self._connected:
                try:
                    result = self._telescope_driver.get_position()
                    if result.get("success"):
                        self._ra = result["data"].get("ra", self._ra)
                except Exception:
                    pass
            return self._ra

    # ================================================================== #
    #  Alpaca: Declination
    # ================================================================== #

    @property
    def declination(self) -> float:
        """Alpaca: Current Dec in degrees (-90 to +90)."""
        with self._lock:
            if self._telescope_driver and self._connected:
                try:
                    result = self._telescope_driver.get_position()
                    if result.get("success"):
                        self._dec = result["data"].get("dec", self._dec)
                except Exception:
                    pass
            return self._dec

    # ================================================================== #
    #  Alpaca: RightAscensionRate / DeclinationRate
    # ================================================================== #

    @property
    def right_ascension_rate(self) -> float:
        """Alpaca: RA tracking rate in arcseconds/s."""
        return 15.04 * self.tracking_rate  # Sidereal rate

    @property
    def declination_rate(self) -> float:
        """Alpaca: Dec tracking rate in arcseconds/s."""
        return 0.0

    # ================================================================== #
    #  Alpaca: SlewToCoordinates (Alt-Az)
    # ================================================================== #

    def slew_to_coordinates(self, ra: float, dec: float) -> dict:
        """Alpaca: Slew to RA/Dec coordinates."""
        with self._lock:
            if not self._connected:
                return alpaca_response(error="Telescope not connected")

            try:
                if self._telescope_driver:
                    result = self._telescope_driver.slew_to_coordinates(ra, dec)
                    if not result.get("success"):
                        return alpaca_response(error=result.get("message", "Slew failed"))

                self._target_ra = ra
                self._target_dec = dec
                self._slewing = True
                logger.info("Alpaca SlewToCoordinates: RA=%.4f, Dec=%.4f", ra, dec)
                return alpaca_response(value=None)
            except Exception as e:
                return alpaca_response(error=f"Slew failed: {str(e)}")

    # ================================================================== #
    #  Alpaca: SlewToAltAz (not implemented for equatorial)
    # ================================================================== #

    def slew_to_alt_az(self, altitude: float, azimuth: float) -> dict:
        """Alpaca: Slew to Alt/Az (stub - equatorial mount uses RA/Dec)."""
        return alpaca_response(error="SlewToAltAz not supported on equatorial mount")

    # ================================================================== #
    #  Alpaca: SlewToTarget / SlewToTargetAsync
    # ================================================================== #

    def slew_to_target(self) -> dict:
        """Alpaca: Slew to previously set target coordinates."""
        return self.slew_to_coordinates(self._target_ra, self._target_dec)

    # ================================================================== #
    #  Alpaca: AbortSlew
    # ================================================================== #

    def abort_slew(self) -> dict:
        """Alpaca: Abort current slew operation."""
        with self._lock:
            if not self._connected:
                return alpaca_response(error="Telescope not connected")

            try:
                if self._telescope_driver:
                    self._telescope_driver.abort_slew()

                self._slewing = False
                logger.info("Alpaca AbortSlew")
                return alpaca_response(value=None)
            except Exception as e:
                return alpaca_response(error=f"Abort failed: {str(e)}")

    # ================================================================== #
    #  Alpaca: AtPark
    # ================================================================== #

    @property
    def at_park(self) -> bool:
        """Alpaca: Is telescope parked?"""
        return self._at_park

    def park(self) -> dict:
        """Alpaca: Park the telescope."""
        with self._lock:
            if not self._connected:
                return alpaca_response(error="Telescope not connected")

            try:
                if self._telescope_driver:
                    result = self._telescope_driver.park()
                    if not result.get("success"):
                        return alpaca_response(error=result.get("message", "Park failed"))

                self._at_park = True
                self._slewing = False
                logger.info("Alpaca Park")
                return alpaca_response(value=None)
            except Exception as e:
                return alpaca_response(error=f"Park failed: {str(e)}")

    def unpark(self) -> dict:
        """Alpaca: Unpark the telescope."""
        with self._lock:
            if not self._connected:
                return alpaca_response(error="Telescope not connected")

            try:
                if self._telescope_driver:
                    result = self._telescope_driver.unpark()
                    if not result.get("success"):
                        return alpaca_response(error=result.get("message", "Unpark failed"))

                self._at_park = False
                logger.info("Alpaca Unpark")
                return alpaca_response(value=None)
            except Exception as e:
                return alpaca_response(error=f"Unpark failed: {str(e)}")

    # ================================================================== #
    #  Alpaca: Tracking
    # ================================================================== #

    @property
    def tracking(self) -> bool:
        """Alpaca: Is tracking active?"""
        return self._tracking

    @tracking.setter
    def tracking(self, value: bool) -> None:
        """Alpaca: Enable/disable tracking."""
        with self._lock:
            self._tracking = value
            logger.info("Alpaca Tracking set to %s", value)

            if self._telescope_driver:
                from src.ascom.constants import TrackingMode
                mode = TrackingMode.SIDEREAL if value else TrackingMode.OFF
                self._telescope_driver.set_tracking_mode(mode)

    # ================================================================== #
    #  Alpaca: IsSlew
    # ================================================================== #

    @property
    def is_slew(self) -> bool:
        """Alpaca: Is telescope currently slewing?"""
        with self._lock:
            if self._telescope_driver and self._connected:
                try:
                    result = self._telescope_driver.get_position()
                    if result.get("success"):
                        self._slewing = result["data"].get("is_slewing", self._slewing)
                except Exception:
                    pass
            return self._slewing

    # ================================================================== #
    #  Alpaca: TargetRightAscension / TargetDeclination
    # ================================================================== #

    @property
    def target_right_ascension(self) -> float:
        """Alpaca: Target RA in hours."""
        return self._target_ra

    @target_right_ascension.setter
    def target_right_ascension(self, value: float) -> None:
        """Alpaca: Set target RA."""
        with self._lock:
            self._target_ra = value

    @property
    def target_declination(self) -> float:
        """Alpaca: Target Dec in degrees."""
        return self._target_dec

    @target_declination.setter
    def target_declination(self, value: float) -> None:
        """Alpaca: Set target Dec."""
        with self._lock:
            self._target_dec = value

    # ================================================================== #
    #  Alpaca: Sidereal Time / UTC Offset
    # ================================================================== #

    @property
    def sidereal_time(self) -> float:
        """Alpaca: Local apparent sidereal time in hours."""
        # Simplified: Use RA + hour angle approximation
        # In production, would calculate from UTC date + longitude
        import datetime
        utc_now = datetime.datetime.now(datetime.timezone.utc)
        # Julian date calculation for sidereal time
        jd = (utc_now - datetime.datetime(2000, 1, 1, 12, tzinfo=datetime.timezone.utc)).total_seconds() / 86400.0 + 2451545.0
        gmst = 18.697374558 + 24.06570982441908 * (jd - 2451545.0)
        gmst = gmst % 24.0
        return gmst

    @property
    def utc_offset(self) -> float:
        """Alpaca: UTC offset in hours."""
        import datetime
        now = datetime.datetime.now()
        return now.astimezone().utcoffset().total_seconds() / 3600.0

    # ================================================================== #
    #  Alpaca: Can... (capability queries)
    # ================================================================== #

    @property
    def can_set_declination_rate(self) -> bool:
        return False

    @property
    def can_set_park(self) -> bool:
        return True

    @property
    def can_set_right_ascension_rate(self) -> bool:
        return False

    @property
    def can_set_tracking(self) -> bool:
        return True

    @property
    def can_slew(self) -> bool:
        return True

    @property
    def can_slew_alt_az(self) -> bool:
        return False

    @property
    def can_slew_alt_az_async(self) -> bool:
        return False

    @property
    def can_sync(self) -> bool:
        return False

    # ================================================================== #
    #  Sidereal Tracking Monitor
    # ================================================================== #

    def _start_tracking_monitor(self) -> None:
        """Start background tracking monitor thread."""
        if self._tracking_monitor_thread and self._tracking_monitor_thread.is_alive():
            return

        self._tracking_monitor_running = True
        self._coord_history.clear()
        self._max_drift_deg = 0.0

        def _monitor():
            """Monitor tracking: sample RA/Dec periodically, detect drift."""
            while self._tracking_monitor_running:
                if self._connected and self._tracking:
                    try:
                        with self._lock:
                            current_ra = self._ra
                            current_dec = self._dec
                            now = time.time()

                            self._coord_history.append((current_ra, current_dec, now))
                            # Keep last 60 samples (5 min at 5s intervals)
                            if len(self._coord_history) > 60:
                                self._coord_history.pop(0)

                            # Calculate drift from first sample
                            if len(self._coord_history) >= 2:
                                first_ra, first_dec, _ = self._coord_history[0]
                                # Simple drift calculation (degrees)
                                ra_drift = abs(current_ra - first_ra) * 15.0  # RA hours->degrees
                                dec_drift = abs(current_dec - first_dec)
                                total_drift = (ra_drift ** 2 + dec_drift ** 2) ** 0.5
                                self._max_drift_deg = max(self._max_drift_deg, total_drift)

                    except Exception as e:
                        logger.error("Tracking monitor error: %s", e)

                time.sleep(5)  # Sample every 5 seconds

        self._tracking_monitor_thread = threading.Thread(target=_monitor, daemon=True)
        self._tracking_monitor_thread.start()
        logger.info("Alpaca tracking monitor started")

    def _stop_tracking_monitor(self) -> None:
        """Stop tracking monitor thread."""
        self._tracking_monitor_running = False
        if self._tracking_monitor_thread:
            self._tracking_monitor_thread.join(timeout=10)
            self._tracking_monitor_thread = None
        logger.info("Alpaca tracking monitor stopped")

    @property
    def tracking_drift_degrees(self) -> float:
        """Maximum coordinate drift observed (degrees)."""
        return self._max_drift_deg

    # ================================================================== #
    #  Status
    # ================================================================== #

    def get_status(self) -> dict[str, Any]:
        """Get full telescope status for Alpaca clients."""
        return {
            "connected": self._connected,
            "ra": self._ra,
            "dec": self._dec,
            "tracking": self._tracking,
            "slewing": self._slewing,
            "at_park": self._at_park,
            "target_ra": self._target_ra,
            "target_dec": self._target_dec,
            "tracking_mode": self._tracking_mode,
            "tracking_drift_degrees": self._max_drift_deg,
        }
