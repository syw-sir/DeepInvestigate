"""
记忆相关节点（占位 + 平滑接入）

Sprint 3 阶段：节点存在但不连真数据，保证整图可跑。
Sprint 4 阶段：把 TODO 处换成 memory.episodic_memory / mem0 等真实调用。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from ..state import AgentState

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config_deepseek import ENABLE_MEMORY

logger = logging.getLogger(__name__)


async def retrieve_memory_node(state: AgentState) -> Dict[str, Any]:
    """召回长期记忆：情景 + 语义画像 + 程序 SOP，合并返回"""
    if not ENABLE_MEMORY:
        return {"recalled_memories": []}

    user_id = state.get("user_id", "")
    query = state.get("user_query", "")
    memories: list = []

    # 情景记忆：相似历史调查
    try:
        from memory import episodic_memory, semantic_memory, procedural_memory, mem0_adapter

        # 1) 优先尝试 Mem0
        if mem0_adapter.is_available():
            mem0_items = mem0_adapter.search(user_id, query, limit=5)
            for it in mem0_items:
                memories.append({"type": "episodic", "source": "mem0", **it})

        # 2) 自家情景记忆（兜底/补充）
        if not memories:
            for it in episodic_memory.recall(user_id, query, top_k=5):
                memories.append({"type": "episodic", "source": "redis", **it})

        # 3) 语义记忆（用户画像）
        profile = semantic_memory.get_profile(user_id)
        if profile:
            prefs = profile.get("preferences") or []
            stats = profile.get("stats") or {}
            memories.append({
                "type": "semantic",
                "source": "profile",
                "content": (
                    f"用户偏好：{', '.join(prefs) if prefs else '无'}；"
                    f"调查总数：{stats.get('total_investigations', 0)}；"
                    f"技能等级：{profile.get('skill_level', 'unknown')}"
                ),
            })

        # 4) 程序记忆（成功 SOP）
        for it in procedural_memory.recall(query, top_k=2):
            memories.append({
                "type": "procedural",
                "source": "sop",
                "content": f"SOP「{it.get('title','')}」: {it.get('description','')}",
                "steps": it.get("steps", []),
                "score": it.get("score"),
            })

    except Exception as e:
        logger.warning("retrieve_memory failed (downgraded): %s", e)
        memories = []

    logger.info("Recalled %d memories for user=%s", len(memories), user_id)
    return {"recalled_memories": memories}


async def update_memory_node(state: AgentState) -> Dict[str, Any]:
    """调查结束后写入长期记忆"""
    if not ENABLE_MEMORY:
        return {}

    try:
        from memory.extractor import extract_and_save
        mem_id = extract_and_save(dict(state))
        if mem_id:
            logger.info("Memory persisted: %s", mem_id)
    except Exception as e:
        logger.warning("update_memory failed (downgraded): %s", e)

    return {}
