#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
src/scripts/stop_server.py - Cross-platform AstroHub server stopper

Usage:
    python -m src.scripts.stop_server [--port PORT] [--force]
"""

import argparse
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))


def main() -> int:
    from src.core.service_manager import ServiceManager
    
    port = 8000
    
    parser = argparse.ArgumentParser(description="停止 AstroHub 服务端")
    parser.add_argument("--port", type=int, default=port, help=f"端口 (default: {port})")
    parser.add_argument("--force", action="store_true", default=False, help="强制停止")
    
    args = parser.parse_args()
    
    print(f"[停止] AstroHub 服务端 (port: {args.port})")
    
    manager = ServiceManager(
        port=args.port,
        work_dir=project_root,
    )
    result = manager.stop_service(force=args.force)
    print(f"[结果] {result['message']}")
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
