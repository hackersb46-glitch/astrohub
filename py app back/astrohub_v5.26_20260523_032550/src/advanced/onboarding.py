"""
AstroHub v2.0 - 首次连接引导模块 (Onboarding)

管理设备首次连接时的引导流程:
- is_new_device(): 判断是否为新设备
- start_onboarding(): 开始引导流程
- get_progress(): 获取进度
- complete_onboarding(): 完成引导

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config_paths import DATA_DIR
from src.advanced.config_writer import (
    load_device_config,
    save_device_config,
    DeviceConfig,
    _normalize_mac,
)


DEVICES_DIR = DATA_DIR / "devices"
ONBOARDING_STEPS = [
    "device_info",         # 获取设备基本信息
    "capability_detection", # 功能探测 (P4.1-P4.20)
    "ptz_home_verification", # PTZ HOME 验证
    "limit_testing",        # 限位测试 (P6.0-P6.4)
    "speed_calibration",    # 速度校准 (P5.4 + M4 P3)
    "restore_defaults",     # 恢复默认值 (P4.21)
    "config_save",          # 保存配置
    "complete",             # 完成
]


@dataclass
class OnboardingState:
    """引导流程状态。"""
    mac: str = ""
    started_at: str = ""
    current_step: int = 0
    total_steps: int = len(ONBOARDING_STEPS)
    steps_completed: list[str] = field(default_factory=list)
    current_step_name: str = ""
    completed: bool = False
    results: dict = field(default_factory=dict)


class OnboardingManager:
    """设备首次连接引导管理器。"""

    @staticmethod
    def is_new_device(mac: str) -> bool:
        """判断是否为新设备 (首次连接)。
        
        新设备判定标准:
        1. 没有对应的设备配置文件
        2. 或者设备配置中 onboarding_complete = False
        """
        norm_mac = _normalize_mac(mac)
        config_path = DEVICES_DIR / f"{norm_mac}.json"

        if not config_path.exists():
            return True

        config = load_device_config(norm_mac)
        if config and config.onboarding_complete:
            return False

        return True

    def get_onboarding_state(self, mac: str) -> OnboardingState:
        """获取设备的引导状态。"""
        norm_mac = _normalize_mac(mac)
        config = load_device_config(norm_mac)

        state = OnboardingState(mac=norm_mac)

        if config and config.metadata:
            onboard_meta = config.metadata.get("onboarding", {})
            state.started_at = onboard_meta.get("started_at", "")
            state.current_step = onboard_meta.get("current_step", 0)
            state.steps_completed = onboard_meta.get("steps_completed", [])
            state.completed = onboard_meta.get("completed", False)
            state.results = onboard_meta.get("results", {})

            if state.current_step < len(ONBOARDING_STEPS):
                state.current_step_name = ONBOARDING_STEPS[state.current_step]

        return state

    def _save_state(self, mac: str, state: OnboardingState) -> None:
        """保存引导状态到设备配置。"""
        norm_mac = _normalize_mac(mac)
        config = load_device_config(norm_mac)
        if not config:
            config = DeviceConfig(mac=norm_mac)

        config.metadata["onboarding"] = {
            "started_at": state.started_at,
            "current_step": state.current_step,
            "steps_completed": state.steps_completed,
            "completed": state.completed,
            "results": state.results,
        }

        if state.completed:
            config.onboarding_complete = True

        save_device_config(config)

    def start_onboarding(self, mac: str) -> dict[str, Any]:
        """开始引导流程。
        
        返回:
            {
                "success": bool,
                "message": str,
                "steps": list[str],
                "current_step": int,
                "estimated_time_seconds": int,
            }
        """
        norm_mac = _normalize_mac(mac)

        # 检查是否已经完成
        if not self.is_new_device(norm_mac) and self._is_completed(norm_mac):
            return {
                "success": False,
                "message": "该设备已完成引导",
                "steps": ONBOARDING_STEPS,
                "current_step": len(ONBOARDING_STEPS),
            }

        state = OnboardingState(
            mac=norm_mac,
            started_at=datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            current_step=0,
            current_step_name=ONBOARDING_STEPS[0],
        )
        self._save_state(mac, state)

        # 估算时间 (每个步骤大约 30-60 秒)
        estimated_time = len(ONBOARDING_STEPS) * 30

        return {
            "success": True,
            "message": "引导流程已开始",
            "steps": ONBOARDING_STEPS,
            "current_step": 0,
            "current_step_name": ONBOARDING_STEPS[0],
            "total_steps": len(ONBOARDING_STEPS),
            "estimated_time_seconds": estimated_time,
        }

    def get_progress(self, mac: str) -> dict[str, Any]:
        """获取引导进度。
        
        返回:
            {
                "success": bool,
                "mac": str,
                "current_step": int,
                "current_step_name": str,
                "total_steps": int,
                "progress_percent": float,
                "steps_completed": list[str],
                "completed": bool,
            }
        """
        norm_mac = _normalize_mac(mac)
        state = self.get_onboarding_state(norm_mac)

        progress_percent = 0
        if state.total_steps > 0:
            progress_percent = round(
                len(state.steps_completed) / state.total_steps * 100, 1
            )

        return {
            "success": True,
            "mac": state.mac,
            "current_step": state.current_step,
            "current_step_name": state.current_step_name,
            "total_steps": state.total_steps,
            "progress_percent": progress_percent,
            "steps_completed": state.steps_completed,
            "completed": state.completed,
            "started_at": state.started_at,
        }

    def advance_step(self, mac: str, step_name: str, step_result: dict | None = None) -> dict[str, Any]:
        """推进引导到下一个步骤。
        
        由各个测试模块在完成后调用。
        """
        norm_mac = _normalize_mac(mac)
        state = self.get_onboarding_state(norm_mac)

        # 标记当前步骤完成
        if step_name:
            state.steps_completed.append(step_name)
            if step_result:
                state.results[step_name] = step_result

        # 推进到下一步
        next_step = len(state.steps_completed)
        if next_step >= len(ONBOARDING_STEPS):
            state.current_step = len(ONBOARDING_STEPS) - 1
            state.current_step_name = ONBOARDING_STEPS[-1]
        else:
            state.current_step = next_step
            state.current_step_name = ONBOARDING_STEPS[next_step]

        self._save_state(mac, state)

        return {
            "success": True,
            "current_step": state.current_step,
            "current_step_name": state.current_step_name,
            "completed_steps": len(state.steps_completed),
            "all_done": state.current_step_name == "complete",
        }

    def complete_onboarding(self, mac: str) -> dict[str, Any]:
        """完成引导流程。"""
        norm_mac = _normalize_mac(mac)
        state = self.get_onboarding_state(norm_mac)

        state.completed = True
        state.current_step = len(ONBOARDING_STEPS) - 1
        state.current_step_name = "complete"
        if "complete" not in state.steps_completed:
            state.steps_completed.append("complete")

        self._save_state(mac, state)

        return {
            "success": True,
            "message": "引导流程已完成",
            "mac": norm_mac,
            "completed_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "steps_completed": len(state.steps_completed),
            "total_steps": state.total_steps,
        }

    def execute_full_onboarding(
        self, mac: str, ip: str, username: str = "admin",
        password: str = "", port: int = 80,
    ) -> dict[str, Any]:
        """自动执行完整的设备引导流程 (8 个步骤)。

        步骤:
        1. device_info: 获取基本信息
        2. capability_detection: 功能探测 (P4.1-P4.20)
        3. ptz_home_verification: HOME 位验证
        4. limit_testing: 限位测试 (P6.0-P6.4)
        5. speed_calibration: 速度校准 (P5.4 + M4 P3)
        6. restore_defaults: 恢复默认值 (P4.21)
        7. config_save: 保存配置
        8. complete
        """
        from src.ptz.isapi.client import ISAPIClient
        from src.advanced.function import FunctionDetector
        from src.advanced.limit import LimitTester
        from src.advanced.speed import SpeedTester
        from src.advanced.config_writer import write_device_config

        # Start onboarding
        start_result = self.start_onboarding(mac)
        if not start_result.get("success"):
            return {"success": False, "message": "引导已开始", **start_result}

        results: dict[str, Any] = {}

        # 1. Device info
        client = ISAPIClient(ip=ip, username=username, password=password, port=port)
        if not client.verify_credentials():
            return {"success": False, "message": "设备认证失败", "step": "device_info"}

        try:
            import xml.etree.ElementTree as ET
            device_info_resp = client.get("/System/deviceInfo")
            device_info: dict[str, str] = {}
            if device_info_resp.status_code == 200:
                root = ET.fromstring(device_info_resp.xml)
                for elem in root.iter():
                    local_name = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                    device_info[local_name] = elem.text or ""
            results["device_info"] = device_info
            self.advance_step(mac, "device_info", device_info)

            # 2. Capability detection
            detector = FunctionDetector(client)
            cap_results = {}
            from src.advanced.function import FUNCTION_ENDPOINTS
            for item_key in FUNCTION_ENDPOINTS:
                cap_results[item_key] = detector.detect_single(item_key)
            results["capabilities"] = cap_results
            self.advance_step(mac, "capability_detection", {"count": len(cap_results)})

            # 3. HOME verification
            limit_tester = LimitTester(client)
            stability = limit_tester.goto_home_verify_stability()
            results["home_stability"] = stability
            self.advance_step(mac, "ptz_home_verification", {"deviation": stability.get("deviation", 0)})

            # 4. Limit testing
            limit_results = limit_tester.run_all_tests()
            results["limits"] = limit_results
            self.advance_step(mac, "limit_testing", {"pan_range": f"{limit_results.get('pan_min', 0)}-{limit_results.get('pan_max', 3600)}"})

            # 5. Speed calibration
            speed_tester = SpeedTester(client)
            speed_results = speed_tester.run_all_tests()
            results["speed"] = speed_results
            self.advance_step(mac, "speed_calibration", {"accuracy": speed_results.get("accuracy", 0)})

            # 6. Restore defaults
            restore_ok = detector.restore_all()
            results["restore"] = {"success": restore_ok}
            self.advance_step(mac, "restore_defaults", {"success": restore_ok})

            # 7. Save config
            config_result = write_device_config(
                mac=mac, ip=ip,
                capabilities=cap_results,
                limits=limit_results,
                speed=speed_results,
                model=device_info.get("model", ""),
                serial_number=device_info.get("serialNumber", ""),
                firmware_version=device_info.get("firmwareVersion", ""),
            )
            results["config_save"] = config_result
            self.advance_step(mac, "config_save", config_result)

            # 8. Complete
            complete_result = self.complete_onboarding(mac)
            results["complete"] = complete_result

            return {
                "success": True,
                "message": f"引导流程已完成: {mac}",
                "steps_completed": len(ONBOARDING_STEPS),
                "results_summary": {
                    "capabilities_count": len(cap_results),
                    "home_stable": stability.get("stability_check", False),
                    "limits": {"pan": f"{limit_results.get('pan_min', 0)}-{limit_results.get('pan_max', 3600)}"},
                    "speed_accuracy": speed_results.get("accuracy", "N/A"),
                    "config_saved": config_result.get("success", False),
                },
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"引导流程异常: {e}",
                "results": results,
            }

    def reset_onboarding(self, mac: str) -> dict[str, Any]:
        """重置引导流程 (允许重新执行)。"""
        norm_mac = _normalize_mac(mac)
        config = load_device_config(norm_mac)

        if config:
            config.onboarding_complete = False
            config.onboarding_started = False
            config.metadata.pop("onboarding", None)
            save_device_config(config)

        return {
            "success": True,
            "message": "引导流程已重置",
            "mac": norm_mac,
        }

    def _is_completed(self, mac: str) -> bool:
        """内部方法：检查引导是否完成。"""
        norm_mac = _normalize_mac(mac)
        config = load_device_config(norm_mac)
        if config:
            return config.onboarding_complete
        return False
