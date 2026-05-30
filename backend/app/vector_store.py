"""
Vector store service backed by Qdrant in local/file mode (no server needed).
"""
import asyncio
import uuid
from typing import Optional, List
from loguru import logger

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue, FilterSelector,
)

from app.config import get_settings, DocumentType, DocumentSource
from app.embeddings import embed_texts, embed_query
from app.schemas import RetrievedChunk

settings = get_settings()


class VectorStoreService:
    _instance: Optional["VectorStoreService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        logger.info(f"Initializing Qdrant local at {settings.qdrant_path}")
        self.client = QdrantClient(path=settings.qdrant_path)
        self._ensure_collections_sync()

    def _ensure_collections_sync(self):
        existing = {c.name for c in self.client.get_collections().collections}
        for name in (settings.qdrant_collection_company, settings.qdrant_collection_base):
            if name not in existing:
                self.client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(
                        size=settings.embedding_dimensions,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info(f"Created Qdrant collection: {name}")

    async def ensure_collections(self):
        await asyncio.to_thread(self._ensure_collections_sync)

    # ── Upsert ───────────────────────────────────────────────────────────────

    async def upsert_chunks(self, collection_name: str, chunks: list[dict]) -> None:
        if not chunks:
            return
        texts = [c["text"] for c in chunks]
        vectors = await embed_texts(texts)

        points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vec,
                payload={**c["payload"], "chunk_str_id": c["id"]},
            )
            for c, vec in zip(chunks, vectors)
        ]
        await asyncio.to_thread(
            self.client.upsert,
            collection_name=collection_name,
            points=points,
        )

    # ── Delete ───────────────────────────────────────────────────────────────

    def _delete_sync(self, collection_name: str, doc_id: str):
        self.client.delete(
            collection_name=collection_name,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
                )
            ),
        )

    async def delete_by_doc_id(self, collection_name: str, doc_id: str) -> None:
        await asyncio.to_thread(self._delete_sync, collection_name, doc_id)

    # ── Search ───────────────────────────────────────────────────────────────

    def _search_sync(self, collection: str, vector: List[float], limit: int, search_filter):
        try:
            return self.client.search(
                collection_name=collection,
                query_vector=vector,
                limit=limit,
                query_filter=search_filter,
                with_payload=True,
            )
        except Exception as e:
            logger.warning(f"Search in {collection} failed: {e}")
            return []

    async def search(
        self,
        query: str,
        top_k: int = 8,
        company_id: Optional[str] = None,
    ) -> list[RetrievedChunk]:
        query_vector = await embed_query(query)

        # Company collection filter: only company-specific docs OR docs with no company
        # We do TWO searches in the company collection: one for the user's company, one for base
        # For simplicity, base collection has no company filter.

        company_filter = None
        if company_id:
            # match docs of this company OR shared docs (no company)
            from qdrant_client.models import Filter as F, FieldCondition as FC, MatchValue as MV, MatchAny
            company_filter = F(
                should=[
                    FC(key="company_id", match=MV(value=company_id)),
                    FC(key="company_id", match=MV(value="")),
                ]
            )

        company_hits = await asyncio.to_thread(
            self._search_sync, settings.qdrant_collection_company, query_vector, top_k, company_filter
        )
        base_hits = await asyncio.to_thread(
            self._search_sync, settings.qdrant_collection_base, query_vector, top_k, None
        )

        all_chunks: list[RetrievedChunk] = []
        for hit in list(company_hits) + list(base_hits):
            p = hit.payload or {}
            boost = float(p.get("priority_boost", 1.0))
            boosted = hit.score * boost
            try:
                dt = DocumentType(p.get("doc_type", "general"))
            except ValueError:
                dt = DocumentType.GENERAL
            try:
                src = DocumentSource(p.get("source", "base_corpus"))
            except ValueError:
                src = DocumentSource.BASE_CORPUS

            all_chunks.append(RetrievedChunk(
                doc_id=p.get("doc_id", ""),
                chunk_id=p.get("chunk_str_id", ""),
                text=p.get("text", ""),
                doc_type=dt,
                source=src,
                title=p.get("title", "Unknown"),
                filename=p.get("filename", ""),
                raw_score=hit.score,
                boosted_score=boosted,
                page_number=p.get("page_number"),
                metadata=p,
            ))

        # Deduplicate by chunk_id, keep highest score
        seen: dict[str, RetrievedChunk] = {}
        for chunk in all_chunks:
            key = chunk.chunk_id or chunk.text[:40]
            if key not in seen or chunk.boosted_score > seen[key].boosted_score:
                seen[key] = chunk

        ranked = sorted(seen.values(), key=lambda x: x.boosted_score, reverse=True)
        return ranked[:top_k]

    # ── Health ───────────────────────────────────────────────────────────────

    async def health(self) -> str:
        try:
            await asyncio.to_thread(self.client.get_collections)
            return "healthy"
        except Exception as e:
            logger.warning(f"Qdrant health check failed: {e}")
            return "unreachable"

    async def count_points(self, collection: str) -> int:
        try:
            res = await asyncio.to_thread(self.client.count, collection)
            return res.count
        except Exception:
            return 0


def get_vector_store() -> VectorStoreService:
    return VectorStoreService()
