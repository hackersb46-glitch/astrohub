@echo off
chcp 65001 >nul
title AstroHub 停止脚本

echo ========================================
echo AstroHub 停止脚本
echo ========================================

REM 查找并终止所有 AstroHub 进程
echo [INFO] 查找 AstroHub 进程...

powershell -Command "Get-Process python | Where-Object { $_.CommandLine -like '*src.main.main*' } | ForEach-Object { Stop-Process -Id $_.Id -Force }"

echo [INFO] 等待端口释放...
timeout /t 2 /nobreak >nul

REM 验证是否已停止
netstat -ano | findstr ":10280" >nul
if %errorlevel% equ 0 (
    echo [WARN] 仍有进程占用端口 10280
    echo [INFO] 尝试强制终止...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr :10280 ^| findstr LISTENING') do (
        taskkill /F /PID %%a >nul 2>&1
    )
)

echo [OK] AstroHub 已停止
timeout /t 2 >nul
