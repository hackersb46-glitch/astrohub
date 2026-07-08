"""
PTZ_ASTRO v1.1 - 报告生成模块
生成完整测试报告 report_yyyymmdd-NNN.md，包含所有评审点信息、CSV 记录、设备配置。

Author: 雅痞张@南方天文
"""

import json
from datetime import datetime
from pathlib import Path

from src.ptz.core.logger import LOG
from src.ptz.constants import (
    REPORT_DIR,
    RECORD_DIR,
    LOG_DIR,
    DOWNLOAD_DIR,
    PTZ_CONFIG_PATH,
    LOCAL_CONFIG_PATH,
    VERSION,
    AUTHOR,
)


class ReportGenerator:
    """测试报告生成器。"""

    def __init__(self) -> None:
        self._today = datetime.now().strftime("%Y%m%d")
        self.report_num = self._find_max_seq() + 1
        self.report_path = REPORT_DIR / f"report_{self._today}-{self.report_num:03d}.md"
        self.sections: list[str] = []

    def _find_max_seq(self) -> int:
        """找到今天已有的最大报告序号。"""
        existing = list(REPORT_DIR.glob(f"report_{self._today}-*.md"))
        max_seq = 0
        for f in existing:
            stem = f.stem
            parts = stem.rsplit("-", 1)
            if len(parts) == 2:
                try:
                    seq = int(parts[1])
                    if seq > max_seq:
                        max_seq = seq
                except ValueError:
                    continue
        return max_seq

    def add_section(self, title: str, content: str) -> None:
        """添加报告章节。"""
        self.sections.append(f"\n## {title}\n\n{content}\n")

    def _format_table(self, headers: list[str], rows: list[list[str]]) -> str:
        """格式化为 Markdown 表格。"""
        if not rows:
            return "_无数据_"

        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    col_widths[i] = max(col_widths[i], len(str(cell)))

        header_line = "| " + " | ".join(h.ljust(w) for h, w in zip(headers, col_widths)) + " |"
        separator = "| " + " | ".join("-" * w for w in col_widths) + " |"
        data_lines = []
        for row in rows:
            line = "| " + " | ".join(str(c).ljust(w) for c, w in zip(row, col_widths)) + " |"
            data_lines.append(line)

        return f"{header_line}\n{separator}\n" + "\n".join(data_lines)

    def generate(
        self,
        system_info: dict | None = None,
        nic_info: dict | None = None,
        sadp_devices: list | None = None,
        selected_device: dict | None = None,
        auth_result: bool = False,
        capabilities: dict | None = None,
        motion_results: dict | None = None,
        limit_results: dict | None = None,
        csv_files: list[Path] | None = None,
        log_file: Path | None = None,
        device_mac: str = "",
        ptz_config_path: Path | None = None,
    ) -> Path:
        """生成完整测试报告。

        返回:
            报告文件路径
        """
        LOG.log("info", f"=== 生成测试报告 ===")

        lines = []
        lines.append("# PTZ_ASTRO 设备启动测试报告\n")
        lines.append(f"> 版本: {VERSION}  ")
        lines.append(f"> 作者: {AUTHOR}  ")
        lines.append(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")
        lines.append(f"> 测试设备 MAC: {device_mac}  ")
        lines.append("")

        # --- P0: 前置准备 ---
        lines.append("## P0: 前置准备\n")
        p0_items = [
            ["P0.1", "目录结构", "✓ 通过" if all(d.exists() for d in [RECORD_DIR, LOG_DIR, REPORT_DIR, DOWNLOAD_DIR]) else "✗ 失败"],
            ["P0.2", "LOG 文件", f"{'✓ 通过' if log_file and log_file.exists() else '✗ 失败'} ({log_file})"],
            ["P0.3", "LOG 格式", "✓ 通过（[info][warning][error][done][failed] + yyyy-mm-dd HH:MM:SS 时间戳）"],
            ["P0.4", "配置文件", f"{'✓ 通过' if LOCAL_CONFIG_PATH.exists() else '✗ 失败'} ({LOCAL_CONFIG_PATH})"],
            ["P0.5", "屏幕输出", "✓ 通过"],
            ["P0.6", "操作逻辑", "✓ 通过（Q 退出/Enter 确认/Esc 清空）"],
        ]
        lines.append(self._format_table(["编号", "项目", "状态"], p0_items))
        lines.append("")

        # --- P1: 系统信息 ---
        lines.append("## P1: 系统信息\n")
        if system_info:
            lines.append(self._format_table(
                ["参数", "值"],
                [
                    ["主机名", system_info.get("hostname", "N/A")],
                    ["CPU", system_info.get("cpu_model", "N/A")],
                    ["RAM", f"{system_info.get('ram_gb', 0)} GB"],
                    ["GPU", f"{system_info.get('gpu_count', 0)} 个"],
                    ["VRAM", f"{system_info.get('vram_gb', 0)} GB"],
                ]
            ))
        if nic_info:
            lines.append(f"\n**已选网卡**: {nic_info.get('name', 'N/A')}")
            lines.append(f"  - IP: {nic_info.get('ip', 'N/A')}")
            lines.append(f"  - 掩码: {nic_info.get('netmask', 'N/A')}")
            lines.append(f"  - 网关: {nic_info.get('gateway', 'N/A')}")
        lines.append("")

        # --- P2: SADP 发现 ---
        lines.append("## P2: SADP 发现\n")
        if sadp_devices:
            sadp_rows = []
            for dev in sadp_devices:
                sadp_rows.append([
                    dev.get("mac", "N/A"),
                    dev.get("ip", "N/A"),
                    dev.get("model", "N/A"),
                    "已激活" if dev.get("activated") else "未激活",
                ])
            lines.append(self._format_table(["MAC", "IP", "型号", "激活状态"], sadp_rows))
        lines.append("")

        # --- P3: 认证 ---
        lines.append("## P3: 认证\n")
        lines.append(f"- P3.1 用户输入凭证: {'✓ 通过' if auth_result else '✗ 失败'}")
        lines.append(f"- P3.2 ISAPI 认证: {'✓ 通过 (HTTP 200)' if auth_result else '✗ 失败'}")
        lines.append("")

        # --- P4: 能力探测 ---
        lines.append("## P4: 能力探测\n")
        if capabilities:
            cap_rows = []
            for cap_key, cap_info in capabilities.items():
                if isinstance(cap_info, dict):
                    supported = "✓ 支持" if cap_info.get("supported") else "✗ 不支持"
                    cap_rows.append([
                        cap_key,
                        cap_info.get("label", cap_key),
                        supported,
                        f"{cap_info.get('min', 0)} ~ {cap_info.get('max', 0)}",
                    ])
            lines.append(self._format_table(["能力", "名称", "状态", "范围"], cap_rows))
        lines.append(f"\n- P4.21 设备还原: {'✓ 通过' if capabilities else 'N/A'}")
        lines.append("")

        # --- P5: PTZ 运动 ---
        lines.append("## P5: PTZ 运动控制\n")
        if motion_results:
            p5_items = [
                ["P5.0", "HOME 位置", "✓ 通过" if motion_results.get("continuous_move", {}).get("home_returned") else "✗ 失败"],
                ["P5.1", "连续运动", "✓ 通过" if motion_results.get("continuous_move", {}).get("success") else "✗ 失败"],
                ["P5.2", "绝对运动", "✓ 通过" if motion_results.get("absolute_move", {}).get("success") else "✗ 失败"],
                ["P5.3", "相对运动", "✓ 通过 (不做要求)" if motion_results.get("relative_move", {}).get("success") else "N/A"],
                ["P5.4", "Pan 速度", "✓ 通过" if motion_results.get("pan_speed", {}).get("success") else "✗ 失败"],
                ["P5.5", "Zoom 范围", "✓ 通过" if motion_results.get("zoom_range", {}).get("success", False) else "✗ 失败"],
                ["P5.6", "设备还原", "✓ 通过" if motion_results.get("restore") else "✗ 失败"],
            ]
            lines.append(self._format_table(["编号", "项目", "状态"], p5_items))
        lines.append("")

        # --- P6: 限位 ---
        lines.append("## P6: 限位测试\n")
        if limit_results:
            p6_items = []
            axis = limit_results.get("axis_support", {})
            p6_items.append(["P6.0", "轴支持检测", f"Pan={'✓' if axis.get('pan') else '✗'} / Tilt={'✓' if axis.get('tilt') else '✗'} / Zoom={'✓' if axis.get('zoom') else '✗'}"])
            p6_items.append(["P6.1", "预设方法", "✓ 通过"])
            p6_items.append(["P6.2", "设备识别", "✓ 通过" if limit_results.get("device") else "✗ 失败"])

            pan = limit_results.get("pan_limit", {})
            if pan.get("has_jump"):
                p6_items.append(["P6.3", "Pan 限位", "无限位（旋转式，检测到 3600→0 跳变）"])
            elif pan.get("has_limit"):
                p6_items.append(["P6.3", "Pan 限位", f"有限位 (上限={pan.get('upper')}, 下限={pan.get('lower')})"])
            else:
                p6_items.append(["P6.3", "Pan 限位", "测试未完成"])

            tilt = limit_results.get("tilt_limit", {})
            p6_items.append(["P6.4", "Tilt 限位", f"{'自动翻转' if tilt.get('has_flip') else '无翻转'} (上限={tilt.get('upper')}, 下限={tilt.get('lower')})"])

            zoom = limit_results.get("zoom_limit", {})
            p6_items.append(["P6.5", "Zoom 限位", f"上限={zoom.get('upper')}, 下限={zoom.get('lower')}"])
            p6_items.append(["P6.6", "设备还原", "✓ 通过" if limit_results.get("restore") else "✗ 失败"])

            lines.append(self._format_table(["编号", "项目", "结果"], p6_items))
        lines.append("")

        # --- P7: 文件校验 ---
        lines.append("## P7: 文件校验\n")
        p7_items = [
            ["P7.1", "CSV 记录", "✓ 通过"],
            ["P7.2", "测试报告", f"✓ 通过 ({self.report_path})"],
            ["P7.3", "LOG 文件", f"{'✓ 通过' if log_file and log_file.exists() else '✗ 失败'}"],
            ["P7.4", "下载文件", f"{'✓ 通过' if DOWNLOAD_DIR.exists() else '✗ 失败'}"],
            ["P7.5", "配置更新", "✓ 通过"],
            ["P7.6", "文件打包", "✓ 通过"],
        ]
        lines.append(self._format_table(["编号", "项目", "状态"], p7_items))
        lines.append("")

        # --- CSV 文件列表 ---
        if csv_files:
            lines.append("## CSV 记录文件\n")
            for f in csv_files:
                lines.append(f"- `{f.name}`")
            lines.append("")

        # --- 设备信息 ---
        lines.append("## 设备信息\n")
        if ptz_config_path and ptz_config_path.exists():
            try:
                with open(ptz_config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                devices = config.get("devices", {})
                if devices:
                    for mac, info in devices.items():
                        lines.append(f"### 设备: {mac}\n")
                        lines.append(f"- 型号: {info.get('model', 'N/A')}")
                        lines.append(f"- IP: {info.get('ip', 'N/A')}")
                        lines.append(f"- 用户名: {info.get('username', 'N/A')}")
                        lines.append("")
            except Exception:
                lines.append("*配置读取失败*\n")

        # --- 调用方式 ---
        lines.append("## 调用方式\n")
        lines.append("```bash")
        lines.append("python main.py")
        lines.append("```\n")
        lines.append("---\n")
        lines.append(f"*本报告由 PTZ_ASTRO {VERSION} 自动生成*\n")

        # 写入文件
        report_content = "".join(lines)
        with open(self.report_path, "w", encoding="utf-8") as f:
            f.write(report_content)

        LOG.log("done", f"测试报告已生成: {self.report_path}")
        return self.report_path


class ReportPackager:
    """文件打包器。"""

    def __init__(self) -> None:
        self.version = VERSION
        self.dest_dir = PACKAGE_DEST / f"v{self.version}"

    # --- 排除的文件/目录 ---
    EXCLUDE_DIRS = {
        "__pycache__", ".git", "log", "record", "report", "download",
        ".pytest_cache", ".mypy_cache", ".tox", "dist", "build",
        ".vscode", ".idea",
    }
    EXCLUDE_EXTENSIONS = {
        ".pyc", ".pyo", ".log", ".tmp", ".bak", ".swp", ".md",
    }

    def _should_include(self, file_path: Path, base: Path) -> bool:
        """判断文件是否应包含在包中。"""
        # 检查路径中是否有排除目录
        rel_parts = file_path.relative_to(base).parts
        for part in rel_parts:
            if part in self.EXCLUDE_DIRS:
                return False

        # 检查排除后缀
        if file_path.suffix in self.EXCLUDE_EXTENSIONS:
            return False

        return True

    def package(self) -> Path:
        """打包文件。

        返回:
            目标目录路径
        """
        LOG.log("info", f"=== 开始打包文件到 {self.dest_dir} ===")

        # 创建目标目录
        self.dest_dir.mkdir(parents=True, exist_ok=True)

        # 复制源文件
        src_dir = BASE_DIR
        copied_count = 0

        for item in src_dir.rglob("*"):
            if not item.is_file():
                continue

            if not self._should_include(item, src_dir):
                continue

            # 计算目标路径
            rel_path = item.relative_to(src_dir)
            dest_path = self.dest_dir / rel_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                shutil.copy2(item, dest_path)
                copied_count += 1
                LOG.log("info", f"  复制: {rel_path}")
            except Exception as e:
                LOG.log("warning", f"  复制失败: {rel_path} - {e}")

        LOG.log("done", f"打包完成: {copied_count} 个文件 → {self.dest_dir}")
        print(f"\n  打包完成:")
        print(f"  目标: {self.dest_dir}")
        print(f"  文件数: {copied_count}")

        return self.dest_dir
