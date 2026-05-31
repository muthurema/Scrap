"""
Embedding service — dense (BGE small) + sparse (BM25) + cross-encoder reranker.
All models loaded lazily and run in thread pool. Query-side embeddings
are LRU-cached (in-process) so repeated questions don't re-embed.
"""
import asyncio
import hashlib
import re
from collections import OrderedDict
from typing import List
from loguru import logger
from fastembed import TextEmbedding, SparseTextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder

from app.config import get_settings

settings = get_settings()

_dense: TextEmbedding | None = None
_sparse: SparseTextEmbedding | None = None
_reranker: TextCrossEncoder | None = None


# ── Query embedding cache (LRU) ──────────────────────────────────────────────
# Caches the embedding for queries the user has asked recently. Saves
# ~50-150ms per duplicate query on CPU. Capped to ~1000 entries × 384 floats
# × 4 bytes ≈ 1.5 MB — trivial memory footprint.
class _LRUCache:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self._data: OrderedDict = OrderedDict()

    def get(self, key):
        if key not in self._data:
            return None
        self._data.move_to_end(key)
        return self._data[key]

    def put(self, key, value):
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = value
        if len(self._data) > self.capacity:
            self._data.popitem(last=False)

    def __len__(self):
        return len(self._data)


_dense_query_cache = _LRUCache(capacity=1000)
_sparse_query_cache = _LRUCache(capacity=1000)


def _cache_key(query: str) -> str:
    # Normalize whitespace + lowercase so "What PPE for confined space?" and
    # "what  ppe for confined space?" share a cache slot.
    norm = re.sub(r"\s+", " ", (query or "").strip().lower())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def query_cache_stats() -> dict:
    """Exposed via /api/health/qdrant or admin tools to monitor hit rate."""
    return {
        "dense_query_cache_size": len(_dense_query_cache),
        "sparse_query_cache_size": len(_sparse_query_cache),
        "capacity": _dense_query_cache.capacity,
    }


def _get_dense() -> TextEmbedding:
    global _dense
    if _dense is None:
        logger.info(f"Loading dense embedding model: {settings.embedding_model}")
        # Cap ONNX threads so embedding can't saturate every core. This
        # keeps CPU headroom for bcrypt-based login + chat streaming while
        # a big document is being ingested in the background.
        _dense = TextEmbedding(
            model_name=settings.embedding_model,
            threads=settings.embed_onnx_threads,
        )
    return _dense


def _get_sparse() -> SparseTextEmbedding:
    global _sparse
    if _sparse is None:
        logger.info("Loading BM25 sparse embedding model")
        _sparse = SparseTextEmbedding(
            model_name="Qdrant/bm25",
            threads=settings.embed_onnx_threads,
        )
    return _sparse


def _get_reranker() -> TextCrossEncoder:
    global _reranker
    if _reranker is None:
        logger.info("Loading cross-encoder reranker: Xenova/ms-marco-MiniLM-L-6-v2")
        _reranker = TextCrossEncoder(
            model_name="Xenova/ms-marco-MiniLM-L-6-v2",
            threads=settings.embed_onnx_threads,
        )
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
    key = _cache_key(query)
    cached = _dense_query_cache.get(key)
    if cached is not None:
        return cached
    vectors = await embed_texts([query])
    _dense_query_cache.put(key, vectors[0])
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
    key = _cache_key(query)
    cached = _sparse_query_cache.get(key)
    if cached is not None:
        return cached
    out = await asyncio.to_thread(_embed_sparse_sync, [query], True)
    _sparse_query_cache.put(key, out[0])
    return out[0]


# ── Reranker ──────────────────────────────────────────────────────────────────

def _rerank_sync(query: str, passages: List[str]) -> List[float]:
    model = _get_reranker()
    return list(map(float, model.rerank(query, passages)))


async def rerank(query: str, passages: List[str]) -> List[float]:
    if not passages:
        return []
    return await asyncio.to_thread(_rerank_sync, query, passages)
