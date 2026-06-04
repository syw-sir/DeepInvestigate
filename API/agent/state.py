"""
LangGraph 状态对象定义

所有节点共享同一份 AgentState，节点返回 dict 进行 partial update。
"""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """DeepInvestigate Agent 全局状态

    字段说明见 docs/DESIGN.md §3.1.1
    """

    # ---- 输入 ----
    user_query: str
    thread_id: str
    user_id: str
    workspace_dir: str

    # ---- 消息历史（LangGraph 自动合并） ----
    messages: Annotated[List[AnyMessage], add_messages]

    # ---- 任务规划（Planner 输出） ----
    plan: Optional[List[str]]
    current_step: int

    # ---- 检索增强（Sprint 4 接入） ----
    retrieved_knowledge: List[Dict[str, Any]]
    recalled_memories: List[Dict[str, Any]]

    # ---- 输出 ----
    final_answer: Optional[str]
    generated_files: List[str]

    # ---- 控制流 ----
    iteration_count: int
    max_iterations: int
    error: Optional[str]

    # ---- v3.0: HITL ----
    hitl_pending: bool
    hitl_tool_name: Optional[str]
    hitl_tool_args: Optional[dict]
    hitl_risk_level: int
    _approval_result: Optional[dict]

    # ---- v3.0: Critic ----
    critic_score: Optional[float]
    critic_feedback: Optional[dict]
    critic_count: int

    # ---- v3.0: Model Router ----
    model_tier: Optional[str]
    fallback_triggered: bool

    # ---- v3.0: Guardrails ----
    guardrail_triggered: bool

    # ---- v3.0: A2A ----
    a2a_messages: List[dict]
    parallel_tasks: Optional[list]


def new_initial_state(
    *,
    user_query: str,
    thread_id: str,
    user_id: str,
    workspace_dir: str,
    max_iterations: int = 15,
) -> AgentState:
    """构造初始状态"""
    return AgentState(
        user_query=user_query,
        thread_id=thread_id,
        user_id=user_id,
        workspace_dir=workspace_dir,
        messages=[],
        plan=None,
        current_step=0,
        retrieved_knowledge=[],
        recalled_memories=[],
        final_answer=None,
        generated_files=[],
        iteration_count=0,
        max_iterations=max_iterations,
        error=None,
        hitl_pending=False,
        hitl_tool_name=None,
        hitl_tool_args=None,
        hitl_risk_level=0,
        _approval_result=None,
        critic_score=None,
        critic_feedback=None,
        critic_count=0,
        model_tier=None,
        fallback_triggered=False,
        guardrail_triggered=False,
        a2a_messages=[],
        parallel_tasks=None,
    )
