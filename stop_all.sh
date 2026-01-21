#!/bin/bash

# 停止 DeepAnalyze 服务 (前端 + 后端)
echo "===================================="
echo "停止 DeepAnalyze 服务"
echo "===================================="

# 停止后端服务 (Python)
echo "停止后端API服务..."
pid=$(pgrep -f "chat_api_deepseek.py")
if [ -n "$pid" ]; then
    echo "停止后端服务 (PID: $pid)..."
    kill $pid
    if [ $? -eq 0 ]; then
        echo "后端服务已成功停止"
    else
        echo "停止后端服务失败，尝试强制停止..."
        kill -9 $pid
        if [ $? -eq 0 ]; then
            echo "后端服务已强制停止"
        else
            echo "强制停止后端服务失败"
        fi
    fi
else
    echo "后端服务未运行"
fi

# 停止前端服务 (Node.js)
echo "停止前端服务..."
pid=$(pgrep -f "npm run dev")
if [ -n "$pid" ]; then
    echo "停止前端服务 (PID: $pid)..."
    kill $pid
    if [ $? -eq 0 ]; then
        echo "前端服务已成功停止"
    else
        echo "停止前端服务失败，尝试强制停止..."
        kill -9 $pid
        if [ $? -eq 0 ]; then
            echo "前端服务已强制停止"
        else
            echo "强制停止前端服务失败"
        fi
    fi
else
    # 尝试查找node进程
    pid=$(pgrep -f "node")
    if [ -n "$pid" ]; then
        echo "停止Node.js进程 (PID: $pid)..."
        kill $pid
        echo "前端服务已停止"
    else
        echo "前端服务未运行"
    fi
fi

echo "===================================="
echo "停止完成！"
echo "===================================="
