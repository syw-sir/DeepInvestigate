"""
Planner 节点

职责：把用户问题拆解成 3-7 个可执行步骤。
输入：user_query + recalled_memories + retrieved_knowledge
输出：plan（字符串列表） + 一条 AIMessage（让前端看到规划过程）
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ..llm import get_planner_llm
from ..prompts import PLANNER_SYSTEM
from ..state import AgentState

logger = logging.getLogger(__name__)


def _format_context(state: AgentState) -> str:
    """把记忆 + 知识拼成上下文段"""
    parts = []
    memories = state.get("recalled_memories") or []
    if memories:
        parts.append("## 召回的历史经验")
        for i, m in enumerate(memories[:5], 1):
            content = m.get("content") or m.get("summary") or str(m)
            parts.append(f"{i}. {content}")

    knowledge = state.get("retrieved_knowledge") or []
    if knowledge:
        parts.append("\n## 检索到的领域知识")
        for i, k in enumerate(knowledge[:5], 1):
            title = k.get("title", "")
            content = k.get("content", "")[:300]
            parts.append(f"{i}. [{title}] {content}")

    return "\n".join(parts) if parts else ""


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _parse_plan(text: str) -> List[str]:
    """从 LLM 返回中尽力提取 plan 数组"""
    # 1. 整体就是 JSON
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and isinstance(obj.get("plan"), list):
            return [str(x) for x in obj["plan"]]
    except Exception:
        pass

    # 2. 代码块包裹
    m = _JSON_BLOCK_RE.search(text)
    if m:
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict) and isinstance(obj.get("plan"), list):
                return [str(x) for x in obj["plan"]]
        except Exception:
            pass

    # 3. 回退：按行号切
    lines = [
        ln.strip(" -*\t").strip()
        for ln in text.splitlines()
        if ln.strip() and re.match(r"^\s*(\d+[\.\)]|[-*])\s+", ln)
    ]
    return lines if lines else [text.strip()]


async def planner_node(state: AgentState) -> Dict[str, Any]:
    """Planner 节点入口"""
    llm = get_planner_llm(streaming=False)

    user_query = state["user_query"]
    context = _format_context(state)

    user_content = f"## 用户问题\n{user_query}"
    if context:
        user_content += f"\n\n{context}"
    user_content += "\n\n请输出 JSON 格式的步骤计划。"

    messages = [
        SystemMessage(content=PLANNER_SYSTEM),
        HumanMessage(content=user_content),
    ]

    try:
        resp = await llm.ainvoke(messages)
        raw_text = resp.content if hasattr(resp, "content") else str(resp)
        plan = _parse_plan(raw_text)
    except Exception as e:
        logger.exception("planner_node failed")
        plan = [f"直接处理用户问题：{user_query}"]
        raw_text = f"[Planner Error]: {e}"

    # 在 messages 历史中写入一条规划摘要（前端可看到）
    plan_summary = "## 📋 调查计划\n" + "\n".join(
        f"{i+1}. {step}" for i, step in enumerate(plan)
    )

    logger.info("Planner generated %d steps", len(plan))

    return {
        "plan": plan,
        "current_step": 0,
        "messages": [AIMessage(content=plan_summary, name="planner")],
    }
