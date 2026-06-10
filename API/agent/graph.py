"""
LangGraph 主流程组装 (v3.0)

完整流程：
    START
      → retrieve_memory       (召回长期记忆)
      → retrieve_knowledge    (RAG 检索)
      → planner               (拆解步骤)
      → investigator          (调查执行)
        ├── human_approval    (HITL: interrupt_before)
        ├── tool_executor → investigator
        └── reporter
      → critic                (★ v3.0: 自审查)
        ├── pass → update_memory
        └── fail → investigator (回退, 最多 2 次)
      → update_memory         (写入记忆)
      → END
"""

from __future__ import annotations

import json as _json
import logging
import os
import aiosqlite

from langchain_core.messages import SystemMessage as _SystemMessage, HumanMessage as _HumanMessage
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from .state import AgentState
from .llm import get_planner_llm
from .nodes import (
    planner_node,
    investigator_node,
    route_after_investigator,
    reporter_node,
    retrieve_memory_node,
    update_memory_node,
    retrieve_knowledge_node,
)

try:
    from tools.registry import get_all_tools
except ImportError:
    from ..tools.registry import get_all_tools  # type: ignore

logger = logging.getLogger(__name__)

CHECKPOINT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "..", "data", "checkpoints.db"
)
CHECKPOINT_DB_PATH = os.path.normpath(CHECKPOINT_DB_PATH)


async def _get_checkpointer() -> AsyncSqliteSaver:
    os.makedirs(os.path.dirname(CHECKPOINT_DB_PATH), exist_ok=True)
    conn = await aiosqlite.connect(CHECKPOINT_DB_PATH)
    return AsyncSqliteSaver(conn)


def _get_tool_node():
    try:
        from config_deepseek import config as raw_config
    except ImportError:
        from ..config_deepseek import config as raw_config  # type: ignore
    mcp_cfg = (raw_config.get("mcp") or {})
    if mcp_cfg.get("enabled"):
        try:
            from mcp.client_node import mcp_tool_executor
            return mcp_tool_executor
        except ImportError:
            logger.warning("MCP enabled but client_node not found, falling back to direct")
    return ToolNode(get_all_tools())


# ---- HITL ----

TOOL_RISK_LEVELS = {
    "rag_search":      0,
    "recall_memory":   0,
    "list_files":      0,
    "read_file":       0,
    "run_python":      1,
    "write_file":      1,
    "web_search":      1,
    "query_logs":      2,
    "search_cve":      2,
    # v4.0 取证工具
    "collect_system_info":  0,
    "scan_processes":       1,
    "check_network":        1,
    "check_startup":        1,
    "check_file_integrity": 1,
    "check_defender_logs":  1,
    "audit_logins":         2,
    "scan_registry":        2,
    # v4.1 处置工具（全部 Level 3 - 必须 HITL 审批）
    "kill_process":         3,
    "quarantine_file":      3,
    "block_ip":             3,
    "remove_startup":       3,
    "repair_registry":      3,
    "rollback_action":      2,
}


def _human_approval_node(state: AgentState) -> dict:
    from langgraph.types import interrupt as lg_interrupt

    approval = state.get("_approval_result")
    if approval is not None:
        if approval.get("approved"):
            return {}
        return {
            "_approval_result": approval,
            "messages": [{
                "role": "assistant",
                "content": f"操作已被用户拒绝: {approval.get('tool_name', 'unknown')}",
                "name": "investigator",
            }],
        }

    messages = state.get("messages") or []
    if not messages:
        return {}

    last = messages[-1]
    tool_calls = getattr(last, "tool_calls", None)
    if not tool_calls:
        return {}

    first_tc = tool_calls[0]
    tool_name = first_tc.get("name", "") if isinstance(first_tc, dict) else getattr(first_tc, "name", "")
    tool_args = first_tc.get("args", {}) if isinstance(first_tc, dict) else getattr(first_tc, "args", {})
    risk = TOOL_RISK_LEVELS.get(tool_name, 0)

    # ★ 仅风险等级 >= 3 的处置工具触发 HITL 审批
    # 等级 0-2（纯读取 / 安全查询 / 文件写入）自动放行，确保调查流程不被频繁打断
    if risk < 3:
        return {}

    # Level 3: 强制每次审批，不支持会话级别信任
    require_per_call = (risk >= 3)

    result = lg_interrupt({
        "tool_name": tool_name,
        "tool_args": tool_args,
        "risk_level": risk,
        "require_per_call": require_per_call,
        "message": f"Agent 请求调用 {tool_name}（风险等级 {risk}/3{' - 每次必须确认' if require_per_call else ''}）",
    })

    if isinstance(result, dict) and result.get("approved"):
        return {"_approval_result": result}

    return {
        "_approval_result": result if isinstance(result, dict) else {"approved": False},
        "messages": [{
            "role": "assistant",
            "content": f"操作已被用户拒绝: {tool_name}",
            "name": "investigator",
        }],
    }


def _route_after_approval(state: AgentState) -> str:
    approval = state.get("_approval_result")
    if approval is not None and not approval.get("approved"):
        return "skip"

    messages = state.get("messages") or []
    if not messages:
        return "to_reporter"

    last = messages[-1]
    tool_calls = getattr(last, "tool_calls", None)
    if not tool_calls:
        return "to_reporter"

    max_iter = state.get("max_iterations") or 15
    cur_iter = state.get("iteration_count") or 0
    if cur_iter >= max_iter:
        return "to_reporter"

    return "execute"


# ---- Critic ----

CRITIC_SYSTEM = """你是 **DeepInvestigate-Critic**，一位严格的安全报告质量审查员。

## 审查维度（每项 1-5 分）
1. **事实准确性**：报告中的结论是否有工具输出/日志证据支撑？有无凭空捏造？
2. **逻辑完整性**：调查过程是否覆盖了所有计划步骤？有无遗漏关键环节？
3. **证据充分性** (v4.0)：每个威胁结论是否有至少一个取证工具输出作为证据？报告中的 IP/PID/文件路径是否能在工具输出中找到原始记录？
4. **关键信息缺失**：是否遗漏了重要的攻击指标（IP、时间、漏洞编号、MITRE 技战术）？
5. **建议可行性**：处置建议是否具体、可操作？是否包含具体命令或操作步骤？还是泛泛而谈？
6. **处置安全性** (v4.1)：处置操作是否在安全白名单内？有无误杀风险？是否保护了系统关键进程？
7. **处置完整性** (v4.1)：是否覆盖了所有发现的威胁指标？有无遗漏？每个处置操作是否记录了回滚 ID？

## 特别审查项 (v4.0 + v4.1)
- 报告中的 IP/PID/文件路径是否能在工具输出中找到原始记录？
- 威胁判定是否有 MITRE ATT&CK 技战术映射？
- 风险评分是否有评分依据说明？
- 处置操作是否有对应的回滚 ID？是否可逆？
- 处置目标是否避开了系统白名单（System32、关键服务等）？

## 输出格式（严格 JSON）
{
  "scores": {
    "factual_accuracy": 4,
    "logical_completeness": 3,
    "evidence_sufficiency": 4,
    "info_completeness": 4,
    "actionability": 5,
    "remediation_safety": 4,
    "remediation_completeness": 4
  },
  "overall": 4,
  "issues": ["未验证 IP 1.2.3.4 的地理位置", "缺少 MITRE ATT&CK 映射"],
  "suggestions": ["请补充 IP 归属地查询", "建议增加攻击技术映射"]
}

## 评分标准
- overall >= 4: 通过，报告质量合格
- overall < 4: 不通过，需回退补充调查
"""


async def _critic_node(state: AgentState) -> dict:
    try:
        from .llm import get_critic_llm
    except ImportError:
        from ..agent.llm import get_critic_llm  # type: ignore

    llm = get_critic_llm(temperature=0.2)

    final_answer = state.get("final_answer") or ""
    messages = state.get("messages") or []

    recent = messages[-20:]
    summary_parts = []
    for m in recent:
        content = getattr(m, "content", "") or ""
        if isinstance(content, str) and len(content) > 200:
            content = content[:200] + "..."
        summary_parts.append(str(content))
    summary = "\n".join(summary_parts[-10:])

    context = f"""## 待审查报告
{final_answer[:4000]}

## 调查过程摘要
{summary}
"""
    try:
        resp = await llm.ainvoke([
            _SystemMessage(content=CRITIC_SYSTEM),
            _HumanMessage(content=context),
        ])
    except Exception as e:
        logger.warning("Critic LLM call failed: %s", e)
        return {"critic_score": 4, "critic_feedback": {}, "critic_count": (state.get("critic_count") or 0) + 1}

    content = resp.content if hasattr(resp, "content") else str(resp)
    try:
        json_str = content
        if "```" in json_str:
            json_str = json_str.split("```")[1]
            if json_str.startswith("json"):
                json_str = json_str[4:]
        review = _json.loads(json_str.strip())
    except (_json.JSONDecodeError, IndexError):
        review = {"overall": 4, "issues": [], "suggestions": []}

    overall = review.get("overall", 4)
    critic_count = (state.get("critic_count") or 0) + 1

    logger.info("Critic score=%s, retry=%d", overall, critic_count)

    return {
        "critic_score": overall,
        "critic_feedback": review,
        "critic_count": critic_count,
    }


def _route_after_critic(state: AgentState) -> str:
    score = state.get("critic_score", 5)
    retries = state.get("critic_count", 0)
    if score >= 4 or retries >= 2:
        return "pass"
    return "retry"


# ---- Graph Assembly ----

# 闲聊检测关键词 - 用户消息中包含这些词时直接走闲聊应答
_CHAT_QUESTION_PATTERNS = [
    "你能做什么", "你能帮我", "你是谁", "你好", "嗨", "hello", "hi",
    "介绍一下自己", "你叫什么", "你是什么", "你有哪些功能", "功能列表",
    "帮帮我", "怎么用", "使用说明", "help", "what can you do",
]


def _is_chat_question(query: str) -> bool:
    """从用户查询快速判断是否为闲聊/介绍类问题"""
    q = query.strip().lower()
    return any(pattern in q for pattern in _CHAT_QUESTION_PATTERNS)


def _route_from_start(state: AgentState) -> str:
    """入口路由：闲聊问题跳过流水线，直接应答"""
    user_query = state.get("user_query") or ""
    if _is_chat_question(user_query):
        return "chat_responder"
    return "retrieve_memory"


async def chat_responder_node(state: AgentState) -> dict:
    """闲聊应答节点 - 直接调用 LLM 生成回复，绕过调查流水线"""
    from langchain_core.messages import HumanMessage, SystemMessage

    # 使用非流式调用，确保快速响应；SSE 适配器会在流结束时补发 final_answer
    llm = get_planner_llm(streaming=False)
    user_query = state.get("user_query", "")

    chat_system = """你是 DeepInvestigate，一个智能安全调查助手。

你可以帮助用户：
- 🔍 **主机安全取证**：扫描进程、网络连接、启动项、注册表等
- 🛡️ **威胁分析**：分析日志、识别恶意软件、检测入侵
- 🛠️ **安全处置**：终止恶意进程、隔离文件、封禁可疑IP
- 📊 **安全报告**：生成结构化的安全调查报告
- 💡 **安全咨询**：回答安全相关问题

请用友好、简洁的方式回答。如果是简单问候，简短回复即可。"""

    messages = [
        SystemMessage(content=chat_system),
        HumanMessage(content=user_query),
    ]

    try:
        resp = await llm.ainvoke(messages)
        content = resp.content if hasattr(resp, "content") else str(resp)
    except Exception as e:
        logger.exception("chat_responder_node failed")
        content = "你好！我是 DeepInvestigate 安全调查助手。我可以帮你进行主机取证、威胁分析、安全处置等工作。有什么需要调查的吗？"

    logger.info("Chat responder replied (%d chars)", len(content))

    return {
        "messages": [{"role": "assistant", "content": content, "name": "chat_responder"}],
        "final_answer": content,
    }


async def build_graph():
    g = StateGraph(AgentState)

    # 节点
    g.add_node("retrieve_memory", retrieve_memory_node)
    g.add_node("retrieve_knowledge", retrieve_knowledge_node)
    g.add_node("planner", planner_node)
    g.add_node("chat_responder", chat_responder_node)
    g.add_node("investigator", investigator_node)
    g.add_node("human_approval", _human_approval_node)
    g.add_node("tool_executor", _get_tool_node())
    g.add_node("reporter", reporter_node)
    g.add_node("critic", _critic_node)
    g.add_node("update_memory", update_memory_node)

    # 边
    # START → 闲聊检测 → 直接应答 or 进入调查流水线
    g.add_conditional_edges(
        START,
        _route_from_start,
        {"chat_responder": "chat_responder", "retrieve_memory": "retrieve_memory"},
    )
    g.add_edge("retrieve_memory", "retrieve_knowledge")
    g.add_edge("retrieve_knowledge", "planner")
    g.add_edge("planner", "investigator")
    g.add_edge("chat_responder", END)

    # Investigator → human_approval → tool_executor / reporter
    g.add_edge("investigator", "human_approval")
    g.add_conditional_edges(
        "human_approval",
        _route_after_approval,
        {"execute": "tool_executor", "skip": "investigator", "to_reporter": "reporter"},
    )
    g.add_edge("tool_executor", "investigator")

    # Reporter → Critic
    g.add_edge("reporter", "critic")
    g.add_conditional_edges(
        "critic",
        _route_after_critic,
        {"pass": "update_memory", "retry": "investigator"},
    )

    g.add_edge("update_memory", END)

    checkpointer = await _get_checkpointer()
    return g.compile(
        checkpointer=checkpointer,
    )


_graph_cache = None


async def get_graph():
    global _graph_cache
    if _graph_cache is None:
        _graph_cache = await build_graph()
        logger.info("LangGraph v3 compiled (checkpointer + HITL + Critic)")
    return _graph_cache
