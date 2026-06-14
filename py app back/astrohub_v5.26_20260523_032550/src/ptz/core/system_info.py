"""
PTZ_ASTRO v1.1 - 系统硬件信息检测模块
获取本机 hostname、CPU 型号、RAM 大小、GPU+VRAM 信息。

Author: 雅痞张@南方天文
"""

import platform
import subprocess

from .logger import LOG


def _run_cmd(cmd: str) -> str:
    """执行命令行并返回输出（跨平台）。"""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip()
    except Exception as e:
        LOG.log("warning", f"命令执行失败 {cmd}: {e}")
        return ""


def get_hostname() -> str:
    """获取主机名。"""
    hostname = platform.node() or _run_cmd("hostname")
    LOG.log("info", f"获取主机名: {hostname}")
    return hostname


def get_cpu_model() -> str:
    """获取 CPU 型号。"""
    system = platform.system()

    if system == "Windows":
        # Windows: 使用 wmic
        output = _run_cmd("wmic cpu get name /value")
        # 解析 "Name=AMD Ryzen 7 5700G"
        for line in output.split("\n"):
            if line.startswith("Name="):
                cpu = line.split("=", 1)[1].strip()
                LOG.log("info", f"CPU 型号: {cpu}")
                return cpu

    elif system == "Linux":
        # Linux: 读取 /proc/cpuinfo
        output = _run_cmd("cat /proc/cpuinfo")
        for line in output.split("\n"):
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                LOG.log("info", f"CPU 型号: {cpu}")
                return cpu

    # Fallback
    cpu = platform.processor() or "Unknown CPU"
    LOG.log("warning", f"使用 fallback CPU 信息: {cpu}")
    return cpu


def get_ram_gb() -> int:
    """获取 RAM 大小（GB，向上取整）。"""
    system = platform.system()

    if system == "Windows":
        # Windows: wmic 返回 MB
        output = _run_cmd("wmic ComputerSystem get TotalPhysicalMemory /value")
        for line in output.split("\n"):
            if "TotalPhysicalMemory=" in line:
                try:
                    bytes_val = int(line.split("=", 1)[1].strip())
                    gb = round(bytes_val / (1024 ** 3))
                    LOG.log("info", f"RAM 大小: {gb} GB")
                    return gb
                except (ValueError, IndexError):
                    pass

    elif system == "Linux":
        # Linux: /proc/meminfo
        output = _run_cmd("grep MemTotal /proc/meminfo")
        # "MemTotal:       65789432 kB"
        for line in output.split("\n"):
            if "MemTotal" in line:
                try:
                    kb = int(line.split(":")[1].strip().split()[0])
                    gb = round(kb / (1024 * 1024))
                    LOG.log("info", f"RAM 大小: {gb} GB")
                    return gb
                except (ValueError, IndexError):
                    pass

    # Fallback via psutil
    try:
        import psutil
        ram = round(psutil.virtual_memory().total / (1024 ** 3))
        if ram:
            LOG.log("info", f"RAM 大小 (psutil): {ram} GB")
            return ram
    except ImportError:
        pass

    LOG.log("warning", "无法获取 RAM 大小")
    return 0


def get_gpu_info() -> dict:
    """获取 GPU 信息。返回 {gpu_count, vram_gb, gpu_names}。"""
    system = platform.system()
    gpu_names = []
    gpu_count = 0
    vram_gb = 0

    if system == "Windows":
        # Windows: 使用 nvidia-smi 获取 GPU 信息
        output = _run_cmd("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits")
        if output:
            for line in output.strip().split("\n"):
                if line.strip():
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 2:
                        name = parts[0]
                        try:
                            mem_mb = int(parts[1])
                            vram_gb += round(mem_mb / 1024)
                        except (ValueError, IndexError):
                            pass
                        gpu_names.append(name)
                        gpu_count += 1

    if system == "Linux":
        output = _run_cmd("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits")
        if output:
            for line in output.strip().split("\n"):
                if line.strip():
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 2:
                        name = parts[0]
                        try:
                            mem_mb = int(parts[1])
                            vram_gb += round(mem_mb / 1024)
                        except (ValueError, IndexError):
                            pass
                        gpu_names.append(name)
                        gpu_count += 1

    # Fallback: 尝试 psutil 或 platform
    if gpu_count == 0:
        # 尝试 pywin32 (Windows)
        if system == "Windows":
            output = _run_cmd("wmic path win32_VideoController get name /value")
            for line in output.split("\n"):
                if line.startswith("Name="):
                    name = line.split("=", 1)[1].strip()
                    if name:
                        gpu_names.append(name)
                        gpu_count += 1

    if gpu_count == 0:
        LOG.log("warning", "无法获取 GPU 信息")
    else:
        LOG.log("info", f"GPU 信息: {gpu_count}x GPU, {vram_gb} GB VRAM, {', '.join(gpu_names)}")

    return {
        "gpu_count": gpu_count,
        "vram_gb": vram_gb,
        "gpu_names": gpu_names,
    }


def collect_system_info() -> dict:
    """收集所有系统信息并返回字典。"""
    LOG.log("info", "=== 开始收集系统硬件信息 ===")

    info = {
        "hostname": get_hostname(),
        "cpu_model": get_cpu_model(),
        "ram_gb": get_ram_gb(),
        **get_gpu_info(),
    }

    LOG.log("done", f"系统信息收集完成: {info['hostname']} / {info['cpu_model']} / {info['ram_gb']}GB RAM / {info['gpu_count']}x GPU / {info['vram_gb']}GB VRAM")
    return info
