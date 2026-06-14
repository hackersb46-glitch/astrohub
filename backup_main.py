#!/usr/bin/env python
"""
Backup current main.py before switching to official SDK approach
"""
import shutil
from pathlib import Path

src = Path("D:/py_app/astro_hub/src/main/main.py")
backup = Path("D:/py_app/astro_hub/src/main/main.py.proxy_backup")

if src.exists():
    shutil.copy2(src, backup)
    print(f"Backed up: {src} -> {backup}")
else:
    print(f"Source not found: {src}")