"""
Reporter 节点

职责：整合调查过程，输出结构化最终报告。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from ..llm import get_reporter_llm
from ..prompts import REPORTER_SYSTEM
from ..state import AgentState

logger = logging.getLogger(__name__)


def _digest_history(state: AgentState, max_chars: int = 6000) -> str:
    """把调查过程浓缩成给 Reporter 的素材"""
    pieces = []

    pieces.append(f"## 用户原始问题\n{state.get('user_query', '')}")

    plan = state.get("plan") or []
    if plan:
        pieces.append(
            "\n## 调查计划\n" + "\n".join(f"- {s}" for s in plan)
        )

    pieces.append("\n## 调查过程（按顺序）")
    msgs = state.get("messages") or []
    for m in msgs:
        if isinstance(m, AIMessage):
            name = getattr(m, "name", "") or "assistant"
            content = (m.content or "").strip()
            tool_calls = getattr(m, "tool_calls", None) or []
            if tool_calls:
                for tc in tool_calls:
                    args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
                    name_ = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                    pieces.append(f"- [{name}] 调用工具 `{name_}`，参数：{str(args)[:200]}")
            if content and name != "planner":
                pieces.append(f"- [{name}] {content[:500]}")
        elif isinstance(m, ToolMessage):
            content = (m.content or "")
            short = content[:400] + ("..." if len(content) > 400 else "")
            tname = getattr(m, "name", "") or "tool"
            pieces.append(f"- [tool:{tname}] 返回：{short}")

    files = state.get("generated_files") or []
    if files:
        pieces.append("\n## 生成的文件")
        for f in files:
            pieces.append(f"- {f}")

    text = "\n".join(pieces)
    if len(text) > max_chars:
        text = text[: max_chars // 2] + "\n\n...[truncated]...\n\n" + text[-max_chars // 2 :]
    return text


async def reporter_node(state: AgentState) -> Dict[str, Any]:
    """Reporter 节点"""
    llm = get_reporter_llm(streaming=True)

    digest = _digest_history(state)

    messages = [
        SystemMessage(content=REPORTER_SYSTEM),
        HumanMessage(content=digest + "\n\n请基于上述调查记录，撰写最终报告。"),
    ]

    try:
        resp = await llm.ainvoke(messages)
        content = resp.content if hasattr(resp, "content") else str(resp)
    except Exception as e:
        logger.exception("reporter_node failed")
        content = f"[Reporter Error]: {e}\n\n以下是原始调查摘要：\n\n{digest}"

    final_msg = AIMessage(content=content, name="reporter")
    logger.info("Reporter generated final answer (%d chars)", len(content))

    return {
        "messages": [final_msg],
        "final_answer": content,
    }
