@echo off
cd /d %~dp0frontend
echo 启动前端看板...
call npm install
call npm run dev
pause
