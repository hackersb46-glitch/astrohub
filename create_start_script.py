import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

PROJECT_ROOT = Path(r'D:\astro_py\astro_hub')

start_py = '''#!/usr/bin/env python3
"""
AstroHub - 统一启动入口 (跨平台)
支持: Windows, macOS, Linux

用法:
  python start.py [--port PORT] [--headless] [--stop] [--status]
"""

import os
import sys
import subprocess
import signal
import time
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.resolve()
PID_FILE = PROJECT_ROOT / "astrohub.pid"
LOG_DIR = PROJECT_ROOT / "logs"
DEFAULT_PORT = 10280

def get_platform():
    return sys.platform

def check_python():
    version = sys.version_info
    if version.major < 3 or version.minor < 11:
        print("[错误] 需要 Python 3.11+")
        sys.exit(1)
    print(f"[信息] Python {version.major}.{version.minor}.{version.micro}")

def check_port(port):
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', port))
    sock.close()
    return result != 0

def get_pid():
    if PID_FILE.exists():
        return int(PID_FILE.read_text().strip())
    return None

def is_running():
    pid = get_pid()
    if pid:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            PID_FILE.unlink(missing_ok=True)
    return False

def stop_service():
    pid = get_pid()
    if pid:
        try:
            print(f"[停止] 正在停止服务 (PID: {pid})...")
            os.kill(pid, signal.SIGTERM)
            time.sleep(2)
            try:
                os.kill(pid, signal.SIGKILL)
            except:
                pass
            PID_FILE.unlink(missing_ok=True)
            print("[停止] 服务已停止")
        except OSError:
            print("[警告] 服务未运行")
            PID_FILE.unlink(missing_ok=True)
    else:
        print("[信息] 未找到运行的服务")

def start_service(port, headless=False):
    if is_running():
        print(f"[警告] 服务已运行 (PID: {get_pid()})")
        return
    
    if not check_port(port):
        print(f"[警告] 端口 {port} 已被占用")
        return
    
    LOG_DIR.mkdir(exist_ok=True)
    
    entry_point = "src.m12_integration.main"
    cmd = [
        sys.executable, "-m", entry_point,
        "--host", "0.0.0.0",
        "--port", str(port)
    ]
    
    if headless:
        cmd.append("--headless")
    
    print(f"[启动] AstroHub 服务...")
    print(f"       入口: {entry_point}")
    print(f"       端口: {port}")
    
    log_file = LOG_DIR / "server.log"
    if get_platform() == "win32":
        proc = subprocess.Popen(
            cmd,
            stdout=open(log_file, "w"),
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
            cwd=PROJECT_ROOT
        )
    else:
        proc = subprocess.Popen(
            cmd,
            stdout=open(log_file, "w"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
            cwd=PROJECT_ROOT
        )
    
    PID_FILE.write_text(str(proc.pid))
    time.sleep(3)
    
    if is_running():
        print(f"[成功] 服务已启动 (PID: {proc.pid})")
        print(f"       地址: http://localhost:{port}")
        print(f"       日志: {log_file}")
    else:
        print("[错误] 服务启动失败，检查日志")

def show_status():
    pid = get_pid()
    if pid and is_running():
        print(f"[状态] 服务运行中 (PID: {pid})")
    else:
        print("[状态] 服务未运行")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="AstroHub 启动脚本")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="服务端口")
    parser.add_argument("--headless", action="store_true", help="无界面模式")
    parser.add_argument("--stop", action="store_true", help="停止服务")
    parser.add_argument("--status", action="store_true", help="查看状态")
    
    args = parser.parse_args()
    
    print("=" * 50)
    print("AstroHub")
    print(f"平台: {get_platform()}")
    print("=" * 50)
    
    check_python()
    
    if args.stop:
        stop_service()
    elif args.status:
        show_status()
    else:
        start_service(args.port, args.headless)

if __name__ == "__main__":
    main()
'''

# 写入文件
start_path = PROJECT_ROOT / 'start.py'
with open(start_path, 'w', encoding='utf-8') as f:
    f.write(start_py)

print(f'Created: {start_path}')

# 创建 shell 脚本（macOS/Linux）
shell_sh = '''#!/bin/bash
# AstroHub 启动脚本 (macOS/Linux)

cd "$(dirname "$0")"
python3 start.py "$@"
'''

shell_path = PROJECT_ROOT / 'start.sh'
with open(shell_path, 'w', encoding='utf-8') as f:
    f.write(shell_sh)

print(f'Created: {shell_path}')
print('Done')