#!/bin/bash

# 启动 DeepAnalyze 服务 (前端 + 后端)
echo "===================================="
echo "启动 DeepAnalyze 服务"
echo "===================================="

# 启动后端服务
echo "启动后端API服务..."
cd "$(dirname "$0")/API" && python3 chat_api_deepseek.py &

# 保存后端进程ID
BACKEND_PID=$!
echo "后端服务启动中 (PID: $BACKEND_PID)..."

# 等待2秒让后端先启动
sleep 2

# 启动前端服务
echo "启动前端服务..."
cd "$(dirname "$0")/demo/chat/frontend" && npm run dev &

# 保存前端进程ID
FRONTEND_PID=$!
echo "前端服务启动中 (PID: $FRONTEND_PID)..."

echo "===================================="
echo "服务启动完成！"
echo "===================================="
