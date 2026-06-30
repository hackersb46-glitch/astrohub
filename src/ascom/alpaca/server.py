"""
M9 ASCOM v1.0 - Alpaca Server

Implements the full ASCOM Alpaca REST protocol on port 5555.
NINA and other Alpaca clients discover devices via /management/v1/apidevices.

Alpaca API Endpoints:
  GET  /management/v1/apidevices                    - Discover all devices
  GET  /api/v1/telescope/{deviceNum}/connected      - Query connection
  PUT  /api/v1/telescope/{deviceNum}/connected      - Connect/disconnect
  GET  /api/v1/telescope/{deviceNum}/rightascension - Current RA
  GET  /api/v1/telescope/{deviceNum}/declination    - Current Dec
  PUT  /api/v1/telescope/{deviceNum}/slewtocoordinates - Slew to target
  PUT  /api/v1/telescope/{deviceNum}/abortslew      - Abort slew
  GET  /api/v1/telescope/{deviceNum}/isslew         - Is slewing?
  GET  /api/v1/telescope/{deviceNum}/tracking       - Tracking active?
  PUT  /api/v1/telescope/{deviceNum}/tracking      - Set tracking
  GET  /api/v1/telescope/{deviceNum}/atpark         - Parked?
  PUT  /api/v1/telescope/{deviceNum}/park           - Park
  PUT  /api/v1/telescope/{deviceNum}/unpark        - Unpark
  GET  /api/v1/telescope/{deviceNum}/description    - Device info
  GET  /api/v1/telescope/{deviceNum}/driverinfo     - Driver info
  GET  /api/v1/telescope/{deviceNum}/name           - Name
  GET  /api/v1/telescope/{deviceNum}/driverversion  - Driver version

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import argparse
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Path as PathParam, Query, HTTPException
from fastapi.responses import JSONResponse

# Ensure project root is on sys.path
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.ascom.alpaca.telescope import TelescopeAlpacaDriver, alpaca_response

logger = logging.getLogger("ascom.alpaca")

# Alpaca default port (official standard)
ALPACA_DEFAULT_PORT = 5555
ALPACA_DEFAULT_HOST = "0.0.0.0"

# Server ID for Alpaca
ALPACA_SERVER_ID = "astro-hub-alpaca"


# ================================================================== #
#  Alpaca Router - Telescope
# ================================================================== #

def create_telescope_router(driver: TelescopeAlpacaDriver):
    """Create FastAPI router for Alpaca Telescope endpoints."""
    from fastapi import APIRouter

    router = APIRouter()
    device_num = driver.DEVICE_NUMBER

    # --- Properties ---

    @router.get(f"/api/v1/telescope/{device_num}/connected")
    async def get_connected():
        return alpaca_response(value=driver.connected)

    @router.put(f"/api/v1/telescope/{device_num}/connected")
    async def set_connected(Connected: bool = Query(...)):
        driver.connected = Connected
        return alpaca_response(value=None)

    @router.get(f"/api/v1/telescope/{device_num}/rightascension")
    async def get_ra():
        if not driver.connected:
            return alpaca_response(error="Not connected")
        return alpaca_response(value=driver.right_ascension)

    @router.get(f"/api/v1/telescope/{device_num}/declination")
    async def get_dec():
        if not driver.connected:
            return alpaca_response(error="Not connected")
        return alpaca_response(value=driver.declination)

    @router.get(f"/api/v1/telescope/{device_num}/isslew")
    async def get_is_slew():
        if not driver.connected:
            return alpaca_response(error="Not connected")
        return alpaca_response(value=driver.is_slew)

    @router.get(f"/api/v1/telescope/{device_num}/tracking")
    async def get_tracking():
        if not driver.connected:
            return alpaca_response(error="Not connected")
        return alpaca_response(value=driver.tracking)

    @router.put(f"/api/v1/telescope/{device_num}/tracking")
    async def set_tracking(Tracking: bool = Query(...)):
        driver.tracking = Tracking
        return alpaca_response(value=None)

    @router.get(f"/api/v1/telescope/{device_num}/atpark")
    async def get_at_park():
        if not driver.connected:
            return alpaca_response(error="Not connected")
        return alpaca_response(value=driver.at_park)

    # --- Actions ---

    @router.put(f"/api/v1/telescope/{device_num}/slewtocoordinates")
    async def slew_to_coordinates(
        RightAscension: float = Query(..., description="RA in hours (0-24)"),
        Declination: float = Query(..., description="Dec in degrees (-90 to +90)"),
    ):
        if not driver.connected:
            return alpaca_response(error="Not connected")
        result = driver.slew_to_coordinates(RightAscension, Declination)
        if result.get("ErrorMessage"):
            return alpaca_response(error=result["ErrorMessage"])
        return alpaca_response(value=None)

    @router.put(f"/api/v1/telescope/{device_num}/abortslew")
    async def abort_slew():
        if not driver.connected:
            return alpaca_response(error="Not connected")
        result = driver.abort_slew()
        if result.get("ErrorMessage"):
            return alpaca_response(error=result["ErrorMessage"])
        return alpaca_response(value=None)

    @router.put(f"/api/v1/telescope/{device_num}/park")
    async def park():
        if not driver.connected:
            return alpaca_response(error="Not connected")
        result = driver.park()
        if result.get("ErrorMessage"):
            return alpaca_response(error=result["ErrorMessage"])
        return alpaca_response(value=None)

    @router.put(f"/api/v1/telescope/{device_num}/unpark")
    async def unpark():
        if not driver.connected:
            return alpaca_response(error="Not connected")
        result = driver.unpark()
        if result.get("ErrorMessage"):
            return alpaca_response(error=result["ErrorMessage"])
        return alpaca_response(value=None)

    @router.put(f"/api/v1/telescope/{device_num}/action")
    async def action(
        ActionName: str = Query(...),
        Parameters: str = Query(""),
    ):
        result = driver.action(ActionName, Parameters)
        return result

    # --- Read-only Info ---

    @router.get(f"/api/v1/telescope/{device_num}/description")
    async def get_description():
        return alpaca_response(value=driver.description)

    @router.get(f"/api/v1/telescope/{device_num}/driverinfo")
    async def get_driver_info():
        return alpaca_response(value=driver.driver_info)

    @router.get(f"/api/v1/telescope/{device_num}/name")
    async def get_name():
        return alpaca_response(value=driver.name)

    @router.get(f"/api/v1/telescope/{device_num}/driverversion")
    async def get_driver_version():
        return alpaca_response(value=driver.driver_version)

    @router.get(f"/api/v1/telescope/{device_num}/interfaceversion")
    async def get_interface_version():
        return alpaca_response(value=driver.interface_version)

    @router.get(f"/api/v1/telescope/{device_num}/alignmentmode")
    async def get_alignment_mode():
        if not driver.connected:
            return alpaca_response(error="Not connected")
        return alpaca_response(value=driver.alignment_mode)

    @router.get(f"/api/v1/telescope/{device_num}/canpark")
    async def get_can_park():
        return alpaca_response(value=driver.can_set_park)

    @router.get(f"/api/v1/telescope/{device_num}/canslew")
    async def get_can_slew():
        return alpaca_response(value=driver.can_slew)

    @router.get(f"/api/v1/telescope/{device_num}/cansettracking")
    async def get_can_set_tracking():
        return alpaca_response(value=driver.can_set_tracking)

    @router.get(f"/api/v1/telescope/{device_num}/siderealtime")
    async def get_sidereal_time():
        if not driver.connected:
            return alpaca_response(error="Not connected")
        return alpaca_response(value=driver.sidereal_time)

    @router.get(f"/api/v1/telescope/{device_num}/utcoffset")
    async def get_utc_offset():
        return alpaca_response(value=driver.utc_offset)

    @router.get(f"/api/v1/telescope/{device_num}/targetrightascension")
    async def get_target_ra():
        if not driver.connected:
            return alpaca_response(error="Not connected")
        return alpaca_response(value=driver.target_right_ascension)

    @router.get(f"/api/v1/telescope/{device_num}/targetdeclination")
    async def get_target_dec():
        if not driver.connected:
            return alpaca_response(error="Not connected")
        return alpaca_response(value=driver.target_declination)

    @router.get(f"/api/v1/telescope/{device_num}/trackingrate")
    async def get_tracking_rate():
        if not driver.connected:
            return alpaca_response(error="Not connected")
        return alpaca_response(value=driver.tracking_rate)

    @router.get(f"/api/v1/telescope/{device_num}/trackingratesavailable")
    async def get_tracking_rates():
        return alpaca_response(value=driver.tracking_rates_available)

    @router.get(f"/api/v1/telescope/{device_num}/status")
    async def get_status():
        if not driver.connected:
            return alpaca_response(error="Not connected")
        return alpaca_response(value=driver.get_status())

    return router


# ================================================================== #
#  Management Router (Device Discovery)
# ================================================================== #

def create_management_router(telescope_driver: TelescopeAlpacaDriver):
    """Create Alpaca management router for device discovery.

    NINA calls /management/v1/apidevices to discover available devices.
    """
    from fastapi import APIRouter

    router = APIRouter()

    @router.get("/management/v1/apidevices")
    async def list_api_devices():
        """Return list of available ASCOM devices.

        This is the primary endpoint NINA uses for discovery.
        """
        devices = []

        # Telescope
        devices.append({
            "DeviceType": telescope_driver.DEVICE_TYPE_ID,
            "DeviceName": telescope_driver.name,
            "UniqueID": f"astro-hub-telescope-{telescope_driver.DEVICE_NUMBER}",
            "DriverVersion": telescope_driver.driver_version,
            "InterfaceVersion": telescope_driver.interface_version,
        })

        return {
            "Value": devices,
            "ErrorMessage": "",
            "CallerStacktrace": "",
        }

    @router.get("/management/v1/{device_type}/{device_num}/connected")
    async def get_device_connected(
        device_type: int = PathParam(..., ge=0, le=20),
        device_num: int = PathParam(..., ge=0),
    ):
        if device_type == telescope_driver.DEVICE_TYPE_ID and device_num == telescope_driver.DEVICE_NUMBER:
            return alpaca_response(value=telescope_driver.connected)
        return alpaca_response(value=False, error="Device not found")

    return router


# ================================================================== #
#  Alpaca Server Factory
# ================================================================== #

def create_alpaca_app(
    telescope_driver: TelescopeAlpacaDriver | None = None,
) -> FastAPI:
    """Create the full Alpaca server application.

    Args:
        telescope_driver: Optional underlying telescope driver instance.
                         If None, operates in standalone Alpaca mode.

    Returns:
        Configured FastAPI application serving the Alpaca protocol.
    """
    driver = telescope_driver or TelescopeAlpacaDriver()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("=== Alpaca Server Starting (port %d) ===", ALPACA_DEFAULT_PORT)
        logger.info("NINA discovery endpoint: /management/v1/apidevices")
        yield
        logger.info("=== Alpaca Server Stopping ===")
        driver.connected = False

    app = FastAPI(
        title="AstroHub Alpaca Server",
        description="ASCOM Alpaca Protocol Server for AstroHub - Compatible with NINA and other Alpaca clients",
        version="1.0",
        lifespan=lifespan,
    )

    app.include_router(create_management_router(driver))
    app.include_router(create_telescope_router(driver))

    # CORS - allow all origins (Alpaca clients can be anywhere)
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app


# ================================================================== #
#  Standalone Alpaca Server Class
# ================================================================== #

class AlpacaServer:
    """Standalone Alpaca server wrapper.

    Can be started from the main M9 app or independently.
    """

    def __init__(
        self,
        host: str = ALPACA_DEFAULT_HOST,
        port: int = ALPACA_DEFAULT_PORT,
        telescope_driver: TelescopeAlpacaDriver | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self._driver = telescope_driver or TelescopeAlpacaDriver()
        self._app = create_alpaca_app(self._driver)
        self._uvicorn_server = None

    @property
    def app(self) -> FastAPI:
        return self._app

    @property
    def driver(self) -> TelescopeAlpacaDriver:
        return self._driver

    def start(self) -> None:
        """Start the Alpaca server (blocking)."""
        import uvicorn
        config = uvicorn.Config(
            app=self._app,
            host=self.host,
            port=self.port,
            log_level="info",
            access_log=False,
        )
        self._uvicorn_server = uvicorn.Server(config)
        self._uvicorn_server.run()

    def start_background(self) -> None:
        """Start the Alpaca server in a background thread."""
        import threading
        import uvicorn

        def _run():
            config = uvicorn.Config(
                app=self._app,
                host=self.host,
                port=self.port,
                log_level="warning",
                access_log=False,
            )
            server = uvicorn.Server(config)
            self._uvicorn_server = server
            server.run()

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        logger.info("Alpaca server started in background on %s:%d", self.host, self.port)

    def stop(self) -> None:
        """Stop the Alpaca server."""
        if self._uvicorn_server:
            self._uvicorn_server.should_exit = True
        self._driver.connected = False
        logger.info("Alpaca server stopped")


# ================================================================== #
#  CLI Entry
# ================================================================== #

def main() -> None:
    """CLI entry point for standalone Alpaca server."""
    parser = argparse.ArgumentParser(description="M9 ASCOM Alpaca Server v1.0")
    parser.add_argument("--host", default=ALPACA_DEFAULT_HOST, help=f"Listen address (default: {ALPACA_DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=ALPACA_DEFAULT_PORT, help=f"Listen port (default: {ALPACA_DEFAULT_PORT})")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

    logger.info("Starting AstroHub Alpaca Server on %s:%d", args.host, args.port)
    logger.info("NINA discovery: http://%s:%d/management/v1/apidevices", args.host, args.port)

    server = AlpacaServer(host=args.host, port=args.port)
    server.start()


if __name__ == "__main__":
    main()
