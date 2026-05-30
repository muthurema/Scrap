"""Feedback routes — thumbs up/down + superadmin review queue with annotations."""
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.db import chat_messages_col, db
from app.schemas import FeedbackIn, FeedbackAnnotateIn
from app.auth import get_current_user, require_superadmin
from app.audit import audit


def feedback_col():
    return db.feedback


router = APIRouter(prefix="/feedback", tags=["Feedback"])


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(v):
    if isinstance(v, str):
        return datetime.fromisoformat(v)
    return v


async def ensure_feedback_indexes():
    await feedback_col().create_index([("created_at", -1)])
    await feedback_col().create_index([("rating", 1), ("annotation", 1)])
    await feedback_col().create_index([("message_id", 1)])


@router.post("/{message_id}")
async def submit_feedback(
    message_id: str, payload: FeedbackIn, request: Request,
    current_user: dict = Depends(get_current_user),
):
    msg = await chat_messages_col().find_one({"id": message_id})
    if not msg or msg.get("role") != "assistant":
        raise HTTPException(404, "Assistant message not found")

    # Upsert feedback (one row per message_id; users can change their rating)
    existing = await feedback_col().find_one({"message_id": message_id})
    if existing:
        await feedback_col().update_one(
            {"message_id": message_id},
            {"$set": {"rating": payload.rating, "comment": payload.comment, "updated_at": _now_iso()}},
        )
        fid = existing["id"]
    else:
        fid = str(uuid.uuid4())
        await feedback_col().insert_one({
            "id": fid,
            "message_id": message_id,
            "session_id": msg["session_id"],
            "user_id": current_user.get("sub"),
            "user_email": current_user.get("email"),
            "company_id": current_user.get("company_id"),
            "rating": payload.rating,
            "comment": payload.comment,
            "annotation": None,
            "annotated_by": None,
            "is_reviewed": False,
            "user_query": "",  # filled below
            "assistant_answer": (msg.get("content") or "")[:2000],
            "sources": msg.get("sources", []),
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        })
        # Fill user_query from the previous user message in session
        prev = await chat_messages_col().find(
            {"session_id": msg["session_id"], "role": "user",
             "created_at": {"$lte": msg["created_at"]}},
            {"_id": 0},
        ).sort("created_at", -1).limit(1).to_list(1)
        if prev:
            await feedback_col().update_one(
                {"id": fid},
                {"$set": {"user_query": prev[0].get("content", "")[:500]}},
            )

    await chat_messages_col().update_one({"id": message_id}, {"$set": {"feedback": payload.rating}})
    await audit(user=current_user, action="submit_feedback", resource_type="chat_message",
                resource_id=message_id, request=request, details={"rating": payload.rating})
    return {"id": fid, "rating": payload.rating}


@router.get("/queue")
async def review_queue(
    rating: Optional[str] = Query("down"),
    reviewed: Optional[bool] = Query(False),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(require_superadmin),
):
    query = {}
    if rating:
        query["rating"] = rating
    if reviewed is not None:
        query["is_reviewed"] = reviewed
    items = await feedback_col().find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    for it in items:
        it["created_at"] = _parse_dt(it.get("created_at"))
        if it.get("updated_at"):
            it["updated_at"] = _parse_dt(it["updated_at"])
    total = await feedback_col().count_documents(query)
    return {"items": items, "total": total}


@router.post("/{feedback_id}/annotate")
async def annotate(
    feedback_id: str, payload: FeedbackAnnotateIn, request: Request,
    current_user: dict = Depends(require_superadmin),
):
    res = await feedback_col().update_one(
        {"id": feedback_id},
        {"$set": {
            "annotation": payload.annotation,
            "annotated_by": current_user.get("email"),
            "annotated_at": _now_iso(),
            "is_reviewed": True,
        }},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Feedback not found")
    await audit(user=current_user, action="annotate_feedback", resource_type="feedback",
                resource_id=feedback_id, request=request,
                details={"annotation_len": len(payload.annotation)})
    return {"ok": True}


@router.delete("/{feedback_id}", status_code=204)
async def delete_feedback(feedback_id: str, request: Request, current_user: dict = Depends(require_superadmin)):
    res = await feedback_col().delete_one({"id": feedback_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Feedback not found")
    await audit(user=current_user, action="delete_feedback", resource_type="feedback",
                resource_id=feedback_id, request=request)


async def get_relevant_annotations(query_text: str, limit: int = 3) -> list[dict]:
    """
    Return SME annotations for past similar queries (heuristic match on shared terms).
    Used to inject 'human correction' context into the RAG prompt.
    """
    # Cheap heuristic: pick reviewed thumbs-down items whose user_query shares ≥2 lowercase words with the new query.
    words = {w for w in (query_text or "").lower().split() if len(w) > 3}
    if not words:
        return []
    items = await feedback_col().find(
        {"is_reviewed": True, "rating": "down", "annotation": {"$ne": None}}, {"_id": 0},
    ).sort("created_at", -1).limit(50).to_list(50)
    scored = []
    for it in items:
        q_words = {w for w in (it.get("user_query") or "").lower().split() if len(w) > 3}
        overlap = len(words & q_words)
        if overlap >= 2:
            scored.append((overlap, it))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [it for _, it in scored[:limit]]
