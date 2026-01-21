@echo off
chcp 65001 >nul

echo Starting DeepAnalyze services...

echo Starting backend API service...
start /min cmd /c "cd API && python chat_api_deepseek.py"

echo Waiting for backend to start...
ping localhost -n 3 >nul

echo Starting frontend service...
start /min cmd /c "cd demo\chat\frontend && npm run dev"

echo Services started!

