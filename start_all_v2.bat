@echo off
chcp 65001 >nul

echo ============================================================
echo  DeepInvestigate v2.0 - LangGraph Multi-Agent
echo ============================================================
echo.

echo [1/3] Starting infrastructure (Redis Stack + ChromaDB)...
docker compose up -d
if errorlevel 1 (
    echo Warning: docker compose failed. Memory/RAG features will be degraded.
)

echo.
echo [2/3] Starting backend (v2 LangGraph)...
start /min cmd /c "cd API && python server_v2.py"

echo Waiting for backend to start...
ping localhost -n 5 >nul

echo.
echo [3/3] Starting frontend...
start /min cmd /c "cd demo\chat\frontend && npm run dev"

echo.
echo ============================================================
echo  All services starting!
echo    - Backend  : http://localhost:8201
echo    - Frontend : http://localhost:4000
echo    - Files    : http://localhost:8101
echo    - Redis UI : http://localhost:8001
echo ============================================================
