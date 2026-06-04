"""
长期记忆召回工具

Agent 可主动调用，从情景记忆 / 语义记忆 / 程序记忆中检索相关条目。
（Sprint 4 实现四类记忆模块后真正生效，当前为可降级占位实现）
"""

from __future__ import annotations

import json
import logging
from typing import Literal

from langchain_core.tools import tool

from .context import get_context

logger = logging.getLogger(__name__)

MemoryType = Literal["episodic", "semantic", "procedural", "all"]


@tool("recall_memory", parse_docstring=True)
def recall_memory(
    query: str,
    memory_type: MemoryType = "episodic",
    top_k: int = 5,
) -> str:
    """从长期记忆中召回与 query 相关的历史调查经验、用户偏好或成功 SOP。

    记忆分层：
        - episodic   : 情景记忆 - 历史调查事件
        - semantic   : 语义记忆 - 用户画像 / 偏好
        - procedural : 程序记忆 - 成功 SOP
        - all        : 全部类型混合返回

    Args:
        query: 查询语句。
        memory_type: 记忆类型，默认 episodic。
        top_k: 返回条数，默认 5。

    Returns:
        JSON 字符串，包含召回的记忆条目列表。
    """
    try:
        ctx = get_context()
        user_id = ctx.user_id

        try:
            from memory import episodic_memory, semantic_memory, procedural_memory
        except ImportError:
            from ..memory import (  # type: ignore
                episodic_memory, semantic_memory, procedural_memory,
            )

        results: list = []
        if memory_type in ("episodic", "all"):
            for it in episodic_memory.recall(user_id, query, top_k):
                results.append({"type": "episodic", **it})
        if memory_type in ("semantic", "all"):
            profile = semantic_memory.get_profile(user_id)
            if profile:
                results.append({"type": "semantic", "profile": profile})
        if memory_type in ("procedural", "all"):
            for it in procedural_memory.recall(query, top_k):
                results.append({"type": "procedural", **it})

        return json.dumps({"results": results}, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.exception("recall_memory failed")
        return json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False)
