"""Acknowledgement routes — user 'I understand' confirmation with snapshot for audit trail."""
import uuid
import csv
import io
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.db import db, chat_messages_col, users_col
from app.auth import get_current_user, require_superadmin
from app.audit import audit


def acks_col():
    return db.acknowledgements


router = APIRouter(prefix="/acknowledgements", tags=["Acknowledgements"])


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(v):
    if isinstance(v, str):
        return datetime.fromisoformat(v)
    return v


async def ensure_ack_indexes():
    await acks_col().create_index([("created_at", -1)])
    await acks_col().create_index([("user_id", 1), ("created_at", -1)])
    await acks_col().create_index([("message_id", 1), ("user_id", 1)], unique=True)


class AckIn(BaseModel):
    message_id: str


@router.post("/")
async def create_ack(payload: AckIn, request: Request, current_user: dict = Depends(get_current_user)):
    msg = await chat_messages_col().find_one({"id": payload.message_id, "role": "assistant"})
    if not msg:
        raise HTTPException(404, "Assistant message not found")

    # Capture user profile snapshot for audit
    profile = await users_col().find_one(
        {"id": current_user["sub"]},
        {"_id": 0, "site": 1, "role_label": 1, "jurisdiction": 1, "industry_sector": 1, "full_name": 1},
    ) or {}

    existing = await acks_col().find_one({"message_id": payload.message_id, "user_id": current_user["sub"]})
    if existing:
        return {"id": existing["id"], "acknowledged_at": _parse_dt(existing["created_at"]), "already": True}

    # Fetch matching user query for compliance context
    user_q = await chat_messages_col().find(
        {"session_id": msg["session_id"], "role": "user", "created_at": {"$lte": msg["created_at"]}},
        {"_id": 0, "content": 1},
    ).sort("created_at", -1).limit(1).to_list(1)
    user_query_text = (user_q[0]["content"] if user_q else "")[:1000]

    ack_id = str(uuid.uuid4())
    doc = {
        "id": ack_id,
        "message_id": payload.message_id,
        "session_id": msg["session_id"],
        "user_id": current_user["sub"],
        "user_email": current_user.get("email"),
        "user_full_name": profile.get("full_name"),
        "user_site": profile.get("site"),
        "user_role_label": profile.get("role_label"),
        "user_jurisdiction": profile.get("jurisdiction"),
        "user_industry": profile.get("industry_sector"),
        "company_id": current_user.get("company_id"),
        "user_query": user_query_text,
        # SNAPSHOT — preserve the answer + sources AT THIS MOMENT for audit trail
        "answer_snapshot": (msg.get("content") or "")[:5000],
        "sources_snapshot": msg.get("sources") or [],
        "confidence_snapshot": msg.get("confidence_score"),
        "is_high_risk": msg.get("is_high_risk", False),
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
        "created_at": _now_iso(),
    }
    await acks_col().insert_one(doc)

    # Mark the chat message itself so the user sees the acknowledged state on reload
    await chat_messages_col().update_one(
        {"id": payload.message_id},
        {"$set": {"acknowledged_at": doc["created_at"], "acknowledged_by": current_user["sub"]}},
    )

    await audit(
        user=current_user, action="acknowledge_message", resource_type="chat_message",
        resource_id=payload.message_id, request=request,
        details={"ack_id": ack_id, "high_risk": doc["is_high_risk"]},
    )

    return {"id": ack_id, "acknowledged_at": _parse_dt(doc["created_at"]), "already": False}


@router.get("/me")
async def my_acks(limit: int = Query(50, ge=1, le=200), current_user: dict = Depends(get_current_user)):
    items = await acks_col().find(
        {"user_id": current_user["sub"]}, {"_id": 0},
    ).sort("created_at", -1).limit(limit).to_list(limit)
    for it in items:
        it["created_at"] = _parse_dt(it.get("created_at"))
    return {"items": items, "total": await acks_col().count_documents({"user_id": current_user["sub"]})}


@router.get("/")
async def list_acks(
    limit: int = Query(100, ge=1, le=500),
    high_risk_only: bool = False,
    user_id: Optional[str] = None,
    current_user: dict = Depends(require_superadmin),
):
    query = {}
    if high_risk_only:
        query["is_high_risk"] = True
    if user_id:
        query["user_id"] = user_id
    items = await acks_col().find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    for it in items:
        it["created_at"] = _parse_dt(it.get("created_at"))
    return {"items": items, "total": await acks_col().count_documents(query)}


@router.get("/export/csv")
async def export_csv(
    high_risk_only: bool = False,
    current_user: dict = Depends(require_superadmin),
):
    query = {"is_high_risk": True} if high_risk_only else {}
    cursor = acks_col().find(query, {"_id": 0}).sort("created_at", -1).limit(10000)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "acknowledged_at", "user_email", "user_full_name", "user_role", "user_site",
        "user_jurisdiction", "is_high_risk", "user_query",
        "answer_excerpt", "confidence_score", "source_titles", "ip",
    ])
    async for ack in cursor:
        w.writerow([
            ack.get("created_at", ""),
            ack.get("user_email", ""),
            ack.get("user_full_name") or "",
            ack.get("user_role_label") or "",
            ack.get("user_site") or "",
            ack.get("user_jurisdiction") or "",
            "YES" if ack.get("is_high_risk") else "no",
            (ack.get("user_query") or "").replace("\n", " ")[:500],
            (ack.get("answer_snapshot") or "").replace("\n", " ")[:800],
            ack.get("confidence_snapshot") or "",
            " | ".join(s.get("title", "")[:60] for s in (ack.get("sources_snapshot") or [])[:5]),
            ack.get("ip") or "",
        ])

    csv_bytes = buf.getvalue().encode("utf-8")
    filename = f"cidsa-acknowledgements-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.csv"
    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
