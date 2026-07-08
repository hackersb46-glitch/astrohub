"""
M9 ASCOM v1.0 - FastAPI 路由

实现:
- P0.3: ASCOM 连接测试
- P1: 望远镜连接、Slew 控制、位置查询、跟踪模式、Slew 取消
- P2: 相机 (占位)
- P3: 焦点器连接、步进控制、自动对焦、温度补偿
- 圆顶控制
- 滤镜轮控制
- 气象站

Author: 雅痞张@南方天文
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from src.ascom.constants import (
    ErrorCode,
    ERROR_CODE_DESCRIPTION,
    TrackingMode,
)
from src.ascom.core.driver_manager import (
    get_driver_manager,
    get_telescope,
    get_focuser,
    get_dome,
    get_filter_wheel,
    get_weather_station,
)


# ------------------------------------------------------------------ #
#  路由器定义
# ------------------------------------------------------------------ #

router = APIRouter(prefix="/api/v1/ascom", tags=["M9 ASCOM"])


# ================================================================== #
#  公共工具
# ================================================================== #

def _error_response(code: ErrorCode, message: str = "") -> dict[str, Any]:
    """构造错误响应。"""
    return {
        "code": code.value,
        "message": message or ERROR_CODE_DESCRIPTION.get(code, "未知错误"),
    }


def _ok_response(data: Any = None, message: str = "操作成功") -> dict[str, Any]:
    """构造成功响应。"""
    return {
        "success": True,
        "message": message,
        "data": data or {},
    }


# ================================================================== #
#  P0: 全局状态
# ================================================================== #

@router.get("/status", summary="获取所有设备状态")
async def get_all_status() -> dict:
    """获取所有 ASCOM 设备的连接状态汇总 (P0.3)。"""
    mgr = get_driver_manager()
    return _ok_response(data=mgr.get_all_status())


# ================================================================== #
#  P1: 望远镜控制 (P1.1-P1.5)
# ================================================================== #

@router.post("/telescope/connect", summary="连接望远镜 (P1.1)")
async def telescope_connect(driver_id: str = "") -> dict:
    """连接 ASCOM 望远镜驱动。

    Args:
        driver_id: ASCOM 驱动 ProgID (如 "ASCOM.Simulator.Telescope")
    """
    try:
        scope = get_telescope()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    result = scope.connect(driver_id)
    if not result.get("success"):
        code = ErrorCode(result.get("code", "ASCOM_INTERNAL_ERROR"))  # type: ignore
        raise HTTPException(
            status_code=400,
            detail=_error_response(code, result.get("message", "")),
        )
    return _ok_response(data=result.get("data"), message=result.get("message", ""))


@router.post("/telescope/disconnect", summary="断开望远镜 (P1.1)")
async def telescope_disconnect() -> dict:
    """断开望远镜连接。"""
    scope = get_telescope()
    result = scope.disconnect()
    return _ok_response(message=result.get("message", ""))


@router.post("/telescope/slew", summary="Slew 到目标坐标 (P1.2)")
async def telescope_slew(
    ra: float = Query(..., description="目标赤经 (小时, 0-24)"),
    dec: float = Query(..., description="目标赤纬 (度, -90~+90)"),
) -> dict:
    """控制望远镜 Slew 到目标赤经/赤纬。"""
    scope = get_telescope()
    result = scope.slew_to_coordinates(ra, dec)
    if not result.get("success"):
        code = ErrorCode(result.get("code", "ASCOM_TELESCOPE_SLEW_FAILED"))  # type: ignore
        raise HTTPException(
            status_code=400,
            detail=_error_response(code, result.get("message", "")),
        )
    return _ok_response(message=result.get("message", ""))


@router.get("/telescope/position", summary="查询望远镜位置 (P1.3)")
async def telescope_position() -> dict:
    """查询望远镜当前赤经/赤纬。"""
    scope = get_telescope()
    result = scope.get_position()
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=_error_response(ErrorCode.NOT_CONNECTED, result.get("message", "")))
    return _ok_response(data=result.get("data"))


@router.post("/telescope/tracking", summary="设置跟踪模式 (P1.4)")
async def telescope_tracking(
    mode: str = Query(..., description="跟踪模式: trackSidereal/trackLunar/trackSolar/trackOff"),
) -> dict:
    """设置望远镜跟踪模式。"""
    mode_map = {
        "trackSidereal": TrackingMode.SIDEREAL,
        "trackLunar": TrackingMode.LUNAR,
        "trackSolar": TrackingMode.SOLAR,
        "trackOff": TrackingMode.OFF,
    }
    tracking_mode = mode_map.get(mode)
    if tracking_mode is None:
        raise HTTPException(
            status_code=400,
            detail=_error_response(ErrorCode.INVALID_PARAMETER, f"无效的跟踪模式: {mode}"),
        )

    scope = get_telescope()
    result = scope.set_tracking_mode(tracking_mode)
    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=_error_response(ErrorCode.INTERNAL_ERROR, result.get("message", "")),
        )
    return _ok_response(message=result.get("message"))


@router.post("/telescope/abort", summary="取消 Slew (P1.5)")
async def telescope_abort() -> dict:
    """取消正在进行的 Slew 操作。"""
    scope = get_telescope()
    result = scope.abort_slew()
    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=_error_response(ErrorCode.TELESCOPE_ABORT_FAILED, result.get("message", "")),
        )
    return _ok_response(message=result.get("message"))


@router.get("/telescope/status", summary="望远镜完整状态")
async def telescope_status() -> dict:
    """获取望远镜完整状态信息。"""
    scope = get_telescope()
    result = scope.get_status()
    return _ok_response(data=result.get("data"))


@router.post("/telescope/park", summary="望远镜归位")
async def telescope_park() -> dict:
    """望远镜归位 (Park)。"""
    scope = get_telescope()
    result = scope.park()
    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=_error_response(ErrorCode.TELESCOPE_PARK_FAILED, result.get("message", "")),
        )
    return _ok_response(message=result.get("message"))


@router.post("/telescope/unpark", summary="解除望远镜归位")
async def telescope_unpark() -> dict:
    """解除归位 (UnPark)。"""
    scope = get_telescope()
    result = scope.unpark()
    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=_error_response(ErrorCode.TELESCOPE_UNPARK_FAILED, result.get("message", "")),
        )
    return _ok_response(message=result.get("message"))


# ================================================================== #
#  P3: 焦点器控制 (P3.1-P3.4)
# ================================================================== #

@router.post("/focuser/connect", summary="连接焦点器 (P3.1)")
async def focuser_connect(driver_id: str = "") -> dict:
    """连接 ASCOM 焦点器驱动。"""
    try:
        foc = get_focuser()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    result = foc.connect(driver_id)
    if not result.get("success"):
        code = ErrorCode(result.get("code", "ASCOM_INTERNAL_ERROR"))  # type: ignore
        raise HTTPException(
            status_code=400,
            detail=_error_response(code, result.get("message", "")),
        )
    return _ok_response(data=result.get("data"), message=result.get("message", ""))


@router.post("/focuser/disconnect", summary="断开焦点器 (P3.1)")
async def focuser_disconnect() -> dict:
    """断开焦点器连接。"""
    foc = get_focuser()
    result = foc.disconnect()
    return _ok_response(message=result.get("message", ""))


@router.post("/focuser/move", summary="移动焦点器到指定位置 (P3.2)")
async def focuser_move(
    position: int = Query(..., description="目标位置 (0-MaxStep)"),
) -> dict:
    """移动焦点器到指定步数位置。"""
    foc = get_focuser()
    result = foc.move_to(position)
    if not result.get("success"):
        code = ErrorCode(result.get("code", "ASCOM_FOCUSER_MOVE_FAILED"))  # type: ignore
        raise HTTPException(
            status_code=400,
            detail=_error_response(code, result.get("message", "")),
        )
    return _ok_response(message=result.get("message"))


@router.post("/focuser/abort", summary="停止焦点器移动 (P3.2)")
async def focuser_abort() -> dict:
    """停止焦点器移动。"""
    foc = get_focuser()
    result = foc.abort_move()
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=_error_response(ErrorCode.FOCUSER_MOVE_FAILED, result.get("message", "")))
    return _ok_response(message=result.get("message"))


@router.get("/focuser/position", summary="查询焦点器位置 (P3.2)")
async def focuser_position() -> dict:
    """获取焦点器当前位置。"""
    foc = get_focuser()
    result = foc.get_position()
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=_error_response(ErrorCode.NOT_CONNECTED, result.get("message", "")))
    return _ok_response(data=result.get("data"))


@router.get("/focuser/status", summary="焦点器完整状态")
async def focuser_status() -> dict:
    """获取焦点器完整状态。"""
    foc = get_focuser()
    result = foc.get_status()
    return _ok_response(data=result.get("data"))


@router.get("/focuser/temperature", summary="读取焦点器温度 (P3.4)")
async def focuser_temperature() -> dict:
    """读取焦点器温度。"""
    foc = get_focuser()
    result = foc.get_temperature()
    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=_error_response(ErrorCode.FOCUSER_TEMPERATURE_ERROR, result.get("message", "")),
        )
    return _ok_response(data=result.get("data"))


@router.post("/focuser/temp-comp", summary="设置温度补偿 (P3.4)")
async def focuser_temp_comp(enabled: bool = Query(..., description="是否启用")) -> dict:
    """启用/禁用温度补偿。"""
    foc = get_focuser()
    result = foc.set_temperature_compensation(enabled)
    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=_error_response(ErrorCode.FOCUSER_NOT_SUPPORTED, result.get("message", "")),
        )
    return _ok_response(message=result.get("message"))


# ================================================================== #
#  圆顶控制
# ================================================================== #

@router.post("/dome/connect", summary="连接圆顶")
async def dome_connect(driver_id: str = "") -> dict:
    """连接 ASCOM 圆顶驱动。"""
    try:
        dm = get_dome()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    result = dm.connect(driver_id)
    if not result.get("success"):
        code = ErrorCode(result.get("code", "ASCOM_INTERNAL_ERROR"))  # type: ignore
        raise HTTPException(
            status_code=400,
            detail=_error_response(code, result.get("message", "")),
        )
    return _ok_response(data=result.get("data"), message=result.get("message", ""))


@router.post("/dome/disconnect", summary="断开圆顶")
async def dome_disconnect() -> dict:
    """断开圆顶连接。"""
    dm = get_dome()
    result = dm.disconnect()
    return _ok_response(message=result.get("message", ""))


@router.post("/dome/slew", summary="圆顶旋转到方位角")
async def dome_slew(azimuth: float = Query(..., description="目标方位角 (0-360°)")) -> dict:
    """旋转圆顶到指定方位角。"""
    dm = get_dome()
    result = dm.slew_to_azimuth(azimuth)
    if not result.get("success"):
        code = ErrorCode(result.get("code", "ASCOM_INTERNAL_ERROR"))  # type: ignore
        raise HTTPException(
            status_code=400,
            detail=_error_response(code, result.get("message", "")),
        )
    return _ok_response(message=result.get("message"))


@router.post("/dome/abort", summary="停止圆顶旋转")
async def dome_abort() -> dict:
    """停止圆顶旋转。"""
    dm = get_dome()
    result = dm.abort_slew()
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=_error_response(ErrorCode.INTERNAL_ERROR, result.get("message", "")))
    return _ok_response(message=result.get("message"))


@router.get("/dome/position", summary="查询圆顶位置")
async def dome_position() -> dict:
    """获取圆顶当前方位角。"""
    dm = get_dome()
    result = dm.get_position()
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=_error_response(ErrorCode.NOT_CONNECTED, result.get("message", "")))
    return _ok_response(data=result.get("data"))


@router.get("/dome/status", summary="圆顶完整状态")
async def dome_status() -> dict:
    """获取圆顶完整状态。"""
    dm = get_dome()
    result = dm.get_status()
    return _ok_response(data=result.get("data"))


@router.post("/dome/shutter", summary="圆顶快门")
async def dome_shutter(open_shutter: bool = Query(..., description="True=开, False=关")) -> dict:
    """控制圆顶快门开关。"""
    dm = get_dome()
    result = dm.set_shutter(open_shutter)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=_error_response(ErrorCode.INTERNAL_ERROR, result.get("message", "")))
    return _ok_response(message=result.get("message"))


# ================================================================== #
#  滤镜轮控制
# ================================================================== #

@router.post("/filter-wheel/connect", summary="连接滤镜轮")
async def filter_wheel_connect(driver_id: str = "") -> dict:
    """连接 ASCOM 滤镜轮驱动。"""
    try:
        fw = get_filter_wheel()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    result = fw.connect(driver_id)
    if not result.get("success"):
        code = ErrorCode(result.get("code", "ASCOM_INTERNAL_ERROR"))  # type: ignore
        raise HTTPException(
            status_code=400,
            detail=_error_response(code, result.get("message", "")),
        )
    return _ok_response(data=result.get("data"), message=result.get("message", ""))


@router.post("/filter-wheel/disconnect", summary="断开滤镜轮")
async def filter_wheel_disconnect() -> dict:
    """断开滤镜轮连接。"""
    fw = get_filter_wheel()
    result = fw.disconnect()
    return _ok_response(message=result.get("message", ""))


@router.post("/filter-wheel/position", summary="切换滤镜位置")
async def filter_wheel_position(
    position: int = Query(..., description="滤镜位置 (0-N)"),
) -> dict:
    """切换到指定滤镜位置。"""
    fw = get_filter_wheel()
    result = fw.set_position(position)
    if not result.get("success"):
        code = ErrorCode(result.get("code", "ASCOM_INTERNAL_ERROR"))  # type: ignore
        raise HTTPException(
            status_code=400,
            detail=_error_response(code, result.get("message", "")),
        )
    return _ok_response(message=result.get("message"))


@router.get("/filter-wheel/position", summary="查询滤镜位置")
async def filter_wheel_get_position() -> dict:
    """获取当前滤镜位置。"""
    fw = get_filter_wheel()
    result = fw.get_position()
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=_error_response(ErrorCode.NOT_CONNECTED, result.get("message", "")))
    return _ok_response(data=result.get("data"))


@router.get("/filter-wheel/status", summary="滤镜轮完整状态")
async def filter_wheel_status() -> dict:
    """获取滤镜轮完整状态。"""
    fw = get_filter_wheel()
    result = fw.get_status()
    return _ok_response(data=result.get("data"))


# ================================================================== #
#  气象站
# ================================================================== #

@router.post("/weather/connect", summary="连接气象站")
async def weather_connect(driver_id: str = "") -> dict:
    """连接 ASCOM 气象站驱动。"""
    try:
        ws = get_weather_station()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    result = ws.connect(driver_id)
    if not result.get("success"):
        code = ErrorCode(result.get("code", "ASCOM_INTERNAL_ERROR"))  # type: ignore
        raise HTTPException(
            status_code=400,
            detail=_error_response(code, result.get("message", "")),
        )
    return _ok_response(data=result.get("data"), message=result.get("message", ""))


@router.post("/weather/disconnect", summary="断开气象站")
async def weather_disconnect() -> dict:
    """断开气象站连接。"""
    ws = get_weather_station()
    result = ws.disconnect()
    return _ok_response(message=result.get("message", ""))


@router.get("/weather/data", summary="读取气象数据")
async def weather_data() -> dict:
    """读取当前气象数据。"""
    ws = get_weather_station()
    result = ws.get_data()
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=_error_response(ErrorCode.NOT_CONNECTED, result.get("message", "")))
    return _ok_response(data=result.get("data"))


@router.get("/weather/status", summary="气象站完整状态")
async def weather_status() -> dict:
    """获取气象站完整状态。"""
    ws = get_weather_station()
    result = ws.get_status()
    return _ok_response(data=result.get("data"))


@router.get("/weather/safe", summary="气象安全状态")
async def weather_safe() -> dict:
    """判断当前气象条件是否安全。"""
    ws = get_weather_station()
    is_safe = ws.is_weather_safe()
    return _ok_response(data={"is_safe": is_safe})


@router.post("/weather/safe/wind", summary="设置安全风速")
async def weather_safe_wind(wind_speed: float = Query(..., description="风速上限 (m/s)")) -> dict:
    """设置安全风速上限。"""
    ws = get_weather_station()
    result = ws.set_safe_wind_speed(wind_speed)
    return _ok_response(message=result.get("message", ""))


@router.post("/weather/safe/humidity", summary="设置安全湿度")
async def weather_safe_humidity(humidity: float = Query(..., description="湿度上限 (%)")) -> dict:
    """设置安全湿度上限。"""
    ws = get_weather_station()
    result = ws.set_safe_humidity(humidity)
    return _ok_response(message=result.get("message", ""))
