"""
程序记忆（Procedural Memory）

记录"做某类事情的成功流程"——把成功的调查路径沉淀为可复用 SOP。

Redis Key 设计：
    pm:{pattern_id}    Hash     单个 SOP
        - title       : str
        - description : str
        - steps       : str (JSON array)
        - keywords    : str (逗号分隔)
        - embedding   : bytes (FLOAT32 raw)
        - success_count : int
        - last_used   : int

    pm_idx             RediSearch 向量索引

复用 episodic_memory 的索引设计模式（HNSW）。
"""

from __future__ import annotations

import json
import logging
import time
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

logger = logging.getLogger(__name__)

KEY_PREFIX = "pm:"
INDEX_NAME = "pm_idx"


def _vec_bytes(vec: List[float]) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def _ensure_index(dim: int) -> bool:
    client = get_redis_client()
    try:
        client.ft(INDEX_NAME).info()
        return True
    except ResponseError:
        pass

    schema = (
        TextField("title"),
        TextField("description"),
        TagField("keywords"),
        NumericField("success_count", sortable=True),
        NumericField("last_used", sortable=True),
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
        logger.info("Procedural index '%s' created (dim=%d)", INDEX_NAME, dim)
        return True
    except Exception as e:
        logger.warning("Failed to create procedural index: %s", e)
        return False


def add(
    pattern_id: str,
    title: str,
    description: str,
    steps: List[str],
    embedding: List[float],
    keywords: Optional[List[str]] = None,
) -> bool:
    """新增或覆盖一个 SOP"""
    try:
        _ensure_index(len(embedding))
        client = get_redis_client()
        key = f"{KEY_PREFIX}{pattern_id}"
        mapping = {
            b"title": title.encode("utf-8"),
            b"description": description.encode("utf-8"),
            b"steps": json.dumps(steps, ensure_ascii=False).encode("utf-8"),
            b"keywords": (",".join(keywords or [])).encode("utf-8"),
            b"embedding": _vec_bytes(embedding),
            b"success_count": str(0).encode("utf-8"),
            b"last_used": str(int(time.time())).encode("utf-8"),
        }
        client.hset(key, mapping=mapping)
        return True
    except Exception as e:
        logger.warning("procedural_memory.add failed: %s", e)
        return False


def increment_success(pattern_id: str) -> bool:
    try:
        client = get_redis_client()
        key = f"{KEY_PREFIX}{pattern_id}"
        client.hincrby(key, "success_count", 1)
        client.hset(key, "last_used", int(time.time()))
        return True
    except Exception as e:
        logger.warning("procedural_memory.increment_success failed: %s", e)
        return False


def recall(query: str, top_k: int = 3, query_embedding: Optional[List[float]] = None) -> List[Dict[str, Any]]:
    """语义检索 SOP"""
    if not query and query_embedding is None:
        return []

    try:
        if query_embedding is None:
            try:
                from rag.embedder import get_embedder
            except ImportError:
                from ..rag.embedder import get_embedder  # type: ignore
            query_embedding = get_embedder().encode_one(query)

        _ensure_index(len(query_embedding))
        client = get_redis_client()

        q_str = f"*=>[KNN {top_k} @embedding $vec AS score]"
        q = (
            Query(q_str)
            .sort_by("score")
            .return_fields("title", "description", "steps", "keywords",
                           "success_count", "score")
            .paging(0, top_k)
            .dialect(2)
        )
        params = {"vec": _vec_bytes(query_embedding)}
        res = client.ft(INDEX_NAME).search(q, query_params=params)

        items = []
        for doc in res.docs:
            def _get(field, default=""):
                v = getattr(doc, field, default)
                if isinstance(v, bytes):
                    v = v.decode("utf-8", errors="replace")
                return v

            try:
                steps_json = _get("steps", "[]")
                steps = json.loads(steps_json) if steps_json else []
            except Exception:
                steps = []

            try:
                score_v = round(1 - float(_get("score", "1.0")), 4)
            except Exception:
                score_v = None

            items.append({
                "id": doc.id,
                "title": _get("title"),
                "description": _get("description"),
                "steps": steps,
                "keywords": [k for k in _get("keywords").split(",") if k],
                "success_count": int(_get("success_count", "0") or 0),
                "score": score_v,
            })
        return items
    except Exception as e:
        logger.warning("procedural_memory.recall failed: %s", e)
        return []
