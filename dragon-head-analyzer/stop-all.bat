@echo off
chcp 65001 >nul

echo ========================================
echo   🐉 龙头战法分析系统 - 停止中...
echo ========================================
echo.

REM 停止后端窗口
echo [1/2] 停止后端...
taskkill /FI "WINDOWTITLE eq 后端-龙头战法" /F >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
    echo     已停止后端进程 %%a
)

REM 停止前端窗口
echo [2/2] 停止前端...
taskkill /FI "WINDOWTITLE eq 前端-龙头战法" /F >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000" ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
    echo     已停止前端进程 %%a
)

REM 清理残留的 node/python 进程（仅本项目）
for /f "tokens=2" %%a in ('wmic process where "commandline like '%%uvicorn%%app.main%%'" get processid 2^>nul ^| findstr /r "[0-9]"') do (
    taskkill /PID %%a /F >nul 2>&1
)

echo.
echo ========================================
echo   ✅ 所有服务已停止
echo ========================================
echo.
pause
