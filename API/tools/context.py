"""
工具运行时上下文

LangChain @tool 装饰的函数只能接受 LLM 提供的参数，
而工具内部经常需要拿到 thread_id / workspace_dir / user_id 等"系统级"信息。

我们用 contextvars 在每次 Agent 调用前注入上下文，工具内部按需读取。
"""

from __future__ import annotations

import os
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional


@dataclass
class ToolContext:
    """工具运行时所需的上下文信息"""
    thread_id: str
    user_id: str
    workspace_dir: str
    # 可扩展：request_id, trace_id, lang, ...


# 全局 ContextVar
_current_ctx: ContextVar[Optional[ToolContext]] = ContextVar(
    "deepinvestigate_tool_ctx", default=None
)


def set_context(ctx: ToolContext) -> None:
    """在 Agent 入口处调用，设置当前请求的工具上下文"""
    _current_ctx.set(ctx)


def get_context() -> ToolContext:
    """工具内部调用，获取上下文。未设置时抛 RuntimeError"""
    ctx = _current_ctx.get()
    if ctx is None:
        raise RuntimeError(
            "ToolContext is not set. Call set_context() before invoking tools."
        )
    return ctx


def get_workspace_dir() -> str:
    """便捷：获取当前 workspace 路径，并确保存在"""
    ws = get_context().workspace_dir
    os.makedirs(ws, exist_ok=True)
    return ws
