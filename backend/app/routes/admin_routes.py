"""Admin routes: stats, companies, Turnstile sync stub."""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException

from app.db import companies_col, documents_col, chat_sessions_col, chat_messages_col, web_sources_col, users_col
from app.schemas import CompanyCreate, CompanyOut, SystemStatsOut
from app.auth import require_superadmin

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
    from app.config import get_settings
    settings = get_settings()

    total_docs = await documents_col().count_documents({})
    company_docs = await documents_col().count_documents({"source": {"$in": ["superadmin", "turnstile_dms"]}})
    base_docs = await documents_col().count_documents({"source": "base_corpus"})

    # Sum chunk_count
    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$chunk_count"}}}]
    chunk_agg = await documents_col().aggregate(pipeline).to_list(1)
    doc_chunks = chunk_agg[0]["total"] if chunk_agg else 0
    # Plus web source chunks
    ws_pipeline = [{"$group": {"_id": None, "total": {"$sum": "$last_chunk_count"}}}]
    ws_agg = await web_sources_col().aggregate(ws_pipeline).to_list(1)
    ws_chunks = ws_agg[0]["total"] if ws_agg else 0

    total_sessions = await chat_sessions_col().count_documents({})
    total_messages = await chat_messages_col().count_documents({})
    total_web = await web_sources_col().count_documents({})
    total_pending = await web_sources_col().count_documents({"is_change_pending_review": True})
    total_users = await users_col().count_documents({})

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
