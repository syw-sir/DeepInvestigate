"""
RAG 知识库灌库脚本

用法：
    cd API
    python -m rag.ingest --file ../knowledge/seed_attack.jsonl
    python -m rag.ingest --file ../knowledge/seed_cve.jsonl
    python -m rag.ingest --dir ../knowledge   # 灌入整个目录

输入 jsonl 文件，每行一条记录，必须包含至少：
    - content  : 文本内容（必填）
    - source   : 数据源标签（如 "mitre_attack" / "cve"）
    - id 或 cve_id 等：作为 ChromaDB doc id
    - 其他字段会写入 metadata
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Iterable, List, Tuple

# 允许从 API/ 目录运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag.chroma_client import get_collection  # noqa: E402
from rag.embedder import get_embedder        # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("ingest")


# 简单分块：长内容按字数切分（中文友好的固定窗口）
CHUNK_SIZE = 600
CHUNK_OVERLAP = 80


def _chunk(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    if not text:
        return []
    if len(text) <= size:
        return [text]
    parts = []
    i = 0
    while i < len(text):
        parts.append(text[i: i + size])
        i += size - overlap
    return parts


def _flatten_meta(meta: dict) -> dict:
    """Chroma metadata 只接受标量类型（str/int/float/bool）"""
    flat = {}
    for k, v in meta.items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            flat[k] = v
        else:
            flat[k] = json.dumps(v, ensure_ascii=False)[:500]
    return flat


def iter_jsonl(path: Path) -> Iterable[dict]:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                yield json.loads(line)
            except Exception as e:
                logger.warning("Bad jsonl line in %s: %s", path, e)


def ingest_file(path: Path) -> Tuple[int, int]:
    """灌入单文件，返回 (records, chunks)"""
    coll = get_collection()
    embedder = get_embedder()

    docs: List[str] = []
    ids: List[str] = []
    metas: List[dict] = []

    n_records = 0
    for rec in iter_jsonl(path):
        n_records += 1
        content = rec.get("content", "")
        if not content:
            continue

        base_id = rec.get("id") or rec.get("cve_id") or uuid.uuid4().hex
        source = rec.get("source", path.stem)

        meta_base = {k: v for k, v in rec.items() if k not in ("content",)}
        meta_base.setdefault("source", source)
        meta_flat = _flatten_meta(meta_base)

        for i, chunk in enumerate(_chunk(content)):
            cid = f"{base_id}_{i}" if i > 0 or len(_chunk(content)) > 1 else base_id
            docs.append(chunk)
            ids.append(cid)
            metas.append({**meta_flat, "chunk_index": i})

    if not docs:
        logger.info("No records to ingest from %s", path)
        return n_records, 0

    logger.info("Embedding %d chunks (file=%s) ...", len(docs), path.name)
    vectors = embedder.encode(docs)

    # ChromaDB 的 upsert 接口（存在则覆盖）
    coll.upsert(documents=docs, ids=ids, metadatas=metas, embeddings=vectors)
    logger.info("✅ Upserted %d chunks from %s", len(docs), path.name)
    return n_records, len(docs)


def main():
    ap = argparse.ArgumentParser(description="Ingest knowledge files into ChromaDB")
    ap.add_argument("--file", type=str, help="single jsonl file")
    ap.add_argument("--dir", type=str, help="directory containing jsonl files")
    args = ap.parse_args()

    if not args.file and not args.dir:
        ap.print_help()
        sys.exit(1)

    files: List[Path] = []
    if args.file:
        files.append(Path(args.file))
    if args.dir:
        for p in Path(args.dir).glob("*.jsonl"):
            files.append(p)

    total_records = 0
    total_chunks = 0
    for fp in files:
        if not fp.exists():
            logger.warning("Skip missing file: %s", fp)
            continue
        r, c = ingest_file(fp)
        total_records += r
        total_chunks += c

    logger.info("=" * 50)
    logger.info("Ingest complete: %d records → %d chunks", total_records, total_chunks)
    logger.info("Collection count: %d", get_collection().count())


if __name__ == "__main__":
    main()
