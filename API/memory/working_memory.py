"""
工作记忆（Working Memory）

短期会话级上下文，TTL 自动衰减（默认 30 分钟）。
存储当前调查任务的摘要、未完成步骤、临时变量等。

Redis Key 设计：
    wm:{thread_id}    String (JSON)   主记忆体
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional

from .redis_client import get_redis_client

try:
    from config_deepseek import WORKING_MEMORY_TTL
except ImportError:
    from ..config_deepseek import WORKING_MEMORY_TTL  # type: ignore

logger = logging.getLogger(__name__)


def _key(thread_id: str) -> str:
    return f"wm:{thread_id}"


def save(thread_id: str, data: Dict[str, Any], ttl: Optional[int] = None) -> bool:
    """覆盖式写入工作记忆"""
    try:
        client = get_redis_client()
        payload = json.dumps(data, ensure_ascii=False, default=str)
        client.setex(_key(thread_id), ttl or WORKING_MEMORY_TTL, payload)
        return True
    except Exception as e:
        logger.warning("working_memory.save failed: %s", e)
        return False


def get(thread_id: str) -> Optional[Dict[str, Any]]:
    """取出工作记忆"""
    try:
        client = get_redis_client()
        raw = client.get(_key(thread_id))
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        return json.loads(raw)
    except Exception as e:
        logger.warning("working_memory.get failed: %s", e)
        return None


def patch(thread_id: str, updates: Dict[str, Any], ttl: Optional[int] = None) -> bool:
    """合并更新（不存在则新建）"""
    cur = get(thread_id) or {}
    cur.update(updates)
    cur["_updated_at"] = int(time.time())
    return save(thread_id, cur, ttl)


def clear(thread_id: str) -> bool:
    """清除工作记忆"""
    try:
        client = get_redis_client()
        client.delete(_key(thread_id))
        return True
    except Exception as e:
        logger.warning("working_memory.clear failed: %s", e)
        return False
