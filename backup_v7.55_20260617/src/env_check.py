"""
AstroHub v2.0 - 环境自检与自动修复

启动前检查环境并自动修复缺失项。
"""

from __future__ import annotations

import warnings
warnings.warn(
    "src/env_check.py is deprecated. Use 'src/deployment/core/health_monitor.py' instead. "
    "Will be removed in a future version.",
    DeprecationWarning,
    stacklevel=2,
)

import platform
import socket
import subprocess
import sys
from pathlib import Path

from src.config import DB_DIR, LOG_DIR, PORT
from src.logger import get_logger

log = get_logger("env_check")

# 最低 Python 版本
MIN_PYTHON = (3, 11)

# 核心依赖清单
CORE_DEPS = [
    "fastapi",
    "uvicorn",
    "sqlalchemy",
    "aiosqlite",
    "pydantic",
    "pywebview",
    "psutil",
    "python-multipart",
    "requests",
]


def _version_tuple(version_str: str) -> tuple[int, ...]:
    """将版本字符串转为元组。"""
    return tuple(int(x) for x in version_str.split(".")[:3])


def check_python_version() -> bool:
    """检查 Python 版本是否满足要求。"""
    current = sys.version_info[:2]
    if current >= MIN_PYTHON:
        log.info(f"Python 版本 {sys.version.split()[0]} >= {'.'.join(map(str, MIN_PYTHON))}")
        return True
    log.error(f"Python 版本 {sys.version.split()[0]} < {'.'.join(map(str, MIN_PYTHON))}")
    return False


def check_dependencies() -> dict[str, bool]:
    """检查核心依赖是否安装。返回值 {包名: 是否已安装}。"""
    results = {}
    for dep in CORE_DEPS:
        try:
            __import__(dep.replace("-", "_"))
            results[dep] = True
            log.debug(f"依赖已安装: {dep}")
        except ModuleNotFoundError:
            results[dep] = False
            log.warning(f"依赖缺失: {dep}")
    return results


def install_dependencies(missing: list[str]) -> bool:
    """自动安装缺失依赖。

    Args:
        missing: 缺失的包名列表。

    Returns:
        安装是否成功。
    """
    if not missing:
        return True
    log.info(f"正在安装缺失依赖: {', '.join(missing)}")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", *missing],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        log.info("依赖安装完成")
        return True
    except subprocess.CalledProcessError as e:
        log.error(f"依赖安装失败: {e}")
        return False


def check_directories() -> list[Path]:
    """检查运行时目录是否存在，不存在则自动创建。

    Returns:
        已创建的目录列表。
    """
    dirs_to_create = [DB_DIR, LOG_DIR, Path(__file__).resolve().parent.parent / "data" / "config"]
    created = []
    for d in dirs_to_create:
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            log.info(f"创建目录: {d}")
            created.append(d)
    return created


def check_dll() -> dict[str, bool]:
    """检查关键 DLL 是否存在（仅 Windows）。

    Returns:
        {DLL名称: 是否存在}
    """
    if platform.system() != "Windows":
        return {}

    dlls_to_check = [
        "ascom.dll",
        "vcruntime140.dll",
    ]

    results = {}
    system_paths = [
        Path("C:/Windows/System32"),
        Path(__file__).resolve().parent.parent / "deps" / "windows",
    ]

    for dll in dlls_to_check:
        found = False
        for path in system_paths:
            if (path / dll).exists():
                found = True
                break
        results[dll] = found
        if not found:
            log.warning(f"DLL 缺失: {dll}")
        else:
            log.debug(f"DLL 存在: {dll}")
    return results


def check_port(port: int | None = None) -> bool:
    """检查端口是否被占用。

    Args:
        port: 要检查的端口，默认使用配置中的端口。

    Returns:
        True = 端口可用，False = 端口被占用。
    """
    check_port = port or PORT
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("0.0.0.0", check_port))
            log.info(f"端口 {check_port} 可用")
            return True
        except OSError:
            log.warning(f"端口 {check_port} 已被占用")
            return False


def run_all_checks(auto_fix: bool = True) -> dict[str, bool]:
    """执行所有环境检查并根据需要自动修复。

    Args:
        auto_fix: 是否启用自动修复。

    Returns:
        检查结果汇总 {检查项: 是否通过}。
    """
    log.info("=== 环境自检开始 ===")
    results = {}

    # 1. Python 版本
    results["python_version"] = check_python_version()

    # 2. 依赖检查 + 自动安装
    deps_results = check_dependencies()
    missing = [dep for dep, installed in deps_results.items() if not installed]
    results["dependencies"] = len(missing) == 0
    if missing and auto_fix:
        install_ok = install_dependencies(missing)
        # 重新检查
        deps_results = check_dependencies()
        results["dependencies"] = all(deps_results.values())
    elif missing:
        log.error(f"缺失依赖（未自动修复）: {', '.join(missing)}")

    # 3. 目录检查 + 自动创建
    created_dirs = check_directories()
    results["directories"] = len(created_dirs) >= 0  # 总是通过（自动创建）

    # 4. DLL 检查（仅 Windows，缺失时提示但不阻塞）
    dll_results = check_dll()
    results["dll"] = all(dll_results.values()) if dll_results else True  # 非 Windows 跳过

    # 5. 端口检查（仅信息性，不阻塞启动）
    results["port"] = check_port()

    passed = sum(1 for v in results.values() if v)
    total = len(results)
    log.info(f"环境自检完成: {passed}/{total} 项通过")

    return results
