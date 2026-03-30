@echo off
chcp 65001 >nul
title 龙头战法分析系统

echo ========================================
echo   🐉 龙头战法分析系统 - 启动中...
echo ========================================
echo.

REM 检查端口
netstat -ano | findstr ":8000" >nul 2>&1
if %errorlevel%==0 (
    echo [警告] 端口 8000 已被占用，后端可能启动失败
)
netstat -ano | findstr ":3000" >nul 2>&1
if %errorlevel%==0 (
    echo [警告] 端口 3000 已被占用，前端可能启动失败
)
echo.

REM 启动后端（新窗口）
echo [1/2] 启动后端 http://localhost:8000
start "后端-龙头战法" cmd /k "cd /d %~dp0backend && chcp 65001 >nul && pip install -r requirements.txt >nul 2>&1 && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

REM 等3秒让后端先起来
timeout /t 3 /nobreak >nul

REM 启动前端（新窗口）
echo [2/2] 启动前端 http://localhost:3000
start "前端-龙头战法" cmd /k "cd /d %~dp0frontend && chcp 65001 >nul && npm run dev"

echo.
echo ========================================
echo   ✅ 启动完成！
echo   后端: http://localhost:8000
echo   前端: http://localhost:3000
echo   API文档: http://localhost:8000/docs
echo ========================================
echo.
echo 关闭此窗口不会停止服务
echo 请使用 stop-all.bat 停止所有服务
echo.
pause
