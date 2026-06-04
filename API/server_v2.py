"""
DeepInvestigate v3.0 服务器入口

启动方式：
    cd API
    python server_v2.py

v3.0 新增能力：
    - Checkpointing (SQLite) — 会话持久化与恢复
    - HITL (Human-in-the-Loop) — 危险工具人工审批
    - Critic Agent — 报告质量自审查
    - Model Router — 多模型路由与 fallback
    - MCP — 工具标准协议（可选）
    - Guardrails — 输入/输出安全护栏
"""

from __future__ import annotations

import logging
import threading
import time

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config_deepseek import (
    API_HOST,
    API_PORT,
    API_TITLE,
    API_VERSION,
    HTTP_SERVER_PORT,
)
from observability import setup_langsmith
from utils import start_http_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_app_v2() -> FastAPI:
    app = FastAPI(title=f"{API_TITLE} v3", version=f"{API_VERSION}-v3")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from file_api import router as file_router
    from models_api import router as models_router
    from admin_api import router as admin_router

    app.include_router(file_router)
    app.include_router(models_router)
    app.include_router(admin_router)

    from chat_api_v2 import router as chat_router_v2
    app.include_router(chat_router_v2)

    @app.get("/health")
    async def health_check():
        return {
            "status": "healthy",
            "version": "v3.0",
            "timestamp": int(time.time()),
        }

    return app


def main():
    print("=" * 60)
    print(">> DeepInvestigate v3.0 (LangGraph + HITL + Critic)")
    print("=" * 60)
    print(f"  API Server   : http://{API_HOST}:{API_PORT}")
    print(f"  File Server  : http://localhost:{HTTP_SERVER_PORT}")
    print(f"  Health       : GET  /health")
    print(f"  Agent Health : GET  /agent/health")
    print(f"  Chat         : POST /chat/completions")
    print(f"  HITL Resume  : POST /chat/resume")
    print(f"  Thread Hist  : GET  /threads/{{id}}/history")
    print(f"  Usage Stats  : GET  /admin/usage")
    print(f"  Audit Logs   : GET  /admin/audit")

    if setup_langsmith():
        print(f"  LangSmith    : [OK] tracing enabled")
    else:
        print(f"  LangSmith    : [--] disabled")

    print("=" * 60)

    threading.Thread(target=start_http_server, daemon=True).start()

    app = create_app_v2()
    uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="info")


if __name__ == "__main__":
    main()
