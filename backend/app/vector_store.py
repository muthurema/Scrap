"""
Vector store service — Qdrant local file mode with HYBRID search (dense + sparse BM25)
plus cross-encoder re-ranking and Reciprocal Rank Fusion.
"""
import asyncio
import uuid
from typing import Optional, List
from loguru import logger

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, SparseVectorParams, SparseIndexParams,
    PointStruct, SparseVector,
    Filter, FieldCondition, MatchValue, FilterSelector,
)

from app.config import get_settings, DocumentType, DocumentSource
from app.embeddings import (
    embed_texts, embed_query,
    embed_sparse_docs, embed_sparse_query,
    rerank,
)
from app.schemas import RetrievedChunk

settings = get_settings()

DENSE_NAME = "dense"
SPARSE_NAME = "bm25"


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
                    vectors_config={DENSE_NAME: VectorParams(
                        size=settings.embedding_dimensions, distance=Distance.COSINE,
                    )},
                    sparse_vectors_config={SPARSE_NAME: SparseVectorParams(index=SparseIndexParams())},
                )
                logger.info(f"Created hybrid Qdrant collection: {name}")

    async def ensure_collections(self):
        await asyncio.to_thread(self._ensure_collections_sync)

    # ── Upsert ───────────────────────────────────────────────────────────────

    async def upsert_chunks(self, collection_name: str, chunks: list[dict]) -> None:
        if not chunks:
            return
        texts = [c["text"] for c in chunks]
        dense_vectors, sparse_vectors = await asyncio.gather(
            embed_texts(texts),
            embed_sparse_docs(texts),
        )
        points = []
        for c, d, s in zip(chunks, dense_vectors, sparse_vectors):
            points.append(PointStruct(
                id=str(uuid.uuid4()),
                vector={
                    DENSE_NAME: d,
                    SPARSE_NAME: SparseVector(indices=s["indices"], values=s["values"]),
                },
                payload={**c["payload"], "chunk_str_id": c["id"]},
            ))
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

    # ── Hybrid Search ────────────────────────────────────────────────────────

    def _search_dense_sync(self, collection, vector, limit, search_filter):
        try:
            return self.client.search(
                collection_name=collection,
                query_vector=(DENSE_NAME, vector),
                limit=limit, query_filter=search_filter, with_payload=True,
            )
        except Exception as e:
            logger.warning(f"Dense search in {collection} failed: {e}")
            return []

    def _search_sparse_sync(self, collection, sparse_vec, limit, search_filter):
        try:
            return self.client.search(
                collection_name=collection,
                query_vector=(SPARSE_NAME, SparseVector(
                    indices=sparse_vec["indices"], values=sparse_vec["values"],
                )),
                limit=limit, query_filter=search_filter, with_payload=True,
            )
        except Exception as e:
            logger.warning(f"Sparse search in {collection} failed: {e}")
            return []

    @staticmethod
    def _reciprocal_rank_fusion(*ranked_lists, k: int = 60) -> list:
        """RRF: each list contains qdrant hits ordered by rank. Returns merged + sorted by RRF score."""
        scores: dict[str, float] = {}
        objs: dict[str, object] = {}
        for ranked in ranked_lists:
            for rank, hit in enumerate(ranked):
                key = str(hit.id)
                scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
                objs[key] = hit
        merged = sorted(objs.values(), key=lambda h: scores[str(h.id)], reverse=True)
        return merged

    async def hybrid_search(
        self,
        query: str,
        top_k: int = 20,
        company_id: Optional[str] = None,
    ) -> list[RetrievedChunk]:
        """Dense + sparse search in both collections, fused via RRF."""
        dense_vec, sparse_vec = await asyncio.gather(
            embed_query(query),
            embed_sparse_query(query),
        )

        company_filter = None
        if company_id:
            company_filter = Filter(
                should=[
                    FieldCondition(key="company_id", match=MatchValue(value=company_id)),
                    FieldCondition(key="company_id", match=MatchValue(value="")),
                ]
            )

        coll_company = settings.qdrant_collection_company
        coll_base = settings.qdrant_collection_base

        # 4 parallel searches
        results = await asyncio.gather(
            asyncio.to_thread(self._search_dense_sync, coll_company, dense_vec, top_k, company_filter),
            asyncio.to_thread(self._search_sparse_sync, coll_company, sparse_vec, top_k, company_filter),
            asyncio.to_thread(self._search_dense_sync, coll_base, dense_vec, top_k, None),
            asyncio.to_thread(self._search_sparse_sync, coll_base, sparse_vec, top_k, None),
        )

        fused = self._reciprocal_rank_fusion(*results)
        out: list[RetrievedChunk] = []
        for hit in fused:
            p = hit.payload or {}
            boost = float(p.get("priority_boost", 1.0))
            try:
                dt = DocumentType(p.get("doc_type", "general"))
            except ValueError:
                dt = DocumentType.GENERAL
            try:
                src = DocumentSource(p.get("source", "base_corpus"))
            except ValueError:
                src = DocumentSource.BASE_CORPUS

            out.append(RetrievedChunk(
                doc_id=p.get("doc_id", ""),
                chunk_id=p.get("chunk_str_id", ""),
                text=p.get("text", ""),
                doc_type=dt,
                source=src,
                title=p.get("title", "Unknown"),
                filename=p.get("filename", ""),
                raw_score=float(hit.score),
                boosted_score=float(hit.score) * boost,
                page_number=p.get("page_number"),
                metadata=p,
            ))

        # dedupe by chunk_id keeping highest boosted_score
        seen: dict[str, RetrievedChunk] = {}
        for c in out:
            key = c.chunk_id or c.text[:60]
            if key not in seen or c.boosted_score > seen[key].boosted_score:
                seen[key] = c
        return list(seen.values())[:top_k]

    async def rerank_chunks(
        self, query: str, candidates: list[RetrievedChunk], top_n: int = 6,
    ) -> list[RetrievedChunk]:
        """Cross-encoder re-rank. Boost still applied multiplicatively to the rerank score."""
        if not candidates:
            return []
        passages = [c.text for c in candidates]
        rerank_scores = await rerank(query, passages)
        # Normalize rerank scores to [0, 1] using min-max (or just shift) — they're logits from MS-MARCO.
        if rerank_scores:
            lo = min(rerank_scores)
            hi = max(rerank_scores)
            span = (hi - lo) or 1.0
            for c, s in zip(candidates, rerank_scores):
                normalized = (s - lo) / span  # 0..1
                c.raw_score = float(normalized)
                boost = float(c.metadata.get("priority_boost", 1.0)) if c.metadata else 1.0
                c.boosted_score = normalized * boost
        ranked = sorted(candidates, key=lambda x: x.boosted_score, reverse=True)
        return ranked[:top_n]

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
