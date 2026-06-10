"""
LangGraph 流式事件 → OpenAI SSE chunk 适配器 (v3.0)

把 graph.astream_events(version="v2") 的事件流，
转换成前端能消费的 OpenAI 兼容 SSE chunk。

v3.0 新增：
    - config 参数支持（thread_id 等）
    - resume 参数支持（HITL 审批恢复）
    - on_chain_interrupt 事件处理
    - critic 节点可见性
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import AsyncGenerator, Dict, Any

logger = logging.getLogger(__name__)


def _chunk(model: str, delta: Dict[str, Any], finish_reason: str | None = None) -> str:
    payload = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _format_tool_start(tool_name: str, tool_input: Any) -> str:
    args_str = json.dumps(tool_input, ensure_ascii=False) if isinstance(tool_input, dict) else str(tool_input)
    if len(args_str) > 200:
        args_str = args_str[:200] + "..."
    return f"\n\n🔧 **调用工具** `{tool_name}`\n```\n{args_str}\n```\n"


def _format_tool_end(tool_name: str, output: Any) -> str:
    text = output if isinstance(output, str) else str(output)
    if len(text) > 500:
        text = text[:500] + f"\n... [省略 {len(text) - 500} 字符]"
    return f"\n💡 **工具返回** `{tool_name}`:\n```\n{text}\n```\n\n"


def _format_node_start(node_name: str) -> str:
    pretty = {
        "retrieve_memory": "🧠 召回历史记忆",
        "retrieve_knowledge": "📚 检索领域知识",
        "planner": "📋 规划调查步骤",
        "investigator": "🔍 执行调查",
        "reporter": "📝 撰写报告",
        "critic": "🔎 审查报告质量",
        "update_memory": "💾 更新长期记忆",
    }.get(node_name)
    if not pretty:
        return ""
    return f"\n\n---\n### {pretty}\n\n"


_SILENT_LLM_NODES = {"planner"}


async def stream_agent_as_openai_sse(
    graph,
    initial_state: dict | None,
    model: str = "deepseek-chat",
    config: dict | None = None,
    resume: dict | None = None,
) -> AsyncGenerator[str, None]:
    config = config or {"recursion_limit": 30}
    generated_files: list = []
    final_thread_id = ""
    _any_token_sent = False  # 跟踪是否有 on_chat_model_stream token 被发送
    _final_answer = ""  # 从 on_chain_end 捕获 final_answer

    if initial_state:
        final_thread_id = initial_state.get("thread_id", "")
    elif config:
        final_thread_id = config.get("configurable", {}).get("thread_id", "")

    current_node = ""

    try:
        if resume:
            from langgraph.types import Command
            cmd = Command(resume=resume)
            event_stream = graph.astream_events(cmd, config=config, version="v2")
        else:
            event_stream = graph.astream_events(initial_state, config=config, version="v2")

        async for event in event_stream:
            etype = event.get("event")
            ename = event.get("name", "")
            data = event.get("data") or {}
            meta = event.get("metadata") or {}
            node = meta.get("langgraph_node", "")

            if etype == "on_chain_interrupt":
                interrupt_data = data.get("value", data)
                hint = f"\n\n⏸️ **需要人工审批**\n```json\n{json.dumps(interrupt_data, ensure_ascii=False, default=str)}\n```\n"
                yield _chunk(model, {"content": hint})
                continue

            if etype == "on_chain_start" and ename in {
                "retrieve_memory", "retrieve_knowledge", "planner",
                "investigator", "reporter", "update_memory", "critic",
            }:
                if ename != current_node:
                    current_node = ename
                    hint = _format_node_start(ename)
                    if hint:
                        yield _chunk(model, {"content": hint})

            elif etype == "on_chat_model_stream":
                if node in _SILENT_LLM_NODES:
                    continue
                chunk_obj = data.get("chunk")
                if chunk_obj is None:
                    continue
                token = getattr(chunk_obj, "content", "") or ""
                if token:
                    _any_token_sent = True
                    yield _chunk(model, {"content": token})

            elif etype == "on_tool_start":
                tool_input = data.get("input", {})
                hint = _format_tool_start(ename, tool_input)
                yield _chunk(model, {"content": hint})

            elif etype == "on_tool_end":
                output = data.get("output", "")
                if hasattr(output, "content"):
                    output = output.content
                hint = _format_tool_end(ename, output)
                yield _chunk(model, {"content": hint})

            elif etype == "on_chain_end" and ename == "LangGraph":
                output_state = data.get("output") or {}
                generated_files = output_state.get("generated_files") or []
                _final_answer = (output_state.get("final_answer") or "").strip()

    except Exception as e:
        logger.exception("Agent stream failed")
        yield _chunk(model, {"content": f"\n\n❌ Agent 异常：{type(e).__name__}: {e}"})

    # ── 补偿机制：如果流式过程中没有 token 输出（如 chat_responder 使用非流式调用），
    #     则在流结束前把 final_answer 整体发送一次，确保前端始终有内容渲染。
    if not _any_token_sent and _final_answer:
        yield _chunk(model, {"content": _final_answer})

    final_delta: Dict[str, Any] = {"thread_id": final_thread_id}
    if generated_files:
        final_delta["files"] = generated_files
    yield _chunk(model, final_delta, finish_reason="stop")
    yield "data: [DONE]\n\n"
