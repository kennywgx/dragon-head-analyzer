@echo off
cd /d %~dp0backend
echo 启动龙头战法分析系统后端...
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause
