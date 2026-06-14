@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ================================================================
REM  AstroHub - 优雅停止脚本
REM  功能: 读取 PID → 优雅停止 (Ctrl+C) → 强制终止
REM ================================================================

echo.
echo ============================================
echo   AstroHub 停止脚本
echo ============================================
echo.

REM ---- 检查 PID 文件 ----
if not exist "astrohub.pid" (
    echo [信息] 未找到 PID 文件，尝试查找运行中的实例...

    REM 尝试通过端口查找进程
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
        set PORT_PID=%%a
    )

    if defined PORT_PID (
        echo [信息] 找到监听 8000 端口的进程 PID: !PORT_PID!
        echo !PORT_PID! > astrohub.pid
    ) else (
        REM 查找 python 进程
        for /f "tokens=2" %%i in ('tasklist /FI "IMAGENAME eq python.exe" /FO LIST ^| findstr /C:"PID:"') do (
            set PORT_PID=%%i
        )
    )

    if not defined PORT_PID (
        echo [信息] 未找到运行中的 AstroHub 实例
        goto :end
    )
) else (
    set /p PORT_PID=<astrohub.pid
)

echo [信息] 目标进程 PID: !PORT_PID!

REM ---- 检查进程是否存在 ----
tasklist /FI "PID eq !PORT_PID!" 2>nul | find /I "!PORT_PID!" >nul
if %errorlevel% neq 0 (
    echo [信息] 进程 !PORT_PID! 不存在
    del astrohub.pid >nul 2>&1
    goto :end
)

REM ---- 优雅停止 (发送 Ctrl+C 信号) ----
echo [1/2] 正在发送停止信号...

REM wmic 通过 PID 终止进程 (优雅方式)
wmic process where processid=!PORT_PID! call terminate >nul 2>&1

REM 等待进程退出
echo 等待进程退出...
set RETRY=0
:wait_loop
timeout /t 1 /nobreak >nul
tasklist /FI "PID eq !PORT_PID!" 2>nul | find /I "!PORT_PID!" >nul
if %errorlevel% equ 0 (
    set /a RETRY+=1
    if !RETRY! lss 10 (
        echo 等待中... (!RETRY!/10)
        goto :wait_loop
    ) else (
        echo [信息] 优雅停止超时，执行强制终止...
        taskkill /F /PID !PORT_PID! >nul 2>&1
    )
)

REM ---- 清理 ----
echo [2/2] 清理 PID 文件...
if exist "astrohub.pid" del astrohub.pid >nul 2>&1

REM ---- 验证停止 ----
timeout /t 1 /nobreak >nul
netstat -ano | findstr ":8000" | findstr "LISTENING" >nul
if %errorlevel% equ 0 (
    echo [警告] 端口 8000 仍被占用
) else (
    echo [成功] 端口 8000 已释放
)

:end
echo.
echo ============================================
echo   AstroHub 已停止
echo ============================================
echo.

endlocal
