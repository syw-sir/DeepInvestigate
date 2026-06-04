"""
情景记忆（Episodic Memory）

记录历史调查的事件、过程、结论，支持向量语义检索。

Redis 存储设计：
    em:{user_id}:{uuid}    Hash       单条记忆
        - content    : str (utf-8 bytes)
        - user_id    : str
        - timestamp  : int
        - tags       : str (逗号分隔)
        - thread_id  : str
        - embedding  : bytes (FLOAT32 raw)

    em_idx                 RediSearch Index (HNSW)
"""

from __future__ import annotations

import json
import logging
import struct
import time
import uuid
from typing import Any, Dict, List, Optional

import numpy as np

from redis.commands.search.field import (
    NumericField,
    TagField,
    TextField,
    VectorField,
)
try:
    from redis.commands.search.index_definition import IndexDefinition, IndexType  # redis-py >= 7
except ImportError:
    from redis.commands.search.indexDefinition import IndexDefinition, IndexType  # redis-py <= 6
from redis.commands.search.query import Query
from redis.exceptions import ResponseError

from .redis_client import get_redis_client

try:
    from config_deepseek import EPISODIC_INDEX, EMBEDDER_DIM
except ImportError:
    from ..config_deepseek import EPISODIC_INDEX, EMBEDDER_DIM  # type: ignore

logger = logging.getLogger(__name__)

KEY_PREFIX = "em:"
INDEX_NAME = EPISODIC_INDEX


# ---------------- 索引初始化 ---------------- #

def _ensure_index(dim: int) -> bool:
    """确保 RediSearch 向量索引存在（幂等）"""
    client = get_redis_client()
    try:
        info = client.ft(INDEX_NAME).info()
        # 如果 dim 不匹配，旧索引可能与新模型不兼容
        if info:
            return True
    except ResponseError:
        pass

    schema = (
        TextField("content"),
        TagField("user_id"),
        NumericField("timestamp", sortable=True),
        TagField("tags"),
        TagField("thread_id"),
        VectorField(
            "embedding",
            "HNSW",
            {
                "TYPE": "FLOAT32",
                "DIM": dim,
                "DISTANCE_METRIC": "COSINE",
                "M": 16,
                "EF_CONSTRUCTION": 200,
            },
        ),
    )

    try:
        client.ft(INDEX_NAME).create_index(
            schema,
            definition=IndexDefinition(prefix=[KEY_PREFIX], index_type=IndexType.HASH),
        )
        logger.info("Episodic index '%s' created (dim=%d)", INDEX_NAME, dim)
        return True
    except Exception as e:
        logger.warning("Failed to create episodic index: %s", e)
        return False


def _vec_to_bytes(vec: List[float]) -> bytes:
    arr = np.asarray(vec, dtype=np.float32)
    return arr.tobytes()


def _bytes_to_vec(buf: bytes) -> List[float]:
    return np.frombuffer(buf, dtype=np.float32).tolist()


# ---------------- 写入 ---------------- #

def add(
    user_id: str,
    content: str,
    embedding: List[float],
    *,
    tags: Optional[List[str]] = None,
    thread_id: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """写入一条情景记忆，返回记忆 id（uuid）"""
    if not content or not embedding:
        return None
    try:
        _ensure_index(len(embedding))
        client = get_redis_client()

        mem_id = uuid.uuid4().hex
        key = f"{KEY_PREFIX}{user_id}:{mem_id}"

        mapping: Dict[bytes, bytes] = {
            b"content": content.encode("utf-8"),
            b"user_id": user_id.encode("utf-8"),
            b"timestamp": str(int(time.time())).encode("utf-8"),
            b"tags": (",".join(tags or [])).encode("utf-8"),
            b"thread_id": thread_id.encode("utf-8"),
            b"embedding": _vec_to_bytes(embedding),
        }
        if extra:
            mapping[b"extra"] = json.dumps(extra, ensure_ascii=False).encode("utf-8")

        client.hset(key, mapping=mapping)
        return mem_id
    except Exception as e:
        logger.warning("episodic_memory.add failed: %s", e)
        return None


# ---------------- 召回 ---------------- #

def recall(
    user_id: str,
    query: str,
    top_k: int = 5,
    query_embedding: Optional[List[float]] = None,
) -> List[Dict[str, Any]]:
    """按语义相似度召回情景记忆

    若不提供 query_embedding，则尝试用全局 embedder 自动编码。
    """
    if not query and query_embedding is None:
        return []

    try:
        # 懒加载 embedder
        if query_embedding is None:
            try:
                from rag.embedder import get_embedder
            except ImportError:
                from ..rag.embedder import get_embedder  # type: ignore
            emb = get_embedder()
            query_embedding = emb.encode_one(query)

        _ensure_index(len(query_embedding))

        client = get_redis_client()
        # KNN 查询，限定 user_id
        # 注意：RediSearch TAG 字段中 - 等符号需要转义
        safe_uid = user_id.replace("-", "\\-").replace("_", "\\_")
        q_str = f"(@user_id:{{{safe_uid}}})=>[KNN {top_k} @embedding $vec AS score]"

        q = (
            Query(q_str)
            .sort_by("score")
            .return_fields("content", "tags", "timestamp", "thread_id", "score")
            .paging(0, top_k)
            .dialect(2)
        )

        params = {"vec": _vec_to_bytes(query_embedding)}
        res = client.ft(INDEX_NAME).search(q, query_params=params)

        items: List[Dict[str, Any]] = []
        for doc in res.docs:
            content = getattr(doc, "content", b"")
            if isinstance(content, bytes):
                content = content.decode("utf-8", errors="replace")
            tags = getattr(doc, "tags", b"")
            if isinstance(tags, bytes):
                tags = tags.decode("utf-8", errors="replace")
            ts = getattr(doc, "timestamp", b"0")
            if isinstance(ts, bytes):
                ts = ts.decode()
            score = getattr(doc, "score", "1.0")
            try:
                score_v = round(1 - float(score), 4)
            except Exception:
                score_v = None
            items.append({
                "id": doc.id,
                "content": content,
                "tags": [t for t in tags.split(",") if t],
                "timestamp": int(ts) if ts else 0,
                "score": score_v,
            })
        return items
    except Exception as e:
        logger.warning("episodic_memory.recall failed (downgraded): %s", e)
        return []


def count(user_id: Optional[str] = None) -> int:
    """统计当前用户（或全部）的记忆条数"""
    try:
        client = get_redis_client()
        if user_id is None:
            keys = list(client.scan_iter(f"{KEY_PREFIX}*", count=500))
        else:
            keys = list(client.scan_iter(f"{KEY_PREFIX}{user_id}:*", count=500))
        return len(keys)
    except Exception as e:
        logger.warning("episodic_memory.count failed: %s", e)
        return 0


def delete_by_id(user_id: str, mem_id: str) -> bool:
    try:
        client = get_redis_client()
        client.delete(f"{KEY_PREFIX}{user_id}:{mem_id}")
        return True
    except Exception as e:
        logger.warning("episodic_memory.delete failed: %s", e)
        return False
