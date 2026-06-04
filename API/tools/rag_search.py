"""
RAG 知识库检索工具

从 ChromaDB 中检索与查询语义相关的知识片段（MITRE ATT&CK、CVE、内部 SOP 等）。

依赖：rag.chroma_client / rag.embedder（Sprint 1 已就绪）
数据：Sprint 4 由 rag/ingest.py 灌库
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _search(query: str, top_k: int, source_filter: Optional[str]) -> list:
    """实际检索逻辑（同步）"""
    try:
        from rag.chroma_client import get_collection
        from rag.embedder import get_embedder
    except ImportError:
        from ..rag.chroma_client import get_collection  # type: ignore
        from ..rag.embedder import get_embedder  # type: ignore

    embedder = get_embedder()
    coll = get_collection()

    query_vec = embedder.encode_one(query)

    where = {"source": source_filter} if source_filter else None
    res = coll.query(
        query_embeddings=[query_vec],
        n_results=top_k,
        where=where,
    )

    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    dists = res.get("distances", [[]])[0]

    items = []
    for doc, meta, dist in zip(docs, metas or [], dists or []):
        items.append({
            "content": doc,
            "source": (meta or {}).get("source", "unknown"),
            "title": (meta or {}).get("title", ""),
            "score": round(1 - dist, 4) if dist is not None else None,
        })
    return items


@tool("rag_search", parse_docstring=True)
def rag_search(
    query: str,
    top_k: int = 5,
    source: Optional[str] = None,
) -> str:
    """从内部知识库（MITRE ATT&CK / CVE / SOP）检索与 query 语义相关的片段。

    返回 JSON 字符串，包含 top_k 条结果，每条含 content / source / title / score。

    Args:
        query: 查询语句，自然语言或关键词。
        top_k: 返回结果数，默认 5。
        source: 可选数据源过滤，例如 "mitre_attack" / "cve"。

    Returns:
        JSON 字符串，形如 [{"content": "...", "source": "...", "title": "...", "score": 0.87}, ...]
    """
    try:
        items = _search(query, top_k, source)
        if not items:
            return json.dumps({"results": [], "message": "no relevant knowledge found"}, ensure_ascii=False)
        return json.dumps({"results": items}, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.exception("rag_search failed")
        return json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False)
