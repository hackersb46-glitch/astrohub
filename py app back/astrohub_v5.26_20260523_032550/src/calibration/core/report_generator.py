"""
M4 Calibration Service v1.0 - 校准报告生成

校准结果报告(P6.1)、校准建议生成(P6.2)。
汇总所有校准步骤结果，生成MD格式报告，提供可操作的改进建议。

Author: 雅痞张@南方天文
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.calibration.constants import (
    CalibrationResult,
    DATA_DIR,
)
from src.calibration.core.logger import LOG


class ReportGenerator:
    """校准报告生成器。

    生成MD格式校准报告，包含通过/失败状态、具体数值、改进建议。
    """

    def __init__(self, output_dir: Path | None = None) -> None:
        self._output_dir = output_dir or DATA_DIR

    # ------------------------------------------------------------------ #
    #  P6.1 - 校准结果报告
    # ------------------------------------------------------------------ #
    def generate_report(
        self,
        device_mac: str,
        calibration_results: dict[str, Any],
    ) -> str:
        """汇总所有校准步骤的结果，生成MD格式报告。

        Args:
            device_mac: 设备MAC地址
            calibration_results: 各校准步骤的结果字典
                {
                    "auto_focus": {...},
                    "color_balance": {...},
                    "speed_mapping": {...},
                    "position_calibration": {...},
                }

        Returns:
            Markdown格式报告字符串
        """
        LOG.info(f"生成校准报告: device={device_mac}")

        timestamp = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")

        lines = [
            f"# M4 Calibration Service - 校准报告",
            f"",
            f"**设备MAC**: {device_mac}",
            f"**校准时间**: {timestamp}",
            f"**版本**: v1.0",
            f"",
            f"---",
            f"",
            f"## 校准总览",
            f"",
        ]

        overall_status = "PASS"
        items_summary = []

        # 各项目概况
        for cal_type, result_data in calibration_results.items():
            success = result_data.get("success", False)
            status = "PASS" if success else "FAIL"
            if not success:
                overall_status = "FAIL"
            items = result_data.get("details", "")
            items_summary.append((cal_type, status, items))

        lines.append(f"| 校准项目 | 结果 | 详情 |")
        lines.append(f"|----------|------|------|")
        for cal_type, status, items in items_summary:
            display_name = self._display_name(cal_type)
            lines.append(f"| {display_name} | {status} | {items} |")

        lines.extend([
            f"",
            f"**总体结果**: **{overall_status}**",
            f"",
            f"---",
            f"",
        ])

        # 各项目详细结果
        for cal_type, result_data in calibration_results.items():
            lines.extend(self._generate_section(cal_type, result_data))

        # 建议部分
        lines.extend([
            f"---",
            f"",
            f"## 改进建议",
            f"",
        ])

        suggestions = self.generate_suggestions(calibration_results)
        for i, suggestion in enumerate(suggestions, 1):
            priority = suggestion["priority"]
            lines.append(f"{i}. **【{priority.upper()}】** {suggestion['message']}")

        lines.append("")

        report = "\n".join(lines)
        LOG.info(f"校准报告生成完成: lines={len(lines)}, status={overall_status}")
        return report

    def save_report(
        self,
        device_mac: str,
        calibration_results: dict[str, Any],
        filename: str | None = None,
    ) -> Path:
        """保存校准报告到文件。

        Args:
            device_mac: 设备MAC地址
            calibration_results: 校准结果字典
            filename: 文件名，不指定则自动生成

        Returns:
            报告文件路径
        """
        self._output_dir.mkdir(parents=True, exist_ok=True)

        if filename is None:
            ts = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y%m%d_%H%M%S")
            filename = f"calibration_{device_mac}_{ts}.md"

        report = self.generate_report(device_mac, calibration_results)
        file_path = self._output_dir / filename

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(report)

        LOG.done(f"校准报告已保存: {file_path}")
        return file_path

    # ------------------------------------------------------------------ #
    #  P6.2 - 校准建议生成
    # ------------------------------------------------------------------ #
    def generate_suggestions(self, calibration_results: dict[str, Any]) -> list[dict]:
        """根据校准结果生成改进建议。

        分析校准数据，识别需要关注的项目，建议具体可操作。

        Args:
            calibration_results: 各校准步骤的结果字典

        Returns:
            建议列表 [{"priority": "high|medium|low", "message": "..."}]
        """
        suggestions = []

        # 自动对焦建议
        af = calibration_results.get("auto_focus", {})
        if af:
            accuracy = af.get("accuracy_test", {})
            if not accuracy.get("pass", True):
                max_dev = accuracy.get("max_deviation_pct", 0)
                suggestions.append({
                    "priority": "high",
                    "message": f"自动对焦精度不通过(max_deviation={max_dev}%)，建议检查镜头机械结构和驱动电机。",
                })

            restore = af.get("restore", {})
            if not restore.get("success", True):
                suggestions.append({
                    "priority": "high",
                    "message": "对焦还原失败，建议确认校准前快照已保存，校准后必须执行还原操作。",
                })

            autofocus = af.get("auto_focus", {})
            if not autofocus.get("acceptable", True):
                suggestions.append({
                    "priority": "medium",
                    "message": "自动对焦清晰度未达标，建议清洁镜头或检查光学组件。",
                })

        # 色彩平衡建议
        cb = calibration_results.get("color_balance", {})
        if cb:
            color = cb.get("color_accuracy", {})
            if not color.get("all_pass", True):
                failed = [b["name"] for b in color.get("color_blocks", []) if not b.get("pass", True)]
                suggestions.append({
                    "priority": "high",
                    "message": f"色彩还原度不通过(未通过色块: {', '.join(failed)})，建议重新校准白平衡后重试。",
                })

            temp = cb.get("temperature_range", {})
            if not temp.get("coverage_ok", True):
                suggestions.append({
                    "priority": "medium",
                    "message": "色温调节范围覆盖不全，确认设备是否支持2800K-6500K全范围。",
                })

        # 速度映射建议
        sm = calibration_results.get("speed_mapping", {})
        if sm:
            fit = sm.get("curve_fit", {})
            if not fit.get("r_squared_pass", True):
                r2 = fit.get("r_squared", 0)
                suggestions.append({
                    "priority": "high",
                    "message": f"速度曲线拟合不通过(R²={r2}，需要>0.9)，建议增加更多校准点或使用更高阶拟合。",
                })

            verify = sm.get("accuracy_verification", {})
            if not verify.get("all_pass", True):
                failed = [str(r["set_speed"]) for r in verify.get("results", []) if not r.get("pass", True)]
                suggestions.append({
                    "priority": "medium",
                    "message": f"速度精度验证部分不通过(速度档位: {', '.join(failed)})，建议复查电机传动。",
                })

        # 位置校准建议
        pc = calibration_results.get("position_calibration", {})
        if pc:
            acc = pc.get("accuracy_test", {})
            if not acc.get("pass_threshold_met", True):
                rate = acc.get("pass_rate", 0)
                suggestions.append({
                    "priority": "high",
                    "message": f"位置精度不通过(通过率={rate*100:.0f}%，需要>=90%)，建议增加补偿表密度或检查机械偏差。",
                })

            coord = pc.get("coordinate_calibration", {})
            if not coord.get("within_threshold", True):
                max_dev = coord.get("max_deviation", 0)
                suggestions.append({
                    "priority": "high",
                    "message": f"坐标系偏差超出阈值(max_deviation={max_dev}，阈值={coord.get('threshold', 10)})，建议检查安装底座和传感器校准。",
                })

        # 没有失败项
        if not suggestions:
            suggestions.append({
                "priority": "low",
                "message": "所有校准项目均通过，建议定期校准确保精度。",
            })

        # 按优先级排序
        priority_order = {"high": 0, "medium": 1, "low": 2}
        suggestions.sort(key=lambda s: priority_order.get(s["priority"], 3))

        LOG.info(f"生成 {len(suggestions)} 条改进建议")
        return suggestions

    # ------------------------------------------------------------------ #
    #  内部辅助方法
    # ------------------------------------------------------------------ #
    @staticmethod
    def _display_name(cal_type: str) -> str:
        """校准类型的中文显示名。"""
        names = {
            "auto_focus": "自动对焦",
            "color_balance": "色彩平衡",
            "speed_mapping": "速度映射",
            "position_calibration": "位置校准",
        }
        return names.get(cal_type, cal_type)

    def _generate_section(self, cal_type: str, result_data: dict) -> list[str]:
        """生成单个校准项目的详细报告段落。"""
        lines = [
            f"## {self._display_name(cal_type)}",
            f"",
            f"**状态**: {'PASS' if result_data.get('success') else 'FAIL'}",
            f"",
        ]

        # 根据类型添加细节
        if cal_type == "auto_focus":
            af = result_data.get("range_detection", {})
            lines.append(f"- 对焦范围: {af.get('min', 'N/A')} ~ {af.get('max', 'N/A')}")
            accuracy = result_data.get("accuracy_test", {})
            if accuracy:
                lines.append(f"- 精度测试: {'PASS' if accuracy.get('pass') else 'FAIL'} (max_deviation={accuracy.get('max_deviation_pct', 0)}%)")
            autofocus = result_data.get("auto_focus", {})
            if autofocus:
                lines.append(f"- 自动对焦: best_focus={autofocus.get('best_focus', 'N/A')}, sharpness={autofocus.get('sharpness', 'N/A')}")
            restore = result_data.get("restore", {})
            if restore:
                lines.append(f"- 对焦还原: {'PASS' if restore.get('success') else 'FAIL'} (deviation={restore.get('deviation_pct', 'N/A')}%)")

        elif cal_type == "color_balance":
            wb = result_data.get("white_balance", {})
            lines.append(f"- 白平衡: {'PASS' if wb.get('white_test_pass') else 'FAIL'}")
            temp = result_data.get("temperature_range", {})
            lines.append(f"- 色温范围: {'PASS' if temp.get('coverage_ok') else 'FAIL'} ({temp.get('min_supported', 'N/A')}K ~ {temp.get('max_supported', 'N/A')}K)")
            color = result_data.get("color_accuracy", {})
            if color:
                lines.append(f"- 色彩精度: {'PASS' if color.get('all_pass') else 'FAIL'} (max_delta_e={color.get('max_delta_e', 'N/A')})")
                for block in color.get("color_blocks", []):
                    lines.append(f"  - {block['name']}: standard={block['standard']}, measured={block['measured']}, ΔE={block['delta_e']}")

        elif cal_type == "speed_mapping":
            fit = result_data.get("curve_fit", {})
            lines.append(f"- 曲线拟合: R²={fit.get('r_squared', 'N/A')} ({'PASS' if fit.get('r_squared_pass') else 'FAIL'})")
            lines.append(f"- 拟合公式: {fit.get('function', 'N/A')}")
            verify = result_data.get("accuracy_verification", {})
            if verify:
                lines.append(f"- 精度验证: {'PASS' if verify.get('all_pass') else 'FAIL'}")
                for r in verify.get("results", []):
                    lines.append(f"  - set={r['set_speed']}, actual={r['actual_speed']}, deviation={r['deviation_pct']}%")

        elif cal_type == "position_calibration":
            coord = result_data.get("coordinate_calibration", {})
            lines.append(f"- 坐标系偏差: max={coord.get('max_deviation', 'N/A')} ({'PASS' if coord.get('within_threshold') else 'FAIL'})")
            comp = result_data.get("compensation", {})
            lines.append(f"- 偏差补偿: pan_offset={comp.get('pan_offset', 'N/A')}, tilt_offset={comp.get('tilt_offset', 'N/A')}")
            acc = result_data.get("accuracy_test", {})
            if acc:
                lines.append(f"- 精度测试: pass_rate={acc.get('pass_rate', 0)*100:.0f}% ({'PASS' if acc.get('pass_threshold_met') else 'FAIL'})")

        lines.append("")
        return lines
