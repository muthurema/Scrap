"""
Embedding service — dense (BGE small) + sparse (BM25) + cross-encoder reranker.
All models loaded lazily and run in thread pool.
"""
import asyncio
import re
from typing import List
from loguru import logger
from fastembed import TextEmbedding, SparseTextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder

from app.config import get_settings

settings = get_settings()

_dense: TextEmbedding | None = None
_sparse: SparseTextEmbedding | None = None
_reranker: TextCrossEncoder | None = None


def _get_dense() -> TextEmbedding:
    global _dense
    if _dense is None:
        logger.info(f"Loading dense embedding model: {settings.embedding_model}")
        _dense = TextEmbedding(model_name=settings.embedding_model)
    return _dense


def _get_sparse() -> SparseTextEmbedding:
    global _sparse
    if _sparse is None:
        logger.info("Loading BM25 sparse embedding model")
        _sparse = SparseTextEmbedding(model_name="Qdrant/bm25")
    return _sparse


def _get_reranker() -> TextCrossEncoder:
    global _reranker
    if _reranker is None:
        logger.info("Loading cross-encoder reranker: Xenova/ms-marco-MiniLM-L-6-v2")
        _reranker = TextCrossEncoder(model_name="Xenova/ms-marco-MiniLM-L-6-v2")
    return _reranker


# ── Dense ─────────────────────────────────────────────────────────────────────

def _embed_dense_sync(texts: List[str]) -> List[List[float]]:
    model = _get_dense()
    return [list(map(float, e)) for e in model.embed(texts)]


async def embed_texts(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    return await asyncio.to_thread(_embed_dense_sync, texts)


async def embed_query(query: str) -> List[float]:
    vectors = await embed_texts([query])
    return vectors[0]


# ── Sparse (BM25) ────────────────────────────────────────────────────────────

def _embed_sparse_sync(texts: List[str], is_query: bool = False) -> List[dict]:
    model = _get_sparse()
    embeds = model.query_embed(texts) if is_query else model.embed(texts)
    out = []
    for e in embeds:
        out.append({"indices": e.indices.tolist(), "values": e.values.tolist()})
    return out


async def embed_sparse_docs(texts: List[str]) -> List[dict]:
    if not texts:
        return []
    return await asyncio.to_thread(_embed_sparse_sync, texts, False)


async def embed_sparse_query(query: str) -> dict:
    out = await asyncio.to_thread(_embed_sparse_sync, [query], True)
    return out[0]


# ── Reranker ──────────────────────────────────────────────────────────────────

def _rerank_sync(query: str, passages: List[str]) -> List[float]:
    model = _get_reranker()
    return list(map(float, model.rerank(query, passages)))


async def rerank(query: str, passages: List[str]) -> List[float]:
    if not passages:
        return []
    return await asyncio.to_thread(_rerank_sync, query, passages)
