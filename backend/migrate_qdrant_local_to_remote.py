"""
migrate_qdrant_local_to_remote.py
==================================

One-time migration: scrolls every chunk from a LOCAL file-mode Qdrant
(your old embedded `/app/backend/qdrant_data`) and upserts the points
into a REMOTE Qdrant service (your new Railway Qdrant service).

Idempotent: uses the original point IDs, so re-running this script
overwrites existing points with the same payload + vectors. Safe.

Usage (local dev or Railway shell):
    QDRANT_LOCAL_PATH=/app/backend/qdrant_data \
    QDRANT_REMOTE_URL=http://qdrant.railway.internal:8080 \
    python /app/backend/migrate_qdrant_local_to_remote.py

Optional:
    QDRANT_REMOTE_API_KEY=...    if you set QDRANT__SERVICE__API_KEY on the remote
    MIGRATE_BATCH=200            scroll/upsert batch size (default 200)
    MIGRATE_COLLECTIONS=ehs_company_docs,ehs_base_knowledge  comma-separated

Tip: run this BEFORE you set QDRANT_URL on the live backend so chats
hitting the new remote service have something to retrieve from.
"""
import os
import sys
import time

from qdrant_client import QdrantClient
from qdrant_client.models import (
    PointStruct, SparseVector,
    Distance, VectorParams, SparseVectorParams, SparseIndexParams,
)


LOCAL_PATH = os.environ.get("QDRANT_LOCAL_PATH", "/app/backend/qdrant_data")
REMOTE_URL = os.environ.get("QDRANT_REMOTE_URL") or os.environ.get("QDRANT_URL")
REMOTE_API_KEY = os.environ.get("QDRANT_REMOTE_API_KEY") or os.environ.get("QDRANT_API_KEY")
BATCH = int(os.environ.get("MIGRATE_BATCH", "200"))
COLLECTIONS = (
    os.environ.get("MIGRATE_COLLECTIONS", "ehs_company_docs,ehs_base_knowledge").split(",")
)
EMBED_DIM = int(os.environ.get("EMBEDDING_DIMENSIONS", "384"))
DENSE_NAME = "dense"
SPARSE_NAME = "sparse"


def _fail(msg: str):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def _ensure_collection(remote: QdrantClient, name: str):
    """Idempotent: create the hybrid collection if missing on the remote."""
    try:
        remote.get_collection(collection_name=name)
        print(f"  · collection '{name}' already exists on remote — will upsert into it")
        return
    except Exception:
        pass
    print(f"  · creating collection '{name}' on remote (hybrid: dense+sparse)")
    remote.create_collection(
        collection_name=name,
        vectors_config={DENSE_NAME: VectorParams(size=EMBED_DIM, distance=Distance.COSINE)},
        sparse_vectors_config={SPARSE_NAME: SparseVectorParams(index=SparseIndexParams())},
    )


def _point_from_scroll(record) -> PointStruct:
    """Rebuild a PointStruct from a Record returned by client.scroll().

    Local-mode scroll returns each Record with `id`, `payload`, and
    `vector` — `vector` is a dict-of-named-vectors when the collection
    has named vectors. Dense values are list[float]; sparse values are
    SparseVector instances OR plain dicts with `indices` + `values`
    depending on qdrant-client version.
    """
    vectors_in = record.vector or {}
    dense = vectors_in.get(DENSE_NAME)
    sparse = vectors_in.get(SPARSE_NAME)
    rebuilt: dict = {}
    if dense is not None:
        rebuilt[DENSE_NAME] = list(dense)
    if sparse is not None:
        if hasattr(sparse, "indices") and hasattr(sparse, "values"):
            rebuilt[SPARSE_NAME] = SparseVector(
                indices=list(sparse.indices), values=list(sparse.values)
            )
        elif isinstance(sparse, dict):
            rebuilt[SPARSE_NAME] = SparseVector(
                indices=list(sparse["indices"]), values=list(sparse["values"]),
            )
        else:
            # Unknown shape — skip sparse rather than crashing the run
            print(f"    [warn] point {record.id} has unrecognized sparse shape {type(sparse).__name__}")
    return PointStruct(id=record.id, vector=rebuilt, payload=record.payload or {})


def migrate_collection(local: QdrantClient, remote: QdrantClient, name: str):
    print(f"\n→ migrating collection: {name}")
    _ensure_collection(remote, name)

    offset = None
    total = 0
    t0 = time.time()
    while True:
        records, next_offset = local.scroll(
            collection_name=name,
            limit=BATCH,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        if not records:
            break
        points = [_point_from_scroll(r) for r in records]
        # Filter out any points where dense vector was missing (shouldn't
        # happen but defensive — upserting without the named vector would
        # break later retrieval).
        points = [p for p in points if isinstance(p.vector, dict) and DENSE_NAME in p.vector]
        if points:
            remote.upsert(collection_name=name, points=points)
            total += len(points)
            print(f"  · upserted batch of {len(points)} (cumulative: {total})")
        if next_offset is None:
            break
        offset = next_offset

    elapsed = time.time() - t0
    print(f"✓ done: {total} points migrated in {elapsed:.1f}s")


def main():
    if not REMOTE_URL:
        _fail("QDRANT_REMOTE_URL (or QDRANT_URL) must be set to the remote Qdrant endpoint")
    if not os.path.isdir(LOCAL_PATH):
        _fail(f"Local Qdrant path not found: {LOCAL_PATH}")

    print(f"Local path:     {LOCAL_PATH}")
    print(f"Remote URL:     {REMOTE_URL}")
    print(f"Collections:    {COLLECTIONS}")
    print(f"Batch size:     {BATCH}")
    print()

    local = QdrantClient(path=LOCAL_PATH)
    remote_kwargs = {"url": REMOTE_URL}
    if REMOTE_API_KEY:
        remote_kwargs["api_key"] = REMOTE_API_KEY
    remote = QdrantClient(**remote_kwargs)

    # Probe remote
    try:
        remote.get_collections()
    except Exception as e:
        _fail(f"Cannot reach remote Qdrant at {REMOTE_URL}: {e}")

    for name in COLLECTIONS:
        name = name.strip()
        if not name:
            continue
        try:
            migrate_collection(local, remote, name)
        except Exception as e:
            print(f"FAILED collection '{name}': {e}")
            # continue to next collection instead of bailing entirely

    print("\nAll done.")


if __name__ == "__main__":
    main()
