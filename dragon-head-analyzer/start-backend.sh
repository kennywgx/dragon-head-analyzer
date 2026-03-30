#!/bin/bash
# 启动后端服务
cd "$(dirname "$0")/backend"
echo "🚀 启动龙头战法分析系统后端..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
