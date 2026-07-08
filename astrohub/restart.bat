@echo off
chcp 65001 >nul
title AstroHub 重启脚本

set "PROJECT_PATH=%~dp0"
set "PROJECT_PATH=%PROJECT_PATH:~0,-1%"
where python >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_EXE=python"
) else (
    set "PYTHON_EXE=C:\Python\python.exe"
)

echo ========================================
echo AstroHub v7.98 重启脚本
echo ========================================

echo [STEP 1] 停止现有进程...
powershell -Command "Get-Process python | Where-Object { $_.CommandLine -like '*src.main.main*' } | ForEach-Object { Stop-Process -Id $_.Id -Force }" 2>nul

echo [INFO] 等待端口释放...
timeout /t 2 /nobreak >nul

echo [STEP 2] 启动新进程...
cd /d "%PROJECT_PATH%"
start /B "" "%PYTHON_EXE%" -m src.main.main --headless

echo [INFO] 等待服务启动...
timeout /t 3 /nobreak >nul

REM 打开浏览器
start http://localhost:10280

echo [OK] AstroHub 已重启
timeout /t 2 >nul
