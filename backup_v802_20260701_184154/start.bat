@echo off
chcp 65001 >nul
title AstroHub 启动脚本

set "PROJECT_PATH=%~dp0"
set "PROJECT_PATH=%PROJECT_PATH:~0,-1%"
where python >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_EXE=python"
) else (
    set "PYTHON_EXE=C:\Python\python.exe"
)

echo ========================================
echo AstroHub v7.98 启动脚本
echo ========================================

cd /d "%PROJECT_PATH%"

REM 检查是否已有进程运行
netstat -ano | findstr ":10280" >nul
if %errorlevel% equ 0 (
    echo [INFO] AstroHub 已在运行（端口 10280）
    echo [INFO] 如需重启，请运行 restart.bat
    start http://localhost:10280
    timeout /t 2 >nul
    exit /b 0
)

echo [INFO] 启动 AstroHub...
start /B "" "%PYTHON_EXE%" -m src.main.main --headless

echo [INFO] 等待服务启动...
timeout /t 3 /nobreak >nul

REM 打开浏览器
start http://localhost:10280

echo [OK] AstroHub 已启动
echo [OK] 访问地址: http://localhost:10280
timeout /t 2 >nul
