"""
ChromaDB 客户端封装

提供全局唯一的 Chroma 客户端实例和默认 Collection。
优先使用 PersistentClient（嵌入模式，无需 Docker），
连接失败时自动回退到 HttpClient（Docker 模式）。
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from chromadb.config import Settings

try:
    from config_deepseek import (
        CHROMA_HOST,
        CHROMA_PORT,
        CHROMA_COLLECTION,
    )
except ImportError:
    from .config_deepseek import (  # type: ignore
        CHROMA_HOST,
        CHROMA_PORT,
        CHROMA_COLLECTION,
    )

logger = logging.getLogger(__name__)

_client: Optional[ClientAPI] = None

# 嵌入模式持久化目录
_CHROMA_PERSIST_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "chroma_embedded",
)


def get_chroma_client() -> ClientAPI:
    """获取全局 Chroma 客户端（懒加载单例）

    优先使用 PersistentClient（嵌入模式，无需 Docker），
    服务器不可用时自动回退。
    """
    global _client
    if _client is not None:
        return _client

    # 尝试嵌入模式（首选，无需 Docker）
    try:
        os.makedirs(_CHROMA_PERSIST_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=_CHROMA_PERSIST_DIR,
            settings=Settings(anonymized_telemetry=False),
        )
        logger.info("Chroma PersistentClient initialized: %s", _CHROMA_PERSIST_DIR)
        return _client
    except Exception as e:
        logger.warning("PersistentClient failed (%s), falling back to HttpClient", e)

    # 回退：尝试连接 Docker 服务器
    try:
        _client = chromadb.HttpClient(
            host=CHROMA_HOST,
            port=CHROMA_PORT,
            settings=Settings(anonymized_telemetry=False),
        )
        logger.info("Chroma HttpClient initialized: %s:%s", CHROMA_HOST, CHROMA_PORT)
        return _client
    except Exception as e:
        logger.error("ChromaDB 完全不可用: %s", e)
        raise


def get_collection(name: Optional[str] = None) -> Collection:
    """获取或创建 Collection

    Args:
        name: collection 名称，默认使用 config.yaml 中的 chroma.collection
    """
    client = get_chroma_client()
    coll_name = name or CHROMA_COLLECTION
    # 注意：embedding 由我们自己计算后传入，不让 chroma 内部 embed
    return client.get_or_create_collection(
        name=coll_name,
        metadata={"hnsw:space": "cosine"},
    )


def ping_chroma() -> bool:
    """健康检查"""
    try:
        client = get_chroma_client()
        client.heartbeat()
        return True
    except Exception as e:
        logger.error("Chroma heartbeat failed: %s", e)
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Ping:", ping_chroma())
    coll = get_collection()
    print("Collection:", coll.name, "count =", coll.count())
