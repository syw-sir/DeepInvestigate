"""
DeepInvestigate RAG 子系统

- chroma_client : ChromaDB 客户端
- embedder      : Embedding 模型（默认 BGE-M3）
- retriever     : 检索接口
- ingest        : 知识库导入
"""

from .chroma_client import get_chroma_client, get_collection
from .embedder import get_embedder

__all__ = ["get_chroma_client", "get_collection", "get_embedder"]
