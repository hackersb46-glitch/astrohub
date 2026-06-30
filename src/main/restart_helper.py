"""
AstroHub v7.114 - 独立重启辅助脚本
由 restart_astrohub() 以独立进程启动，不依赖父进程生命周期。
职责：等待主进程退出（端口释放）→ 启动新进程。
跨平台，纯 Python 标准库。
"""
import time
import socket
import subprocess
import sys


def wait_port_free(host: str, port: int, timeout: float = 15.0) -> bool:
    """轮询等待端口释放。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect((host, port))
            s.close()
            time.sleep(0.5)
        except (socket.error, OSError):
            return True
    return False


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 10280
    python_exe = sys.argv[3] if len(sys.argv) > 3 else sys.executable
    cwd = sys.argv[4] if len(sys.argv) > 4 else "."

    wait_port_free(host, port)
    
    subprocess.Popen(
        [python_exe, "-m", "src.main.main", "--headless"],
        cwd=cwd,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )


if __name__ == "__main__":
    main()
