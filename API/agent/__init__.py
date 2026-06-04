"""
DeepInvestigate v2.0 Agent 模块

公共入口：
    - get_graph()                : 获取编译好的 LangGraph
    - new_initial_state(...)     : 构造初始 AgentState
    - stream_agent_as_openai_sse : 流式跑 Agent 并转 OpenAI SSE
    - run_agent_sync             : 非流式跑 Agent
"""

from __future__ import annotations

import logging
from typing import Optional

from .graph import get_graph
from .state import AgentState, new_initial_state
from .sse_adapter import stream_agent_as_openai_sse

logger = logging.getLogger(__name__)


async def run_agent_sync(
    *,
    user_query: str,
    thread_id: str,
    user_id: str,
    workspace_dir: str,
    max_iterations: int = 15,
) -> dict:
    """非流式：跑完整个 Agent，返回最终 state（包含 final_answer / generated_files）"""
    graph = get_graph()
    init = new_initial_state(
        user_query=user_query,
        thread_id=thread_id,
        user_id=user_id,
        workspace_dir=workspace_dir,
        max_iterations=max_iterations,
    )
    final_state = await graph.ainvoke(init, config={"recursion_limit": 25})
    return final_state


__all__ = [
    "get_graph",
    "AgentState",
    "new_initial_state",
    "stream_agent_as_openai_sse",
    "run_agent_sync",
]
