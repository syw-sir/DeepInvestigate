"""
Redis Stack 客户端封装

统一管理 Redis 连接池，供四类记忆模块共用。
要求 Redis Stack（含 RediSearch + RedisJSON 模块）。
"""

from __future__ import annotations

import logging
from typing import Optional

import redis
from redis.connection import ConnectionPool

try:
    from config_deepseek import (
        REDIS_HOST,
        REDIS_PORT,
        REDIS_DB,
        REDIS_PASSWORD,
    )
except ImportError:
    from .config_deepseek import (  # type: ignore
        REDIS_HOST,
        REDIS_PORT,
        REDIS_DB,
        REDIS_PASSWORD,
    )

logger = logging.getLogger(__name__)

_pool: Optional[ConnectionPool] = None
_client: Optional[redis.Redis] = None


def _build_pool() -> ConnectionPool:
    """构建全局连接池"""
    return ConnectionPool(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        password=REDIS_PASSWORD,
        decode_responses=False,   # 二进制安全（向量需要 bytes）
        max_connections=32,
        socket_connect_timeout=5,
        socket_timeout=10,
    )


def get_redis_client() -> redis.Redis:
    """获取全局 Redis 客户端（懒加载单例）"""
    global _pool, _client
    if _client is None:
        _pool = _build_pool()
        _client = redis.Redis(connection_pool=_pool)
        logger.info(
            "Redis client initialized: %s:%s/db%s", REDIS_HOST, REDIS_PORT, REDIS_DB
        )
    return _client


def ping_redis() -> bool:
    """健康检查：返回 True 表示连接正常"""
    try:
        client = get_redis_client()
        return bool(client.ping())
    except Exception as e:
        logger.error("Redis ping failed: %s", e)
        return False


def check_redis_modules() -> dict:
    """检查 Redis Stack 模块是否就绪（RediSearch / RedisJSON）"""
    client = get_redis_client()
    try:
        modules = client.module_list()
        loaded = {}
        for m in modules:
            # m 形如 [b'name', b'search', b'ver', 20612]
            name = None
            if isinstance(m, list):
                for i, item in enumerate(m):
                    if item == b"name" and i + 1 < len(m):
                        name = m[i + 1].decode() if isinstance(m[i + 1], bytes) else str(m[i + 1])
                        break
            elif isinstance(m, dict):
                name = m.get(b"name", b"").decode() if isinstance(m.get(b"name"), bytes) else str(m.get("name", ""))
            if name:
                loaded[name] = True
        return {
            "search": loaded.get("search", False),
            "ReJSON": loaded.get("ReJSON", False),
            "all_modules": list(loaded.keys()),
        }
    except Exception as e:
        logger.error("Failed to check redis modules: %s", e)
        return {"search": False, "ReJSON": False, "error": str(e)}


if __name__ == "__main__":
    # 简单自检
    logging.basicConfig(level=logging.INFO)
    print("Ping:", ping_redis())
    print("Modules:", check_redis_modules())
