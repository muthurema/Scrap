"""
backfill_chunk_metadata.py
==========================

One-time backfill for chunks ingested before v3.8 — they're missing
`tier` and/or `freshness_ts` in their Qdrant payload. The retriever has
a fallback (`_infer_tier_from_source`) for missing tier, but it's safer
and faster to materialise the fields.

What this script does:
  1. Scrolls every point in each Qdrant collection.
  2. For any point whose payload lacks `tier`, computes it from the
     `source` field using the same SOURCE_TO_TIER mapping the retriever
     uses (`global` / `regional` / `company`).
  3. For any point whose payload lacks `freshness_ts`, fills it from the
     parent document's `ingested_at` or `created_at` in Mongo.
  4. Uses Qdrant's `set_payload` to update ONLY the missing keys — the
     dense + sparse vectors are untouched (no re-embedding cost).

Idempotent: re-running just skips points that already have both fields.

Usage:
    MONGO_URL=mongodb://...  DB_NAME=ehsrag  \
    QDRANT_URL=http://qdrant.railway.internal:8080 \
    python /app/backend/backfill_chunk_metadata.py

Local file-mode (dev):
    MONGO_URL=...  DB_NAME=...  python /app/backend/backfill_chunk_metadata.py
    (uses /app/backend/qdrant_data when QDRANT_URL is unset)
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient
from qdrant_client import QdrantClient

# Reuse the same mapping the live retriever uses — so backfilled tiers
# match exactly what new uploads stamp at ingest time.
from app.config import SOURCE_TO_TIER, KnowledgeTier  # type: ignore


MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")
QDRANT_URL = os.environ.get("QDRANT_URL")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY")
QDRANT_PATH = os.environ.get("QDRANT_PATH", "/app/backend/qdrant_data")
COLLECTIONS = os.environ.get(
    "BACKFILL_COLLECTIONS", "ehs_company_docs,ehs_base_knowledge",
).split(",")
BATCH = int(os.environ.get("BACKFILL_BATCH", "200"))


def _fail(msg: str):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def _qdrant() -> QdrantClient:
    if QDRANT_URL:
        kwargs = {"url": QDRANT_URL}
        if QDRANT_API_KEY:
            kwargs["api_key"] = QDRANT_API_KEY
        return QdrantClient(**kwargs)
    return QdrantClient(path=QDRANT_PATH)


def _tier_for(source: str) -> str:
    """Map a DocumentSource string to its tier string. Falls back to
    'global' for unknown sources (matches retriever behaviour)."""
    for src_enum, tier_enum in SOURCE_TO_TIER.items():
        if src_enum.value == source:
            return tier_enum.value
    return KnowledgeTier.GLOBAL.value


async def _load_doc_freshness_map(db) -> dict[str, str]:
    """Fetch every document's id → freshness_ts (ISO string) in one go.

    Prefers `ingested_at` (set when ingestion finished), falls back to
    `created_at`, then `processed_at`."""
    cursor = db["documents"].find(
        {}, {"_id": 0, "id": 1, "ingested_at": 1, "created_at": 1, "processed_at": 1},
    )
    out = {}
    async for d in cursor:
        ts = d.get("ingested_at") or d.get("processed_at") or d.get("created_at")
        if ts:
            out[d["id"]] = ts if isinstance(ts, str) else ts.isoformat()
        else:
            # Fallback so we never leave a chunk with no freshness — use
            # NOW so retriever doesn't downrank it unfairly.
            out[d["id"]] = datetime.now(timezone.utc).isoformat()
    return out


def backfill_collection(qc: QdrantClient, name: str, freshness_map: dict[str, str]):
    print(f"\n→ {name}")
    offset = None
    updated = 0
    skipped = 0
    scanned = 0
    try:
        qc.get_collection(name)
    except Exception:
        print("  · collection missing on this Qdrant — skip")
        return
    while True:
        records, next_offset = qc.scroll(
            collection_name=name,
            limit=BATCH,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        if not records:
            break
        for r in records:
            scanned += 1
            p = r.payload or {}
            patch = {}
            if not p.get("tier"):
                src = p.get("source") or ""
                patch["tier"] = _tier_for(src)
            if not p.get("freshness_ts"):
                doc_id = p.get("doc_id")
                if doc_id and doc_id in freshness_map:
                    patch["freshness_ts"] = freshness_map[doc_id]
                else:
                    # No parent doc found (could happen if doc was
                    # deleted but chunks orphaned) — stamp now.
                    patch["freshness_ts"] = datetime.now(timezone.utc).isoformat()
            if patch:
                qc.set_payload(collection_name=name, payload=patch, points=[r.id])
                updated += 1
            else:
                skipped += 1
        if next_offset is None:
            break
        offset = next_offset
    print(f"  · scanned={scanned}  updated={updated}  already-tagged={skipped}")


async def main():
    if not MONGO_URL or not DB_NAME:
        _fail("MONGO_URL and DB_NAME must be set")

    mongo = AsyncIOMotorClient(MONGO_URL)
    db = mongo[DB_NAME]
    print("Loading document freshness map from Mongo…")
    freshness_map = await _load_doc_freshness_map(db)
    print(f"  · {len(freshness_map)} documents indexed")

    qc = _qdrant()
    try:
        cols = [c.name for c in qc.get_collections().collections]
        print(f"Qdrant collections seen: {cols}")
    except Exception as e:
        _fail(f"Cannot list Qdrant collections: {e}")

    for name in COLLECTIONS:
        name = name.strip()
        if not name:
            continue
        backfill_collection(qc, name, freshness_map)

    mongo.close()
    print("\nAll done.")


if __name__ == "__main__":
    asyncio.run(main())
