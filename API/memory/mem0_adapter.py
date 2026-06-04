"""
Mem0 适配器（可选）

Mem0 提供"从对话中智能抽取/合并/去重记忆"的高级能力，
本模块只是一层薄封装，不强依赖：mem0 未装时优雅降级，
直接走我们自己的 episodic_memory（按对话末尾消息抽取）。

启用 mem0：
    pip install mem0ai
    然后调用 mem0_extract_and_save() 时会自动使用
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_MEM0_AVAILABLE = False
_mem0_instance = None


def _try_init_mem0():
    """懒加载 Mem0；任何失败都降级"""
    global _MEM0_AVAILABLE, _mem0_instance
    if _mem0_instance is not None:
        return _mem0_instance
    try:
        from mem0 import Memory  # type: ignore

        try:
            from config_deepseek import (
                REDIS_HOST, REDIS_PORT, REDIS_PASSWORD,
                EMBEDDER_MODEL, EMBEDDER_DEVICE,
                API_BASE, API_KEY, MODEL_PATH,
            )
        except ImportError:
            from ..config_deepseek import (  # type: ignore
                REDIS_HOST, REDIS_PORT, REDIS_PASSWORD,
                EMBEDDER_MODEL, EMBEDDER_DEVICE,
                API_BASE, API_KEY, MODEL_PATH,
            )

        config = {
            "vector_store": {
                "provider": "redis",
                "config": {
                    "host": REDIS_HOST,
                    "port": REDIS_PORT,
                    "password": REDIS_PASSWORD or None,
                    "collection_name": "mem0_collection",
                },
            },
            "embedder": {
                "provider": "huggingface",
                "config": {"model": EMBEDDER_MODEL},
            },
            "llm": {
                "provider": "openai",
                "config": {
                    "model": MODEL_PATH,
                    "openai_base_url": API_BASE,
                    "api_key": API_KEY,
                },
            },
        }
        _mem0_instance = Memory.from_config(config)
        _MEM0_AVAILABLE = True
        logger.info("Mem0 initialized")
        return _mem0_instance
    except Exception as e:
        logger.info("Mem0 unavailable, fallback to manual extraction: %s", e)
        _MEM0_AVAILABLE = False
        return None


def is_available() -> bool:
    """是否可用"""
    inst = _try_init_mem0()
    return _MEM0_AVAILABLE and inst is not None


def save_messages(user_id: str, messages: List[Dict[str, str]]) -> bool:
    """让 Mem0 自动从对话抽取记忆并保存"""
    inst = _try_init_mem0()
    if not inst:
        return False
    try:
        inst.add(messages, user_id=user_id)
        return True
    except Exception as e:
        logger.warning("mem0.save_messages failed: %s", e)
        return False


def search(user_id: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """通过 Mem0 检索"""
    inst = _try_init_mem0()
    if not inst:
        return []
    try:
        res = inst.search(query=query, user_id=user_id, limit=limit)
        # mem0 返回结构：{"results": [{"memory": "...", "score": 0.x}, ...]}
        if isinstance(res, dict):
            res = res.get("results") or []
        out = []
        for r in res:
            if isinstance(r, dict):
                out.append({
                    "content": r.get("memory") or r.get("content") or str(r),
                    "score": r.get("score"),
                    "source": "mem0",
                })
        return out
    except Exception as e:
        logger.warning("mem0.search failed: %s", e)
        return []
