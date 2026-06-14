@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ================================================================
REM  AstroHub - 一键启动脚本
REM  功能: 环境自检 → 启动 uvicorn 服务端 → 记录 PID
REM  用法: start.bat [--headless] [--port XXXX]
REM ================================================================

echo.
echo ============================================
echo   AstroHub 启动脚本
echo ============================================
echo.

REM ---- 检查 Python 是否存在 ----
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.11+
    pause
    exit /b 1
)

REM ---- 解析参数 ----
set HEADLESS=
set PORT=8000
for %%a in (%*) do (
    if "%%a"=="--headless" set HEADLESS=--headless
    if "%%a"=="--port" (
        shift
        set PORT=%%a
    )
)

REM ---- 环境自检 ----
echo [1/3] 执行环境自检...
python src\m11_deployment\core\env_verify.py
if %errorlevel% neq 0 (
    echo.
    echo [警告] 环境自检未完全通过，但仍尝试启动...
    echo.
)

REM ---- 创建日志目录 ----
if not exist "logs" mkdir logs

REM ---- 检查是否已在运行 ----
if exist "astrohub.pid" (
    set /p OLD_PID=<astrohub.pid
    tasklist /FI "PID eq !OLD_PID!" 2>nul | find /I "!OLD_PID!" >nul
    if !errorlevel! equ 0 (
        echo [警告] AstroHub 已在运行 (PID: !OLD_PID!)
        echo 如需重新启动，请先运行 stop.bat
        pause
        exit /b 0
    ) else (
        echo [信息] 清理过期 PID 文件
        del astrohub.pid >nul 2>&1
    )
)

REM ---- 端口清理 (Bug-8: 端口 8000 占用检测与清理) ----
echo [1.5/3] 检查端口 %PORT% 占用情况...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    set PORT_PID=%%a
)
if defined PORT_PID (
    echo [警告] 端口 %PORT% 被进程 PID=!PORT_PID! 占用，正在清理...
    taskkill /F /PID !PORT_PID! >nul 2>&1
    timeout /t 2 /nobreak >nul
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
        echo [错误] 端口 %PORT% 仍然被占用，请手动处理
        pause
        exit /b 1
    )
    echo [信息] 端口 %PORT% 已释放
    set PORT_PID=
) else (
    echo [信息] 端口 %PORT% 可用
)

REM ---- 启动 uvicorn ----
echo.
echo [2/3] 启动 AstroHub 服务端 (端口: %PORT%)...

start /B python -m m12_integration.main %HEADLESS% --host 0.0.0.0 --port %PORT% > logs\server_bg.log 2>&1

REM ---- 等待启动完成 ----
echo 等待服务端就绪...
timeout /t 3 /nobreak >nul

REM ---- 获取 PID ----
for /f "tokens=2" %%i in ('tasklist /FI "IMAGENAME eq python.exe" /FO LIST ^| findstr /C:"PID:"') do (
    set LAST_PID=%%i
)

if defined LAST_PID (
    echo !LAST_PID! > astrohub.pid
    echo [信息] 服务端 PID: !LAST_PID!
) else (
    echo [警告] 无法获取服务端 PID
)

REM ---- 验证启动 ----
echo.
echo [3/3] 验证服务端...
timeout /t 2 /nobreak >nul

powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:%PORT%/api/v1/health' -TimeoutSec 5 -UseBasicParsing; if ($r.StatusCode -eq 200) { Write-Host '  健康检查通过!' } } catch { Write-Host '  注意: 健康检查端点未响应，请稍后手动验证' }"

echo.
echo ============================================
echo   AstroHub 已启动
echo   访问: http://localhost:%PORT%
echo   日志: logs\server_bg.log
echo   停止: stop.bat
echo ============================================
echo.

endlocal
