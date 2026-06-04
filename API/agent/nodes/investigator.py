"""
Investigator 节点

职责：基于 plan，循环调用工具完成调查；完成后输出"中间结论"。

工作流（在 graph.py 中编排）：
    investigator → (有 tool_calls?)
        ├─ 是 → tool_executor → investigator
        └─ 否 → reporter
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ..llm import get_investigator_llm
from ..prompts import INVESTIGATOR_SYSTEM
from ..state import AgentState

# 工具
try:
    from tools.registry import get_all_tools
except ImportError:
    from ...tools.registry import get_all_tools  # type: ignore

logger = logging.getLogger(__name__)


def _build_user_brief(state: AgentState) -> str:
    """首次进入 Investigator 时给的任务简报"""
    plan = state.get("plan") or []
    plan_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(plan))

    parts = [
        "## 用户原始问题",
        state.get("user_query", ""),
        "",
        "## 调查计划",
        plan_text or "（无明确计划，请基于用户问题自由调查）",
    ]

    memories = state.get("recalled_memories") or []
    if memories:
        parts.append("\n## 可参考的历史经验")
        for i, m in enumerate(memories[:3], 1):
            content = m.get("content") or m.get("summary") or str(m)
            parts.append(f"{i}. {content}")

    knowledge = state.get("retrieved_knowledge") or []
    if knowledge:
        parts.append("\n## 可参考的领域知识")
        for i, k in enumerate(knowledge[:3], 1):
            content = (k.get("content") or "")[:300]
            parts.append(f"{i}. {content}")

    parts.append(
        "\n现在开始执行调查。每次只调用一个工具，看到结果后再决定下一步。"
        "全部完成后，输出一段简明的中间结论（不要再调工具）。"
    )
    return "\n".join(parts)


async def investigator_node(state: AgentState) -> Dict[str, Any]:
    """Investigator 节点"""
    tools = get_all_tools()
    llm = get_investigator_llm(streaming=True).bind_tools(tools)

    messages = list(state.get("messages") or [])

    # 首次进入：注入 system + brief
    has_investigator_msg = any(
        isinstance(m, (AIMessage, SystemMessage)) and getattr(m, "name", "") == "investigator"
        for m in messages
    )
    if not has_investigator_msg:
        # 检查是否已经存在 system message
        has_system = any(isinstance(m, SystemMessage) for m in messages)
        prefix = []
        if not has_system:
            prefix.append(SystemMessage(content=INVESTIGATOR_SYSTEM))
        prefix.append(HumanMessage(content=_build_user_brief(state)))
        messages = prefix + messages

    # 调用 LLM
    try:
        resp = await llm.ainvoke(messages)
    except Exception as e:
        logger.exception("investigator LLM call failed")
        return {
            "messages": [AIMessage(content=f"[Investigator Error]: {e}", name="investigator")],
            "error": str(e),
        }

    # 给 AIMessage 标 name 便于追踪（不影响 tool_calls）
    if isinstance(resp, AIMessage) and not getattr(resp, "name", None):
        resp.name = "investigator"

    iteration_count = (state.get("iteration_count") or 0) + 1

    logger.info(
        "Investigator iter=%d, tool_calls=%d",
        iteration_count,
        len(getattr(resp, "tool_calls", []) or []),
    )

    return {
        "messages": [resp],
        "iteration_count": iteration_count,
    }


def route_after_investigator(
    state: AgentState,
) -> Literal["use_tool", "to_reporter"]:
    """条件路由：有 tool_calls 则去执行工具，否则进入 Reporter"""
    # 安全护栏：超过最大轮数强制退出
    max_iter = state.get("max_iterations") or 15
    cur_iter = state.get("iteration_count") or 0
    if cur_iter >= max_iter:
        logger.warning("Max iterations reached (%d), force to reporter", max_iter)
        return "to_reporter"

    messages = state.get("messages") or []
    if not messages:
        return "to_reporter"

    last = messages[-1]
    tool_calls = getattr(last, "tool_calls", None)
    if tool_calls:
        return "use_tool"
    return "to_reporter"
