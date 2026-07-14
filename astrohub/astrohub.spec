# -*- mode: python ; coding: utf-8 -*-
"""
AstroHub PyInstaller 打包配置文件

用法:
  pyinstaller astrohub.spec

输出:
  dist/AstroHub/AstroHub.exe

打包结构:
  AstroHub.exe          -> 主程序 (含 Python 运行时)
  SDK/hik/              -> 海康设备发现/加密 SDK
  data/                 -> 设备配置/校准数据
  src/web/              -> 前端 HTML/JS/CSS
  _internal/            -> PyInstaller 运行时目录 (自动)
"""

import os
from pathlib import Path

# ================================================================ #
# 项目路径
# ================================================================ #
PROJECT_ROOT = Path(__file__).parent
SRC_DIR = PROJECT_ROOT / 'src'
WEB_DIR = SRC_DIR / 'web'
SDK_DIR = PROJECT_ROOT / 'SDK'
DATA_DIR = PROJECT_ROOT / 'data'

# ================================================================ #
# 入口点
# ================================================================ #
a = Analysis(
    [str(SRC_DIR / 'main' / 'main.py')],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        # 前端文件 (HTML/JS/CSS)
        (str(WEB_DIR), 'src/web'),
        # 海康 SDK DLL
        (str(SDK_DIR / 'hik'), 'SDK/hik'),
        # 默认配置数据
        (str(DATA_DIR), 'data'),
    ],
    hiddenimports=[
        # ---- FastAPI / Uvicorn ----
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets.auto',
        # ---- Starlette ----
        'starlette.responses',
        'starlette.websockets',
        'starlette.staticfiles',
        'starlette.templating',
        # ---- 数据库 ----
        'sqlalchemy.dialects.sqlite',
        'aiosqlite',
        'sqlite3',
        # ---- Web ----
        'jinja2',
        'jinja2.ext',
        'multipart',
        'websockets',
        # ---- 天文/数值 ----
        'numpy',
        'numpy.core._methods',
        'numpy.lib.format',
        'astropy',
        'astropy.coordinates',
        'astropy.time',
        'astropy.units',
        'erfa',
        # ---- 图像 ----
        'cv2',
        'PIL',
        # ---- 系统 ----
        'psutil',
        'win32com',
        'win32com.client',
        'win32com.server',
        # ---- HTTP ----
        'aiohttp',
        'aiohttp.web',
        'requests',
        # ---- 认证 ----
        'jwt',
        'jwt.algorithms',
        # ---- 可选 ----
        'pystray',
        'webview',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[
        # PyInstaller 启动时加载的 hook (可选)
    ],
    excludes=[
        # 排除不需要的包，减小体积
        'matplotlib',
        'scipy',
        'pandas',
        'tkinter',
        'IPython',
        'jupyter',
        'notebook',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# ================================================================ #
# PYZ (Python 字节码压缩包)
# ================================================================ #
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# ================================================================ #
# EXE 配置
# ================================================================ #
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AstroHub',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,      # 无控制台窗口 (桌面模式)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# ================================================================ #
# COLLECT (输出目录)
# ================================================================ #
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AstroHub',
)
