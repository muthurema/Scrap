"""
Seed script: creates admin user + base EHS knowledge corpus.
Run: cd /app/backend && python seed.py
"""
import asyncio
import os
import uuid
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from app.db import users_col, documents_col
from app.auth import hash_password
from app.config import DocumentType, DocumentSource
from app.vector_store import get_vector_store
from app.ingestion import IngestionService


ADMIN_EMAIL = os.environ.get("SEED_ADMIN_EMAIL", os.environ.get("ADMIN_EMAIL", "admin@ehsrag.com"))
ADMIN_PASSWORD = os.environ.get("SEED_ADMIN_PASSWORD", os.environ.get("ADMIN_PASSWORD", "Admin@12345"))
ADMIN_FULL_NAME = os.environ.get("ADMIN_FULL_NAME", "EHS Superadmin")


BASE_CORPUS_DOCS = []


async def reseed_base_corpus(force: bool = False) -> dict:
    """
    Re-runs base corpus ingestion. Returns a stats dict.
    `force=True` re-ingests docs even if titles already exist (deletes the old base-corpus entries first).
    Used both by the CLI seed and by the admin API endpoint.
    """
    from app.config import DocumentSource as _DS

    ingestion = IngestionService(get_vector_store())

    if force:
        # Remove existing base-corpus docs + their chunks before re-ingesting
        old_docs = [d async for d in documents_col().find(
            {"source": _DS.BASE_CORPUS.value}, {"id": 1, "_id": 0}
        )]
        for d in old_docs:
            try:
                await ingestion.delete_document(d["id"])
            except Exception:
                pass
        if old_docs:
            await documents_col().delete_many({"source": _DS.BASE_CORPUS.value})

    existing_titles = {d["title"] async for d in documents_col().find(
        {"source": _DS.BASE_CORPUS.value}, {"title": 1, "_id": 0}
    )}

    stats = {"created": 0, "skipped": 0, "failed": 0, "total_chunks": 0, "errors": []}

    for entry in BASE_CORPUS_DOCS:
        if entry["title"] in existing_titles:
            stats["skipped"] += 1
            continue

        doc_id = str(uuid.uuid4())
        await documents_col().insert_one({
            "id": doc_id,
            "company_id": None,
            "filename": f"{doc_id}.txt",
            "original_filename": f"{entry['title']}.txt",
            "file_path": None,
            "file_type": "txt",
            "file_size_bytes": len(entry["text"]),
            "mime_type": "text/plain",
            "doc_type": entry["doc_type"].value,
            "source": _DS.BASE_CORPUS.value,
            "title": entry["title"],
            "description": None,
            "tags": [],
            "version": None,
            "is_processed": False,
            "chunk_count": 0,
            "uploaded_by": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "processed_at": None,
            "processing_error": None,
        })

        try:
            chunk_count, _ = await ingestion.ingest_document(
                file_bytes=entry["text"].encode("utf-8"),
                file_ext="txt",
                doc_id=doc_id,
                title=entry["title"],
                doc_type=entry["doc_type"],
                source=_DS.BASE_CORPUS,
                extra_metadata={"company_id": "", "filename": f"{entry['title']}.txt"},
            )
            await documents_col().update_one(
                {"id": doc_id},
                {"$set": {
                    "is_processed": True,
                    "chunk_count": chunk_count,
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                }},
            )
            stats["created"] += 1
            stats["total_chunks"] += chunk_count
        except Exception as e:
            stats["failed"] += 1
            stats["errors"].append({"title": entry["title"], "error": str(e)})
            await documents_col().update_one(
                {"id": doc_id},
                {"$set": {"processing_error": str(e)}},
            )

    return stats


async def main():
    print("=== EHS RAG Seed ===")

    # 1. Admin user
    existing = await users_col().find_one({"email": ADMIN_EMAIL})
    if existing:
        print(f"Admin user already exists: {ADMIN_EMAIL}")
        # Ensure superadmin role
        if existing.get("role") != "superadmin":
            await users_col().update_one({"email": ADMIN_EMAIL}, {"$set": {"role": "superadmin"}})
            print("  Promoted to superadmin")
    else:
        user_id = str(uuid.uuid4())
        await users_col().insert_one({
            "id": user_id,
            "email": ADMIN_EMAIL,
            "hashed_password": hash_password(ADMIN_PASSWORD),
            "full_name": ADMIN_FULL_NAME,
            "role": "superadmin",
            "company_id": None,
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        print(f"Created admin user: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")

    # 2. Base corpus ingestion
    stats = await reseed_base_corpus(force=False)
    print(f"  Created: {stats['created']}, Skipped (already exist): {stats['skipped']}, Failed: {stats['failed']}, Total chunks: {stats['total_chunks']}")
    for err in stats["errors"]:
        print(f"  FAILED: {err['title']} — {err['error']}")

    print("=== Seed complete ===")


if __name__ == "__main__":
    asyncio.run(main())
