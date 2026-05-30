"""
Local embedding service using fastembed (ONNX-based, no torch needed).
Default model: BAAI/bge-small-en-v1.5 (384-dim, fast).
"""
import asyncio
from typing import List
from loguru import logger
from fastembed import TextEmbedding
from app.config import get_settings

settings = get_settings()

_model: TextEmbedding | None = None


def _get_model() -> TextEmbedding:
    global _model
    if _model is None:
        logger.info(f"Loading embedding model: {settings.embedding_model}")
        _model = TextEmbedding(model_name=settings.embedding_model)
        logger.info("Embedding model loaded")
    return _model


def _embed_sync(texts: List[str]) -> List[List[float]]:
    model = _get_model()
    return [list(map(float, e)) for e in model.embed(texts)]


async def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed a batch of texts. Runs in a thread pool to avoid blocking the event loop."""
    if not texts:
        return []
    return await asyncio.to_thread(_embed_sync, texts)


async def embed_query(query: str) -> List[float]:
    vectors = await embed_texts([query])
    return vectors[0]
