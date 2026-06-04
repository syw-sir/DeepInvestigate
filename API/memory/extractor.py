"""
记忆抽取器

职责：从一次完整调查的 LangGraph state 中，抽取"值得记住"的内容写入 episodic_memory。

策略（优先级从高到低）：
    1. 若 Mem0 可用 → 委托给 Mem0
    2. 否则用 LLM 生成一段简短的"调查摘要"作为记忆 content
    3. LLM 失败兜底：拼接 user_query + final_answer 头部
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, ToolMessage

from . import episodic_memory, mem0_adapter, semantic_memory

logger = logging.getLogger(__name__)


def _digest_for_memory(state: Dict[str, Any], max_chars: int = 2000) -> str:
    """把 state 凝练成一段话，供入库"""
    user_q = state.get("user_query", "")
    final = state.get("final_answer") or ""
    plan = state.get("plan") or []

    parts = [f"问题：{user_q}"]
    if plan:
        parts.append("步骤：" + " → ".join(plan[:5]))

    # 提取关键工具结果
    tool_summaries = []
    msgs = state.get("messages") or []
    for m in msgs:
        if isinstance(m, ToolMessage):
            content = m.content if isinstance(m.content, str) else str(m.content)
            tname = getattr(m, "name", "") or "tool"
            short = content[:150].replace("\n", " ")
            tool_summaries.append(f"[{tname}] {short}")
    if tool_summaries:
        parts.append("工具关键输出（前 3 条）：" + " | ".join(tool_summaries[:3]))

    if final:
        parts.append("结论：" + final[:600])

    text = "\n".join(parts)
    return text[:max_chars]


def _extract_tags(text: str) -> List[str]:
    """从文本中粗暴抽取候选 tag（关键词）"""
    candidates = [
        "ssh", "brute_force", "暴力破解", "rdp", "异常登录", "横向移动",
        "提权", "勒索", "钓鱼", "恶意进程", "可疑外联", "数据泄露",
        "cve", "0day", "webshell", "sql注入", "xss", "ddos",
    ]
    lower = text.lower()
    return [c for c in candidates if c.lower() in lower][:5]


def extract_and_save(state: Dict[str, Any]) -> Optional[str]:
    """从 state 抽取并写入情景记忆，返回记忆 id 或 None"""
    user_id = state.get("user_id") or "anonymous"
    thread_id = state.get("thread_id") or ""

    # 路径 1: Mem0
    if mem0_adapter.is_available():
        # Mem0 接受标准 messages 格式
        oai_msgs = []
        for m in state.get("messages") or []:
            if isinstance(m, AIMessage):
                content = m.content if isinstance(m.content, str) else str(m.content)
                if content.strip():
                    oai_msgs.append({"role": "assistant", "content": content})
            elif isinstance(m, ToolMessage):
                pass  # mem0 不需要 tool 消息
        # 加上原始问题
        oai_msgs.insert(0, {"role": "user", "content": state.get("user_query", "")})
        if oai_msgs and mem0_adapter.save_messages(user_id, oai_msgs):
            logger.info("Memory saved via Mem0 (user=%s)", user_id)
            # 更新画像
            try:
                semantic_memory.increment_investigation(user_id)
            except Exception:
                pass
            return "mem0"

    # 路径 2: 自己抽取 + 写入 episodic
    digest = _digest_for_memory(state)
    if not digest.strip():
        return None

    try:
        from rag.embedder import get_embedder
        emb = get_embedder()
        vec = emb.encode_one(digest)
    except Exception as e:
        logger.warning("embedder failed in extractor: %s", e)
        return None

    tags = _extract_tags(digest)
    mem_id = episodic_memory.add(
        user_id=user_id,
        content=digest,
        embedding=vec,
        tags=tags,
        thread_id=thread_id,
    )

    # 更新语义记忆统计
    try:
        semantic_memory.increment_investigation(user_id)
    except Exception:
        pass

    if mem_id:
        logger.info("Episodic memory saved: %s (tags=%s)", mem_id, tags)
    return mem_id
