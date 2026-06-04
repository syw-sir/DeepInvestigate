"""
DeepInvestigate v3.0 Chat API

基于 LangGraph + Multi-Agent + Tool Use + HITL + Checkpointing。
对外保持 OpenAI Chat Completions 协议，前端无需改动。

v3.0 新增：
    - session_id 会话恢复（Checkpointing）
    - /chat/resume HITL 审批恢复
    - /threads/{id}/history 时间旅行
    - /threads/{id}/state 状态查询
    - /admin/usage 成本追踪
    - /admin/audit 护栏审计
    - InputGuard 输入护栏
"""

from __future__ import annotations

import json
import logging
import random
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

from agent import (
    get_graph,
    new_initial_state,
    stream_agent_as_openai_sse,
    run_agent_sync,
)
from tools.context import ToolContext, set_context
from utils import get_thread_workspace, _normalize_openai_message_content

try:
    from config_deepseek import (
        DEFAULT_MODEL,
        DEFAULT_TEMPERATURE,
        MAX_NEW_TOKENS,
        AGENT_MAX_ITERATIONS,
    )
except ImportError:
    from .config_deepseek import (  # type: ignore
        DEFAULT_MODEL,
        DEFAULT_TEMPERATURE,
        MAX_NEW_TOKENS,
        AGENT_MAX_ITERATIONS,
    )

logger = logging.getLogger(__name__)

router = APIRouter()

# ---- v3.0: Guardrails ----
_input_guard = None
_output_guard = None
_audit_logger = None


def _get_input_guard():
    global _input_guard
    if _input_guard is None:
        try:
            from guardrails.input_guard import InputGuard
            _input_guard = InputGuard()
        except ImportError:
            _input_guard = False
    return _input_guard if _input_guard is not False else None


def _get_output_guard():
    global _output_guard
    if _output_guard is None:
        try:
            from guardrails.output_guard import OutputGuard
            _output_guard = OutputGuard()
        except ImportError:
            _output_guard = False
    return _output_guard if _output_guard is not False else None


def _get_audit_logger():
    global _audit_logger
    if _audit_logger is None:
        try:
            from guardrails.audit import AuditLogger, AuditEvent
            from memory.redis_client import get_redis_client
            _audit_logger = AuditLogger(get_redis_client())
        except ImportError:
            _audit_logger = False
    return _audit_logger if _audit_logger is not False else None


# ---- Models ----

class ChatCompletionRequest(BaseModel):
    model: str = DEFAULT_MODEL
    messages: List[Dict[str, Any]]
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int = MAX_NEW_TOKENS
    stream: bool = True
    session_id: Optional[str] = None
    user_id: Optional[str] = Field(default="anonymous")
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None


class ResumeRequest(BaseModel):
    thread_id: str
    approved: bool = True
    approve_all: bool = False
    model: str = DEFAULT_MODEL


# ---- Helpers ----

def _extract_user_query(messages: List[Dict[str, Any]]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return _normalize_openai_message_content(m.get("content", ""))
    return ""


def _make_thread_id(session_id: Optional[str]) -> str:
    if session_id:
        return session_id
    return f"session_{int(time.time())}_{random.randint(10**9, 10**10 - 1)}"


# ---- Main Chat Endpoint ----

@router.post("/chat/completions")
async def chat_completions_v2(request: ChatCompletionRequest):
    user_query = _extract_user_query(request.messages)
    if not user_query:
        raise HTTPException(status_code=400, detail="No user message found")

    # ★ v3.0: Input Guard
    guard = _get_input_guard()
    if guard:
        is_safe, reason = guard.check(user_query)
        if not is_safe:
            audit = _get_audit_logger()
            if audit:
                try:
                    from guardrails.audit import AuditEvent
                except ImportError:
                    pass
                else:
                    audit.log(AuditEvent(
                        timestamp=datetime.now().isoformat(),
                        event_type="input_blocked",
                        user_id=request.user_id or "anonymous",
                        thread_id="",
                        detail=reason or "blocked",
                        original_preview=user_query[:200],
                    ))
            raise HTTPException(status_code=400, detail=f"输入内容不合规: {reason}")

    thread_id = _make_thread_id(request.session_id)
    user_id = request.user_id or "anonymous"
    workspace_dir = get_thread_workspace(thread_id)

    set_context(ToolContext(
        thread_id=thread_id,
        user_id=user_id,
        workspace_dir=workspace_dir,
    ))

    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    # ★ v3.0: Session recovery via Checkpointer
    init_state = None
    if request.session_id:
        try:
            existing = graph.get_state(config)
            if existing and existing.values:
                logger.info("Resuming session %s from checkpoint", thread_id)
        except Exception as e:
            logger.warning("Failed to check existing state: %s", e)

    if init_state is None:
        init_state = new_initial_state(
            user_query=user_query,
            thread_id=thread_id,
            user_id=user_id,
            workspace_dir=workspace_dir,
            max_iterations=AGENT_MAX_ITERATIONS,
        )

    # ---------- 流式 ----------
    if request.stream:
        async def event_stream():
            try:
                async for chunk in stream_agent_as_openai_sse(
                    graph, init_state, model=request.model, config=config
                ):
                    yield chunk
            except Exception as e:
                logger.exception("v3 stream failed")
                err = {
                    "id": "chatcmpl-error",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": request.model,
                    "choices": [{
                        "index": 0,
                        "delta": {"content": f"\n[FATAL]: {e}"},
                        "finish_reason": "error",
                    }],
                }
                yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    # ---------- 非流式 ----------
    final_state = await run_agent_sync(
        user_query=user_query,
        thread_id=thread_id,
        user_id=user_id,
        workspace_dir=workspace_dir,
        max_iterations=AGENT_MAX_ITERATIONS,
    )

    answer = final_state.get("final_answer") or ""

    # ★ v3.0: Output Guard (PII masking)
    out_guard = _get_output_guard()
    if out_guard:
        answer = out_guard.sanitize(answer)

    return JSONResponse({
        "id": f"chatcmpl-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": answer},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "thread_id": thread_id,
        "generated_files": final_state.get("generated_files") or None,
        "critic_score": final_state.get("critic_score"),
    })


# ---- v3.0: HITL Resume ----

@router.post("/chat/resume")
async def resume_chat(request: ResumeRequest):
    graph = get_graph()
    config = {"configurable": {"thread_id": request.thread_id}}

    async def event_stream():
        try:
            async for chunk in stream_agent_as_openai_sse(
                graph, None, model=request.model, config=config,
                resume={"approved": request.approved, "approve_all": request.approve_all}
            ):
                yield chunk
        except Exception as e:
            logger.exception("HITL resume failed")
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---- v3.0: Thread History (Time Travel) ----

@router.get("/threads/{thread_id}/history")
async def get_thread_history(thread_id: str):
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    history = []
    try:
        for checkpoint in graph.get_state_history(config):
            history.append({
                "checkpoint_id": checkpoint.config["configurable"].get("checkpoint_id", ""),
                "metadata": checkpoint.metadata,
                "next_nodes": list(checkpoint.next) if checkpoint.next else [],
            })
    except Exception as e:
        logger.warning("Failed to get history for %s: %s", thread_id, e)

    return {"thread_id": thread_id, "history": history}


@router.get("/threads/{thread_id}/state")
async def get_thread_state(thread_id: str):
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        state = graph.get_state(config)
        if state is None:
            return {"thread_id": thread_id, "has_state": False}
        values = state.values or {}
        return {
            "thread_id": thread_id,
            "has_state": True,
            "next_nodes": list(state.next) if state.next else [],
            "final_answer_preview": (values.get("final_answer") or "")[:500],
            "iteration_count": values.get("iteration_count", 0),
            "critic_score": values.get("critic_score"),
        }
    except Exception as e:
        return {"thread_id": thread_id, "has_state": False, "error": str(e)}


# ---- v3.0: Admin APIs ----

@router.get("/admin/usage")
async def get_usage_stats(days: int = 7):
    try:
        from model_router.cost_tracker import get_cost_tracker
        tracker = get_cost_tracker()
        return tracker.get_daily_stats(days=days)
    except ImportError:
        return {"error": "CostTracker not available"}


@router.get("/admin/audit")
async def get_audit_logs(days: int = 7, event_type: str = ""):
    audit = _get_audit_logger()
    if not audit:
        return {"error": "AuditLogger not available"}
    try:
        logs = audit.query(days=days, event_type=event_type or None)
        return {"logs": logs}
    except Exception as e:
        return {"error": str(e)}


# ---- Health ----

@router.get("/agent/health")
async def agent_health():
    try:
        graph = get_graph()
        nodes = list(graph.get_graph().nodes) if hasattr(graph, 'get_graph') else []
        return {
            "status": "healthy",
            "version": "v3.0",
            "graph_nodes": nodes,
            "modules": {
                "checkpointer": True,
                "hitl": True,
                "critic": True,
                "model_router": True,
            },
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "unhealthy", "error": str(e)},
        )
