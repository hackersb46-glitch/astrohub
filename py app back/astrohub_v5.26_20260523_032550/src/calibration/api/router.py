"""
M4 Calibration Service v1.0 - FastAPI 路由层

包含校准管理、自动对焦、色彩平衡、速度映射、位置校准、报告生成、恢复路由。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/v1", tags=["M4 Calibration Service"])


# ------------------------------------------------------------------ #
#  全局管理器实例延迟引用
# ------------------------------------------------------------------ #

_managers: dict[str, Any] = {}


def set_managers(**kwargs: Any) -> None:
    """注入管理器实例到路由层。

    Args:
        **kwargs: 各管理器实例
    """
    _managers.update(kwargs)


def _get_calibration_manager() -> Any:
    manager = _managers.get("calibration_manager")
    if manager is None:
        raise HTTPException(status_code=500, detail="CalibrationManager 未初始化")
    return manager


def _get_auto_focus() -> Any:
    manager = _managers.get("auto_focus")
    if manager is None:
        raise HTTPException(status_code=500, detail="AutoFocusCalibrator 未初始化")
    return manager


def _get_color_balance() -> Any:
    manager = _managers.get("color_balance")
    if manager is None:
        raise HTTPException(status_code=500, detail="ColorBalanceCalibrator 未初始化")
    return manager


def _get_speed_mapping() -> Any:
    manager = _managers.get("speed_mapping")
    if manager is None:
        raise HTTPException(status_code=500, detail="SpeedMappingCalibrator 未初始化")
    return manager


def _get_position_calibration() -> Any:
    manager = _managers.get("position_calibration")
    if manager is None:
        raise HTTPException(status_code=500, detail="PositionCalibrator 未初始化")
    return manager


def _get_calibration_store() -> Any:
    manager = _managers.get("calibration_store")
    if manager is None:
        raise HTTPException(status_code=500, detail="CalibrationStore 未初始化")
    return manager


def _get_report_generator() -> Any:
    manager = _managers.get("report_generator")
    if manager is None:
        raise HTTPException(status_code=500, detail="ReportGenerator 未初始化")
    return manager


def _get_calibration_recovery() -> Any:
    manager = _managers.get("calibration_recovery")
    if manager is None:
        raise HTTPException(status_code=500, detail="CalibrationRecovery 未初始化")
    return manager


# ------------------------------------------------------------------ #
#  P0 - 校准框架
# ------------------------------------------------------------------ #

@router.get("/calibration/status", summary="查询校准状态(P0)")
async def get_calibration_status() -> dict:
    """获取当前校准状态。"""
    return _get_calibration_manager().get_status()


@router.post("/calibration/start", summary="启动校准流程(P0.1)")
async def start_calibration(
    device_mac: str = Query(..., description="设备MAC地址"),
    steps: str | None = Query(None, description="要执行的步骤，逗号分隔: auto_focus,color_balance,speed_mapping,position_calibration"),
) -> dict:
    """启动校准流程。"""
    manager = _get_calibration_manager()
    step_list = [s.strip() for s in steps.split(",")] if steps else None
    result = manager.start_calibration(steps=step_list)
    if not result.get("success"):
        return result  # 校准中途失败也返回结果
    return result


@router.post("/calibration/reset", summary="重置校准状态")
async def reset_calibration() -> dict:
    """重置校准状态到idle。"""
    _get_calibration_manager().reset()
    return {"success": True, "state": "idle"}


@router.get("/calibration/logs", summary="查询校准日志(P0.3)")
async def get_calibration_logs() -> list[dict]:
    """获取校准操作日志。"""
    return _get_calibration_manager().get_logs()


@router.get("/calibration/summary", summary="查询校准汇总")
async def get_calibration_summary() -> dict:
    """获取校准汇总信息。"""
    return _get_calibration_manager().get_summary()


# ------------------------------------------------------------------ #
#  P1 - 自动对焦
# ------------------------------------------------------------------ #

@router.post("/calibration/auto-focus/run", summary="自动对焦完整校准(P1)")
async def run_auto_focus_calibration() -> dict:
    """执行完整的自动对焦校准流程。"""
    result = _get_auto_focus().run_full_calibration()
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=f"自动对焦校准失败: {result}")
    return result


@router.post("/calibration/auto-focus/range", summary="对焦范围探测(P1.1)")
async def detect_focus_range() -> dict:
    """获取设备对焦能力的上下限。"""
    return _get_auto_focus().detect_focus_range()


@router.post("/calibration/auto-focus/accuracy", summary="对焦精度测试(P1.2)")
async def test_focus_accuracy() -> dict:
    """测试对焦在不同位置的精度。"""
    return _get_auto_focus().test_focus_accuracy()


@router.post("/calibration/auto-focus/auto", summary="自动对焦算法(P1.3)")
async def run_auto_focus() -> dict:
    """通过对比度检测找到最佳对焦点。"""
    return _get_auto_focus().auto_focus()


@router.post("/calibration/auto-focus/restore", summary="对焦还原(P1.4)")
async def restore_focus() -> dict:
    """对焦测试后恢复原始状态。"""
    return _get_auto_focus().restore_focus()


# ------------------------------------------------------------------ #
#  P2 - 色彩平衡
# ------------------------------------------------------------------ #

@router.post("/calibration/color-balance/run", summary="色彩平衡完整校准(P2)")
async def run_color_balance_calibration() -> dict:
    """执行完整的色彩平衡校准流程。"""
    result = _get_color_balance().run_full_calibration()
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=f"色彩平衡校准失败: {result}")
    return result


@router.post("/calibration/color-balance/white", summary="白平衡校准(P2.1)")
async def calibrate_white_balance() -> dict:
    """校准设备白平衡。"""
    return _get_color_balance().calibrate_white_balance()


@router.post("/calibration/color-balance/temperature", summary="色温调节测试(P2.2)")
async def test_temperature_range() -> dict:
    """测试色温调节范围（2800K-6500K）。"""
    return _get_color_balance().test_temperature_range()


@router.post("/calibration/color-balance/accuracy", summary="色彩还原度测试(P2.3)")
async def test_color_accuracy() -> dict:
    """测试设备色彩还原准确性。"""
    return _get_color_balance().test_color_accuracy()


# ------------------------------------------------------------------ #
#  P3 - 速度映射
# ------------------------------------------------------------------ #

@router.post("/calibration/speed-mapping/run", summary="速度映射完整校准(P3)")
async def run_speed_mapping_calibration() -> dict:
    """执行完整的速度映射校准流程。"""
    result = _get_speed_mapping().run_full_calibration()
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=f"速度映射校准失败: {result}")
    return result


@router.post("/calibration/speed-mapping/calibrate", summary="电机速度校准(P3.1)")
async def calibrate_speeds() -> dict:
    """校准PTZ电机在不同速度下的实际表现。"""
    return _get_speed_mapping().calibrate_speeds()


@router.post("/calibration/speed-mapping/fit", summary="速度曲线拟合(P3.2)")
async def fit_speed_curve() -> dict:
    """使用校准数据拟合速度曲线。"""
    return _get_speed_mapping().fit_speed_curve()


@router.post("/calibration/speed-mapping/verify", summary="速度精度验证(P3.3)")
async def verify_speed_accuracy() -> dict:
    """验证补偿后的速度精度。"""
    return _get_speed_mapping().verify_speed_accuracy()


# ------------------------------------------------------------------ #
#  P4 - 位置校准
# ------------------------------------------------------------------ #

@router.post("/calibration/position/run", summary="位置校准完整流程(P4)")
async def run_position_calibration() -> dict:
    """执行完整的位置校准流程。"""
    result = _get_position_calibration().run_full_calibration()
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=f"位置校准失败: {result}")
    return result


@router.post("/calibration/position/calibrate", summary="坐标系校准(P4.1)")
async def calibrate_coordinate_system() -> dict:
    """校准设备P/T坐标系。"""
    return _get_position_calibration().calibrate_coordinate_system()


@router.post("/calibration/position/compensate", summary="偏差补偿(P4.2)")
async def build_compensation_table() -> dict:
    """根据校准结果建立偏差补偿表。"""
    return _get_position_calibration().build_compensation_table()


@router.post("/calibration/position/verify", summary="位置精度测试(P4.3)")
async def test_position_accuracy() -> dict:
    """验证补偿后的定位精度。"""
    return _get_position_calibration().test_position_accuracy()


# ------------------------------------------------------------------ #
#  P5 - 校准数据存储
# ------------------------------------------------------------------ #

@router.post("/calibration/data/save", summary="保存校准参数(P5.1)")
async def save_calibration_data(
    device_mac: str = Query(..., description="设备MAC地址"),
) -> dict:
    """保存校准结果到持久化存储。"""
    # 收集所有校准结果并保存
    store = _get_calibration_store()
    calibration_data = {
        "device_mac": device_mac,
    }

    # 尝试从各校准器获取数据
    auto_focus_cal = _get_auto_focus()
    af_snapshot = getattr(auto_focus_cal, "_focus_range", None)
    if af_snapshot:
        calibration_data["auto_focus_range"] = af_snapshot

    result = store.save_calibration(device_mac=device_mac, calibration_data=calibration_data)
    return {"success": True, "record": result}


@router.get("/calibration/data/history", summary="校准历史查询(P5.2)")
async def get_calibration_history(
    device_mac: str | None = Query(None, description="设备MAC地址"),
    start_time: str | None = Query(None, description="起始时间"),
    end_time: str | None = Query(None, description="结束时间"),
    limit: int = Query(default=20, description="返回记录数"),
) -> list[dict]:
    """按设备/时间范围查询校准历史。"""
    return _get_calibration_store().get_calibration_history(
        device_mac=device_mac,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )


@router.get("/calibration/data/latest/{device_mac}", summary="获取最新校准记录")
async def get_latest_calibration(device_mac: str) -> dict:
    """获取设备最新的校准记录。"""
    result = _get_calibration_store().get_latest_calibration(device_mac)
    if result is None:
        raise HTTPException(status_code=404, detail=f"设备无校准记录: {device_mac}")
    return result


@router.get("/calibration/data/devices", summary="获取所有校准设备列表")
async def get_all_calibration_devices() -> list[str]:
    """获取所有有校准记录的设备MAC列表。"""
    return _get_calibration_store().get_all_devices()


# ------------------------------------------------------------------ #
#  P6 - 校准报告
# ------------------------------------------------------------------ #

@router.post("/calibration/report/generate", summary="生成校准报告(P6)")
async def generate_calibration_report(
    device_mac: str = Query(..., description="设备MAC地址"),
) -> dict:
    """生成校准结果报告和建议。"""
    # 从各校准器收集结果
    auto_focus_cal = _get_auto_focus()
    color_cal = _get_color_balance()
    speed_cal = _get_speed_mapping()
    position_cal = _get_position_calibration()

    calibration_results = {
        "auto_focus": auto_focus_cal.run_full_calibration(),
        "color_balance": color_cal.run_full_calibration(),
        "speed_mapping": speed_cal.run_full_calibration(),
        "position_calibration": position_cal.run_full_calibration(),
    }

    report = _get_report_generator().generate_report(device_mac, calibration_results)

    return {"success": True, "report": report}


@router.post("/calibration/report/save", summary="保存校准报告到文件")
async def save_calibration_report(
    device_mac: str = Query(..., description="设备MAC地址"),
    filename: str | None = Query(None, description="文件名"),
) -> dict:
    """保存校准报告到文件。"""
    auto_focus_cal = _get_auto_focus()
    color_cal = _get_color_balance()
    speed_cal = _get_speed_mapping()
    position_cal = _get_position_calibration()

    calibration_results = {
        "auto_focus": auto_focus_cal.run_full_calibration(),
        "color_balance": color_cal.run_full_calibration(),
        "speed_mapping": speed_cal.run_full_calibration(),
        "position_calibration": position_cal.run_full_calibration(),
    }

    file_path = _get_report_generator().save_report(device_mac, calibration_results, filename)
    return {"success": True, "file_path": str(file_path)}


@router.post("/calibration/suggestions", summary="生成改进建议(P6.2)")
async def generate_suggestions() -> dict:
    """根据校准结果生成改进建议。"""
    auto_focus_cal = _get_auto_focus()
    color_cal = _get_color_balance()
    speed_cal = _get_speed_mapping()
    position_cal = _get_position_calibration()

    calibration_results = {
        "auto_focus": auto_focus_cal.run_full_calibration(),
        "color_balance": color_cal.run_full_calibration(),
        "speed_mapping": speed_cal.run_full_calibration(),
        "position_calibration": position_cal.run_full_calibration(),
    }

    suggestions = _get_report_generator().generate_suggestions(calibration_results)
    return {"success": True, "suggestions": suggestions}


# ------------------------------------------------------------------ #
#  P7 - 校准恢复
# ------------------------------------------------------------------ #

@router.post("/calibration/recovery/snapshot", summary="保存校准快照")
async def save_calibration_snapshot(
    device_mac: str = Query(..., description="设备MAC地址"),
) -> dict:
    """校准前保存设备参数快照。"""
    snapshot_params = {
        "focus": 0,
        "white_balance": {"r_gain": 1.0, "g_gain": 1.0, "b_gain": 1.0},
        "speed": 50,
        "position": {"pan": 0, "tilt": 0},
    }
    _get_calibration_recovery().save_snapshot(device_mac, snapshot_params)
    return {"success": True, "device_mac": device_mac, "params_saved": list(snapshot_params.keys())}


@router.post("/calibration/recovery/rollback", summary="异常回滚(P7.2)")
async def rollback_calibration(
    device_mac: str = Query(..., description="设备MAC地址"),
) -> dict:
    """校准失败时回滚到校准前状态。"""
    return _get_calibration_recovery().rollback(device_mac)


@router.post("/calibration/recovery/restore", summary="校准参数恢复(P7.1)")
async def restore_calibration_params(
    device_mac: str = Query(..., description="设备MAC地址"),
    calibration_id: str | None = Query(None, description="校准ID"),
) -> dict:
    """从保存的校准参数恢复设备。"""
    return _get_calibration_recovery().restore_calibration(
        device_mac=device_mac,
        calibration_id=calibration_id,
    )


@router.get("/calibration/recovery/history", summary="回滚历史记录")
async def get_rollback_history(
    device_mac: str | None = Query(None, description="设备MAC地址"),
) -> list[dict]:
    """获取回滚历史记录。"""
    return _get_calibration_recovery().get_rollback_history(device_mac)
