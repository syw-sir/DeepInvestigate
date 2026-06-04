"""
知识检索节点（RAG hook）

Sprint 3：占位降级；
Sprint 4：导入 MITRE ATT&CK / CVE 后真正生效。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from ..state import AgentState

try:
    from config_deepseek import ENABLE_RAG, CHROMA_DEFAULT_TOP_K
except ImportError:
    from ...config_deepseek import ENABLE_RAG, CHROMA_DEFAULT_TOP_K  # type: ignore

logger = logging.getLogger(__name__)


async def retrieve_knowledge_node(state: AgentState) -> Dict[str, Any]:
    """在 Planner 之前检索领域知识（RAG）"""
    if not ENABLE_RAG:
        return {"retrieved_knowledge": []}

    query = state.get("user_query", "")
    docs: list = []

    try:
        from rag.chroma_client import get_collection
        from rag.embedder import get_embedder

        embedder = get_embedder()
        coll = get_collection()
        if coll.count() == 0:
            logger.info("Knowledge collection empty, skip RAG")
            return {"retrieved_knowledge": []}

        vec = embedder.encode_one(query)
        res = coll.query(query_embeddings=[vec], n_results=CHROMA_DEFAULT_TOP_K)
        contents = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        for c, m in zip(contents, metas or []):
            docs.append({
                "content": c,
                "title": (m or {}).get("title", ""),
                "source": (m or {}).get("source", ""),
            })
    except Exception as e:
        logger.warning("retrieve_knowledge failed (downgraded): %s", e)
        docs = []

    logger.info("Retrieved %d knowledge docs", len(docs))
    return {"retrieved_knowledge": docs}
