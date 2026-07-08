"""
src/core/service_manager.py - Cross-platform service manager

Manages uvicorn service lifecycle with unified API across Windows/Mac/Linux.
Uses Python subprocess only - no OS-specific shell commands.

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import os
import platform
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


class ServiceManager:
    """跨平台服务管理器。
    
    提供统一 API: start_service(), stop_service(), is_running()
    Windows: subprocess.CREATE_NO_WINDOW 不弹窗口
    Mac/Linux: subprocess.Popen + stdout/stderr=DEVNULL
    """
    
    def __init__(
        self,
        module: str = "src.main.main",
        host: str = "0.0.0.0",
        port: int = 8000,
        headless: bool = True,
        work_dir: Path | None = None,
        pid_file: str = "astrohub.pid",
        log_dir: Path | None = None,
    ) -> None:
        self.module = module
        self.host = host
        self.port = port
        self.headless = headless
        self.work_dir = work_dir or Path(__file__).resolve().parent.parent.parent
        self.pid_file = self.work_dir / pid_file
        self.log_dir = log_dir or self.work_dir / "log"
        self.process: subprocess.Popen | None = None
    
    def _platform_kwargs(self) -> dict[str, Any]:
        """Get platform-specific subprocess kwargs."""
        if platform.system() == "Windows":
            return {"creationflags": subprocess.CREATE_NO_WINDOW}
        return {}
    
    def start_service(self) -> dict[str, Any]:
        """Start uvicorn service.
        
        Returns:
            {"success": bool, "pid": int|None, "message": str}
        """
        if self.is_running():
            pid = self._read_pid()
            return {
                "success": False,
                "pid": pid,
                "message": f"服务已在运行 (PID: {pid})",
            }
        
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        args = [
            sys.executable, "-m", self.module,
            "--host", self.host,
            "--port", str(self.port),
        ]
        if self.headless:
            args.append("--headless")
        
        stdout_log = self.log_dir / "server_output.log"
        stderr_log = self.log_dir / "server_err.log"
        
        try:
            stdout_f = open(stdout_log, "a", encoding="utf-8")
            stderr_f = open(stderr_log, "a", encoding="utf-8")
            
            self.process = subprocess.Popen(
                args,
                stdout=stdout_f,
                stderr=stderr_f,
                cwd=str(self.work_dir),
                **self._platform_kwargs(),
            )
            
            # Health check: wait up to 10s for service to respond
            pid = self.process.pid
            self._write_pid(pid)
            
            for i in range(20):
                time.sleep(0.5)
                if self.process.poll() is None and self._is_port_listening():
                    return {
                        "success": True,
                        "pid": pid,
                        "message": f"服务已启动 (PID: {pid})",
                    }
            
            if self.process.poll() is not None:
                return {
                    "success": False,
                    "pid": None,
                    "message": f"服务启动失败 (exit code: {self.process.returncode})",
                }
            
            return {
                "success": True,
                "pid": pid,
                "message": f"服务已启动 (PID: {pid}, 健康检查未响应)",
            }
        
        except Exception as e:
            return {"success": False, "pid": None, "message": f"启动异常: {e}"}
    
    def stop_service(self, force: bool = False) -> dict[str, Any]:
        """Stop uvicorn service.
        
        Args:
            force: If True, use SIGKILL/TASKKILL instead of graceful SIGTERM
            
        Returns:
            {"success": bool, "message": str}
        """
        pid = self._read_pid()
        if pid is None:
            # Try finding by port
            pid = self._find_pid_by_port()
            if pid is None:
                return {"success": False, "message": "服务未在运行"}
        
        if platform.system() == "Windows":
            return self._stop_windows(pid, force)
        return self._stop_unix(pid, force)
    
    def _stop_windows(self, pid: int, force: bool) -> dict[str, Any]:
        """Stop on Windows."""
        try:
            self.process = subprocess.Popen(
                ["taskkill", "/PID", str(pid)] + (["/F"] if force else []),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **self._platform_kwargs(),
            )
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            # Force kill
            self.process.kill()
            self.process.wait(timeout=5)
        except Exception:
            pass
        
        self._remove_pid()
        return {"success": True, "message": f"服务已停止 (PID: {pid})"}
    
    def _stop_unix(self, pid: int, force: bool) -> dict[str, Any]:
        """Stop on Mac/Linux."""
        try:
            sig = signal.SIGKILL if force else signal.SIGTERM
            os.kill(pid, sig)
            
            for _ in range(20):
                time.sleep(0.25)
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    self._remove_pid()
                    return {"success": True, "message": f"服务已停止 (PID: {pid})"}
            
            if force:
                os.kill(pid, signal.SIGKILL)
                time.sleep(1)
        except ProcessLookupError:
            pass
        except Exception as e:
            return {"success": False, "message": f"停止异常: {e}"}
        
        self._remove_pid()
        return {"success": True, "message": f"服务已停止 (PID: {pid})"}
    
    def is_running(self) -> bool:
        """Check if service is running."""
        pid = self._read_pid()
        if pid is None:
            return False
        return self._is_process_alive(pid)
    
    def _is_process_alive(self, pid: int) -> bool:
        """Check if process is alive."""
        if platform.system() == "Windows":
            try:
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                    capture_output=True, text=True,
                    **self._platform_kwargs(),
                )
                return str(pid) in result.stdout
            except Exception:
                return False
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except Exception:
            return False
    
    def _is_port_listening(self) -> bool:
        """Check if port is listening."""
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(("127.0.0.1", self.port))
            sock.close()
            return result == 0
        except Exception:
            return False
    
    def _find_pid_by_port(self) -> int | None:
        """Find PID by port."""
        try:
            if platform.system() == "Windows":
                result = subprocess.run(
                    ["netstat", "-ano"],
                    capture_output=True, text=True,
                    **self._platform_kwargs(),
                )
                for line in result.stdout.splitlines():
                    if f":{self.port}" in line and "LISTENING" in line:
                        parts = line.strip().split()
                        if parts:
                            return int(parts[-1])
            else:
                result = subprocess.run(
                    ["lsof", "-ti", f":{self.port}"],
                    capture_output=True, text=True,
                )
                if result.stdout.strip():
                    return int(result.stdout.strip().split()[0])
        except Exception:
            pass
        return None
