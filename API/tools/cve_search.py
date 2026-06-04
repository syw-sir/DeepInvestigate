"""
CVE 漏洞信息检索

策略：
    1. 优先从本地 RAG 知识库（source=cve）召回
    2. 若给定 CVE ID（CVE-XXXX-XXXX），可选直接走 NVD API 在线查询
       （需配置 web 访问；默认仅走本地以避免外网依赖）

输出统一 JSON，便于 Agent 解析。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

CVE_ID_RE = re.compile(r"CVE-\d{4}-\d{4,7}", re.IGNORECASE)


def _local_rag(query: str, top_k: int) -> list:
    """走本地 RAG 知识库的 cve 源"""
    try:
        from rag.chroma_client import get_collection
        from rag.embedder import get_embedder
    except ImportError:
        from ..rag.chroma_client import get_collection  # type: ignore
        from ..rag.embedder import get_embedder  # type: ignore

    embedder = get_embedder()
    coll = get_collection()
    vec = embedder.encode_one(query)
    res = coll.query(
        query_embeddings=[vec],
        n_results=top_k,
        where={"source": "cve"},
    )
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    items = []
    for doc, meta in zip(docs, metas or []):
        items.append({
            "cve_id": (meta or {}).get("cve_id", ""),
            "title": (meta or {}).get("title", ""),
            "severity": (meta or {}).get("severity", ""),
            "content": doc,
        })
    return items


@tool("search_cve", parse_docstring=True)
def search_cve(query: str, top_k: int = 5) -> str:
    """根据 CVE ID 或自然语言关键词检索 CVE 漏洞信息。

    优先使用本地知识库（已索引 NVD 数据），返回匹配的漏洞描述、严重程度、影响产品等。

    Args:
        query: CVE 编号（如 "CVE-2023-44487"）或自然语言描述（如 "openssh 暴力破解相关漏洞"）。
        top_k: 返回条数，默认 5。

    Returns:
        JSON 字符串：{"results": [{"cve_id": "...", "title": "...", "severity": "...", "content": "..."}, ...]}
    """
    try:
        items = _local_rag(query, top_k)
        if not items:
            return json.dumps(
                {"results": [], "message": "no matching CVE in local knowledge base"},
                ensure_ascii=False,
            )
        return json.dumps({"results": items}, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.exception("search_cve failed")
        return json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False)
