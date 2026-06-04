"""
语义记忆（Semantic Memory）

存储跨会话的稳定知识：用户画像、偏好、确认过的攻击模式等。
基于 RedisJSON。

Redis Key 设计：
    sm:{user_id}    JSON     用户画像

画像结构：
{
    "user_id": "u_001",
    "skill_level": "beginner|intermediate|advanced",
    "preferences": ["关注 SSH", "关注内网横向"],
    "focus_areas": ["auth", "lateral_movement"],
    "confirmed_patterns": ["pattern_001", ...],
    "stats": {
        "total_investigations": 42,
        "last_active": 1716528000
    },
    "_updated_at": 1716528000
}
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from .redis_client import get_redis_client

logger = logging.getLogger(__name__)


def _key(user_id: str) -> str:
    return f"sm:{user_id}"


def _default_profile(user_id: str) -> Dict[str, Any]:
    return {
        "user_id": user_id,
        "skill_level": "intermediate",
        "preferences": [],
        "focus_areas": [],
        "confirmed_patterns": [],
        "stats": {"total_investigations": 0, "last_active": int(time.time())},
        "_updated_at": int(time.time()),
    }


def _has_redisjson() -> bool:
    """检测 RedisJSON 是否可用"""
    try:
        client = get_redis_client()
        client.execute_command("JSON.SET", "_dii_probe_", "$", '"ok"')
        client.delete("_dii_probe_")
        return True
    except Exception:
        return False


def get_profile(user_id: str) -> Optional[Dict[str, Any]]:
    """读取用户画像；首次返回 None"""
    try:
        client = get_redis_client()
        try:
            raw = client.execute_command("JSON.GET", _key(user_id), "$")
        except Exception as e:
            logger.warning("semantic_memory.get RedisJSON unavailable: %s", e)
            return None
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        import json
        data = json.loads(raw)
        # JSON.GET with $ 返回数组
        if isinstance(data, list):
            data = data[0] if data else None
        return data
    except Exception as e:
        logger.warning("semantic_memory.get_profile failed: %s", e)
        return None


def upsert_profile(user_id: str, updates: Dict[str, Any]) -> bool:
    """合并式写入画像（不存在则用默认值新建）"""
    try:
        client = get_redis_client()
        cur = get_profile(user_id) or _default_profile(user_id)
        # 合并（顶层键覆盖，不深合并以保持简单）
        cur.update(updates)
        cur["_updated_at"] = int(time.time())
        import json
        client.execute_command("JSON.SET", _key(user_id), "$", json.dumps(cur, ensure_ascii=False))
        return True
    except Exception as e:
        logger.warning("semantic_memory.upsert_profile failed: %s", e)
        return False


def add_preference(user_id: str, preference: str) -> bool:
    """追加一条偏好（去重）"""
    profile = get_profile(user_id) or _default_profile(user_id)
    prefs = profile.get("preferences") or []
    if preference not in prefs:
        prefs.append(preference)
    return upsert_profile(user_id, {"preferences": prefs})


def add_confirmed_pattern(user_id: str, pattern_id: str) -> bool:
    profile = get_profile(user_id) or _default_profile(user_id)
    patterns = profile.get("confirmed_patterns") or []
    if pattern_id not in patterns:
        patterns.append(pattern_id)
    return upsert_profile(user_id, {"confirmed_patterns": patterns})


def increment_investigation(user_id: str) -> bool:
    profile = get_profile(user_id) or _default_profile(user_id)
    stats = profile.get("stats") or {}
    stats["total_investigations"] = (stats.get("total_investigations") or 0) + 1
    stats["last_active"] = int(time.time())
    return upsert_profile(user_id, {"stats": stats})
