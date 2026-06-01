"""Admin routes: stats, companies, Turnstile sync stub, corpus re-seed."""
import sys
import uuid
from pathlib import Path
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request

from app.db import companies_col, documents_col, chat_sessions_col, chat_messages_col, web_sources_col, users_col
from app.schemas import CompanyCreate, CompanyOut, SystemStatsOut
from app.auth import require_superadmin
from app.audit import audit

# seed.py lives at /app/backend/seed.py (sibling of app/ package)
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

router = APIRouter(prefix="/admin", tags=["Admin"])


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(v):
    if isinstance(v, str):
        return datetime.fromisoformat(v)
    return v


@router.post("/companies", response_model=CompanyOut, status_code=201)
async def create_company(payload: CompanyCreate, current_user: dict = Depends(require_superadmin)):
    doc = {
        "id": str(uuid.uuid4()),
        "name": payload.name,
        "turnstile_instance_url": payload.turnstile_instance_url,
        "is_active": True,
        "created_at": _now_iso(),
    }
    await companies_col().insert_one(doc)
    return CompanyOut(
        id=doc["id"], name=doc["name"],
        turnstile_instance_url=doc["turnstile_instance_url"],
        is_active=doc["is_active"], created_at=_parse_dt(doc["created_at"]),
    )


@router.get("/companies", response_model=list[CompanyOut])
async def list_companies(current_user: dict = Depends(require_superadmin)):
    items = await companies_col().find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return [
        CompanyOut(
            id=c["id"], name=c["name"],
            turnstile_instance_url=c.get("turnstile_instance_url"),
            is_active=c.get("is_active", True),
            created_at=_parse_dt(c["created_at"]),
        ) for c in items
    ]


@router.get("/stats", response_model=SystemStatsOut)
async def stats(current_user: dict = Depends(require_superadmin)):
    from app.vector_store import get_vector_store
    from app.routes.feedback_routes import feedback_col

    total_docs = await documents_col().count_documents({"superseded_by_id": None})
    company_docs = await documents_col().count_documents({"source": {"$in": ["superadmin", "turnstile_dms"]}, "superseded_by_id": None})
    base_docs = await documents_col().count_documents({"source": "base_corpus", "superseded_by_id": None})

    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$chunk_count"}}}]
    chunk_agg = await documents_col().aggregate(pipeline).to_list(1)
    doc_chunks = chunk_agg[0]["total"] if chunk_agg else 0
    ws_pipeline = [{"$group": {"_id": None, "total": {"$sum": "$last_chunk_count"}}}]
    ws_agg = await web_sources_col().aggregate(ws_pipeline).to_list(1)
    ws_chunks = ws_agg[0]["total"] if ws_agg else 0

    total_sessions = await chat_sessions_col().count_documents({})
    total_messages = await chat_messages_col().count_documents({})
    total_web = await web_sources_col().count_documents({})
    total_pending = await web_sources_col().count_documents({"is_change_pending_review": True})
    total_users = await users_col().count_documents({})
    pending_fb = await feedback_col().count_documents({"rating": "down", "is_reviewed": False})

    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    expired = await documents_col().count_documents({"expiry_date": {"$lt": now_iso, "$ne": None}})

    vs = get_vector_store()
    qdrant_status = await vs.health()

    return SystemStatsOut(
        total_documents=total_docs,
        total_chunks_embedded=int(doc_chunks) + int(ws_chunks),
        total_chat_sessions=total_sessions,
        total_messages=total_messages,
        company_doc_count=company_docs,
        base_corpus_count=base_docs,
        qdrant_status=qdrant_status,
        total_web_sources=total_web,
        web_sources_pending_review=total_pending,
        total_users=total_users,
        pending_feedback=pending_fb,
        expired_documents=expired,
    )


@router.post("/sync/turnstile/{company_id}")
async def sync_turnstile(company_id: str, current_user: dict = Depends(require_superadmin)):
    """Stub: simulates Turnstile DMS sync — returns mock summary."""
    company = await companies_col().find_one({"id": company_id})
    if not company:
        raise HTTPException(404, "Company not found")
    return {
        "status": "completed",
        "company": company["name"],
        "summary": {"new": 0, "updated": 0, "skipped": 0, "errors": 0},
        "note": "Turnstile DMS sync is stubbed in this demo build. Wire the real API in app/services/turnstile_sync.py.",
    }


@router.post("/reseed-corpus")
async def reseed_corpus(
    request: Request,
    force: bool = False,
    current_user: dict = Depends(require_superadmin),
):
    """
    Re-runs the bundled base EHS corpus ingestion (OSHA confined space, ISO 45001, LOTO, JSA,
    GHS, hot work, RCA). Idempotent — skips documents whose title is already present.
    Use `?force=true` to delete the existing base-corpus docs first and re-ingest from scratch.
    Returns a stats summary.
    """
    try:
        from seed import reseed_base_corpus  # noqa
    except ImportError as e:
        raise HTTPException(500, f"seed module not available: {e}")

    stats = await reseed_base_corpus(force=force)
    await audit(
        user=current_user,
        action="reseed_base_corpus",
        resource_type="documents",
        request=request,
        details={"force": force, **{k: v for k, v in stats.items() if k != "errors"},
                 "error_count": len(stats.get("errors", []))},
    )
    return {"ok": True, "force": force, **stats}


@router.post("/qdrant/reset")
async def reset_qdrant_collection(
    request: Request,
    collection: str,
    confirm: bool = False,
    current_user: dict = Depends(require_superadmin),
):
    """
    Wipe + recreate a Qdrant collection. Use this to recover from index
    corruption — symptom in logs:
      "Dense/Sparse search in <coll> failed: operands could not be
       broadcast together with shapes (N,) (M,)"
    This usually happens when a background ingestion was killed mid-write
    (e.g. Railway OOM, container restart) and left the local on-disk
    Qdrant payload in an inconsistent state.

    Requires `confirm=true`. After reset, re-upload (or POST /admin/reseed-corpus
    for the base corpus) so the collection is repopulated cleanly.

    Allowed collection names: `ehs_base_knowledge`, `ehs_company_docs`.
    """
    from app.config import get_settings
    from app.vector_store import get_vector_store, DENSE_NAME, SPARSE_NAME
    from qdrant_client.models import (
        Distance, VectorParams, SparseVectorParams, SparseIndexParams,
    )
    import asyncio

    settings = get_settings()
    allowed = {settings.qdrant_collection_base, settings.qdrant_collection_company}
    if collection not in allowed:
        raise HTTPException(400, f"collection must be one of {sorted(allowed)}")
    if not confirm:
        raise HTTPException(400, "Pass ?confirm=true to wipe & recreate the collection")

    vs = get_vector_store()

    # Best-effort: clear the Mongo `documents` flags so the UI doesn't show
    # phantom indexed docs after the wipe. We only reset docs whose source
    # routed them to THIS collection (base_corpus → base, others → company).
    if collection == settings.qdrant_collection_base:
        doc_filter = {"source": "base_corpus"}
    else:
        doc_filter = {"source": {"$ne": "base_corpus"}}
    affected = await documents_col().update_many(
        doc_filter,
        {"$set": {"is_processed": False, "chunk_count": 0,
                  "processing_error": "Collection reset — re-upload required",
                  "processed_at": None}},
    )

    def _wipe_and_recreate():
        # delete_collection is the cleanest way to remove on-disk state for
        # qdrant local file mode. Then recreate with the same schema.
        try:
            vs.client.delete_collection(collection_name=collection)
        except Exception as e:
            # If the collection doesn't exist we still want to (re)create it
            logger = __import__("loguru").logger
            logger.warning(f"delete_collection {collection} skipped: {e}")
        vs.client.create_collection(
            collection_name=collection,
            vectors_config={DENSE_NAME: VectorParams(
                size=settings.embedding_dimensions, distance=Distance.COSINE,
            )},
            sparse_vectors_config={SPARSE_NAME: SparseVectorParams(index=SparseIndexParams())},
        )

    await asyncio.to_thread(_wipe_and_recreate)

    await audit(
        user=current_user, action="qdrant_reset", resource_type="qdrant_collection",
        resource_id=collection, request=request,
        details={"documents_invalidated": affected.modified_count},
    )
    return {
        "ok": True, "collection": collection,
        "documents_invalidated": affected.modified_count,
        "note": "Collection wiped & recreated. Re-upload affected documents "
                "(or POST /api/admin/reseed-corpus?force=true for base corpus).",
    }


@router.post("/smtp/test")
async def smtp_test(
    request: Request,
    to: str,
    current_user: dict = Depends(require_superadmin),
):
    """Send a real test email through the configured SMTP and surface the
    actual error if it fails. Unlike the password-reset endpoint (which
    silently swallows SMTP errors to prevent email enumeration), this one
    is superadmin-only and tells you exactly what went wrong.

    Usage from Railway shell:
        curl -X POST "$API/api/admin/smtp/test?to=you@example.com" \
             -H "Authorization: Bearer <superadmin token>"
    """
    import asyncio as _asyncio
    import os as _os
    from app.password_reset import _send_smtp_sync

    cfg = {
        "host": _os.environ.get("SMTP_HOST", "<unset>"),
        "port": _os.environ.get("SMTP_PORT", "587 (default)"),
        "username": _os.environ.get("SMTP_USERNAME", "<unset>"),
        "from": _os.environ.get("SMTP_FROM") or _os.environ.get("SMTP_USERNAME") or "<unset>",
        "use_tls": _os.environ.get("SMTP_USE_TLS", "true (default)"),
        "password_set": bool(_os.environ.get("SMTP_PASSWORD")),
    }
    if cfg["host"] == "<unset>" or cfg["username"] == "<unset>" or not cfg["password_set"]:
        return {
            "ok": False,
            "stage": "config",
            "error": "SMTP_HOST / SMTP_USERNAME / SMTP_PASSWORD are not all set in env",
            "config": cfg,
        }

    try:
        await _asyncio.to_thread(
            _send_smtp_sync,
            to,
            "EHS RAG — SMTP test",
            "<p>This is a test email from your EHS RAG instance.</p>",
            "This is a test email from your EHS RAG instance.\n",
        )
    except Exception as e:
        return {
            "ok": False,
            "stage": "send",
            "error": f"{type(e).__name__}: {e}",
            "config": cfg,
            "hints": [
                "Gmail: use an App Password (myaccount.google.com/apppasswords), NOT your login password",
                "Office365: ensure SMTP AUTH is enabled on the mailbox (admin center → mail settings)",
                "Port 587 needs SMTP_USE_TLS=true (STARTTLS); port 465 uses implicit TLS regardless of that flag",
                "SMTP_FROM should typically equal SMTP_USERNAME — providers reject mismatched From addresses",
                "If you see 'connection refused', Railway egress may be blocked — try a different SMTP provider",
            ],
        }
    await audit(user=current_user, action="smtp_test", resource_type="smtp",
                resource_id=to, request=request, details={"to": to})
    return {"ok": True, "config": cfg, "note": f"Sent test email to {to}. Check the inbox (and spam folder)."}
