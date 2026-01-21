@echo off
chcp 65001 >nul

echo ====================================
echo 停止 DeepAnalyze 服务 (前端 + 后端)
echo ====================================

rem 停止后端服务 (Python)
echo 停止后端API服务...
taskkill /IM python3.13.exe /F 2>nul
if %errorlevel% equ 0 (
    echo 后端服务已停止
) else (
    echo 后端服务未运行
)

rem 停止前端服务 (Node.js)
echo 停止前端服务...
taskkill /IM node.exe /F 2>nul
if %errorlevel% equ 0 (
    echo 前端服务已停止
) else (
    echo 前端服务未运行
)

echo ====================================
echo 停止完成！
echo ====================================
