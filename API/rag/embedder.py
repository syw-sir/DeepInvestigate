"""
Embedding 模型封装

支持两种 provider：
    - huggingface : 本地加载 sentence-transformers 模型（默认 BGE-M3）
    - openai      : 通过 OpenAI 兼容接口调用 embedding 模型

统一接口：
    embedder.encode(texts: List[str]) -> List[List[float]]
"""

from __future__ import annotations

import logging
from typing import List, Optional, Sequence

try:
    from config_deepseek import (
        EMBEDDER_PROVIDER,
        EMBEDDER_MODEL,
        EMBEDDER_DEVICE,
        EMBEDDER_DIM,
        EMBEDDER_BATCH_SIZE,
        EMBEDDER_API_BASE,
        EMBEDDER_API_KEY,
    )
except ImportError:
    from ..config_deepseek import (  # type: ignore
        EMBEDDER_PROVIDER,
        EMBEDDER_MODEL,
        EMBEDDER_DEVICE,
        EMBEDDER_DIM,
        EMBEDDER_BATCH_SIZE,
        EMBEDDER_API_BASE,
        EMBEDDER_API_KEY,
    )

logger = logging.getLogger(__name__)


class BaseEmbedder:
    """Embedding 接口基类"""

    dim: int = 0

    def encode(self, texts: Sequence[str]) -> List[List[float]]:
        raise NotImplementedError

    def encode_one(self, text: str) -> List[float]:
        return self.encode([text])[0]


class HuggingFaceEmbedder(BaseEmbedder):
    """基于 sentence-transformers 的本地 Embedding 模型"""

    def __init__(
        self,
        model_name: str = EMBEDDER_MODEL,
        device: str = EMBEDDER_DEVICE,
        batch_size: int = EMBEDDER_BATCH_SIZE,
    ):
        from sentence_transformers import SentenceTransformer

        logger.info("Loading HF embedder: %s on %s", model_name, device)
        self.model = SentenceTransformer(model_name, device=device)
        self.batch_size = batch_size
        # 推断真实维度
        try:
            self.dim = int(self.model.get_sentence_embedding_dimension())
        except Exception:
            self.dim = EMBEDDER_DIM

    def encode(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            return []
        vecs = self.model.encode(
            list(texts),
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return vecs.tolist()


class OpenAIEmbedder(BaseEmbedder):
    """通过 OpenAI 兼容接口调用 Embedding"""

    def __init__(
        self,
        model_name: str = "text-embedding-3-small",
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        batch_size: int = 64,
    ):
        from openai import OpenAI

        self.client = OpenAI(
            base_url=api_base or EMBEDDER_API_BASE,
            api_key=api_key or EMBEDDER_API_KEY,
        )
        self.model_name = model_name
        self.batch_size = batch_size
        # OpenAI 模型维度（small=1536, large=3072）
        self.dim = EMBEDDER_DIM or (1536 if "small" in model_name else 3072)
        logger.info(
            "OpenAIEmbedder ready: model=%s base=%s dim=%d",
            model_name, self.client.base_url, self.dim,
        )

    def encode(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            return []
        all_vecs: List[List[float]] = []
        items = list(texts)
        for i in range(0, len(items), self.batch_size):
            batch = items[i: i + self.batch_size]
            resp = self.client.embeddings.create(
                model=self.model_name,
                input=batch,
            )
            all_vecs.extend(d.embedding for d in resp.data)
        return all_vecs


# ---------------- 单例工厂 ---------------- #

_embedder: Optional[BaseEmbedder] = None


def get_embedder() -> BaseEmbedder:
    """获取全局 Embedder 实例（懒加载单例）"""
    global _embedder
    if _embedder is None:
        provider = EMBEDDER_PROVIDER.lower()
        if provider == "openai":
            _embedder = OpenAIEmbedder(model_name=EMBEDDER_MODEL)
        else:
            _embedder = HuggingFaceEmbedder(
                model_name=EMBEDDER_MODEL,
                device=EMBEDDER_DEVICE,
                batch_size=EMBEDDER_BATCH_SIZE,
            )
        logger.info("Embedder ready: provider=%s dim=%s", provider, _embedder.dim)
    return _embedder


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    emb = get_embedder()
    vec = emb.encode_one("SSH 暴力破解攻击")
    print(f"Embedding dim={len(vec)}, first 5 = {vec[:5]}")
