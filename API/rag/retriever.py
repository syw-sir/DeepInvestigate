"""
RAG 统一检索接口

封装 ChromaDB + Embedder 的查询逻辑，供工具和节点统一调用。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .chroma_client import get_collection
from .embedder import get_embedder

try:
    from config_deepseek import CHROMA_DEFAULT_TOP_K
except ImportError:
    from ..config_deepseek import CHROMA_DEFAULT_TOP_K  # type: ignore

logger = logging.getLogger(__name__)


def search(
    query: str,
    top_k: Optional[int] = None,
    source: Optional[str] = None,
    collection_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """检索 RAG 知识库

    Args:
        query: 查询字符串
        top_k: 返回结果数，默认 config 中的 default_top_k
        source: 数据源过滤（mitre_attack / cve / ...）
        collection_name: 指定 collection，默认主 collection
    """
    if not query:
        return []

    try:
        embedder = get_embedder()
        coll = get_collection(collection_name)
        if coll.count() == 0:
            return []

        vec = embedder.encode_one(query)
        where = {"source": source} if source else None
        res = coll.query(
            query_embeddings=[vec],
            n_results=top_k or CHROMA_DEFAULT_TOP_K,
            where=where,
        )

        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]

        items: List[Dict[str, Any]] = []
        for doc, meta, dist in zip(docs, metas or [], dists or []):
            items.append({
                "content": doc,
                "title": (meta or {}).get("title", ""),
                "source": (meta or {}).get("source", "unknown"),
                "metadata": meta or {},
                "score": round(1 - dist, 4) if dist is not None else None,
            })
        return items
    except Exception as e:
        logger.warning("rag.retriever.search failed: %s", e)
        return []
