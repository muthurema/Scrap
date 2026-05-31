"""Chat routes — non-streaming + SSE streaming (sources-first), with user profile awareness + SME corrections."""
import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.db import chat_sessions_col, chat_messages_col, users_col
from app.schemas import ChatMessageIn, ChatMessageOut, ChatSessionOut, SourceReference
from app.auth import get_current_user
from app.vector_store import get_vector_store
from app.rag_engine import RAGEngine
from app.security import sanitize_user_query, has_injection_signal, detect_pii
from app.escalation import is_high_risk
from app.audit import audit
from app.routes.feedback_routes import get_relevant_annotations

router = APIRouter(prefix="/chat", tags=["Chat"])


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(value):
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return value or datetime.now(timezone.utc)


async def _ensure_session(payload: ChatMessageIn, current_user: dict) -> str:
    """
    Either resolves an existing session (verifying the caller owns it) OR creates a fresh one.
    Returns 404 if the session does not exist; 403 if it exists but belongs to a different user.
    """
    session_id = payload.session_id
    now = _now_iso()
    if session_id:
        session = await chat_sessions_col().find_one({"id": session_id})
        if not session:
            raise HTTPException(404, "Chat session not found")
        if session.get("user_id") != current_user.get("sub"):
            raise HTTPException(403, "You don't have access to this chat session")
        return session_id
    session_id = str(uuid.uuid4())
    await chat_sessions_col().insert_one({
        "id": session_id, "user_id": current_user.get("sub"),
        "company_id": current_user.get("company_id"),
        "title": payload.content[:60], "created_at": now, "updated_at": now,
    })
    return session_id


async def _load_history(session_id: str, limit: int = 20) -> list[dict]:
    rows = await chat_messages_col().find(
        {"session_id": session_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(limit)
    return [{"role": m["role"], "content": m["content"]} for m in rows]


@router.post("/", response_model=ChatMessageOut)
async def chat(payload: ChatMessageIn, request: Request, current_user: dict = Depends(get_current_user)):
    session_id = await _ensure_session(payload, current_user)
    history = await _load_history(session_id)

    profile = await users_col().find_one({"id": current_user["sub"]}, {"_id": 0, "jurisdiction": 1})
    user_juris = (profile or {}).get("jurisdiction")
    sme_corrections = await get_relevant_annotations(payload.content)

    rag = RAGEngine(get_vector_store())
    answer, chunks, retrieval_meta = await rag.answer(
        query=payload.content, session_id=session_id, history=history,
        company_id=current_user.get("company_id"),
        user_jurisdiction=user_juris,
        sme_corrections=sme_corrections,
    )
    sources = rag.chunks_to_sources(chunks)
    avg_score = (sum(c.boosted_score for c in chunks) / len(chunks)) if chunks else None
    followups = await rag.suggest_followups(payload.content, answer)
    high_risk = is_high_risk(payload.content)

    user_msg_id = str(uuid.uuid4())
    assistant_msg_id = str(uuid.uuid4())
    created_at = _now_iso()

    await chat_messages_col().insert_many([
        {"id": user_msg_id, "session_id": session_id, "role": "user",
         "content": payload.content, "sources": [], "confidence_score": None,
         "pii_categories": detect_pii(payload.content),
         "injection_signal": retrieval_meta.get("injection_signal", False),
         "created_at": created_at},
        {"id": assistant_msg_id, "session_id": session_id, "role": "assistant",
         "content": answer, "sources": [s.model_dump(mode="json") for s in sources],
         "confidence_score": avg_score, "retrieval_meta": retrieval_meta,
         "is_high_risk": high_risk, "suggested_followups": followups,
         "created_at": created_at},
    ])
    await chat_sessions_col().update_one(
        {"id": session_id}, {"$set": {"updated_at": created_at}}
    )

    return ChatMessageOut(
        message_id=assistant_msg_id, session_id=session_id, role="assistant",
        content=answer, sources=sources, confidence_score=avg_score,
        is_high_risk=high_risk, suggested_followups=followups,
        created_at=datetime.fromisoformat(created_at),
    )


# ── Streaming (SSE) ──────────────────────────────────────────────────────────

@router.post("/stream")
async def chat_stream(payload: ChatMessageIn, request: Request, current_user: dict = Depends(get_current_user)):
    # Validate any attached images BEFORE we open the SSE response so errors return a normal 4xx
    images_b64 = []
    if payload.images:
        from app.vision import parse_data_urls
        try:
            images_b64 = parse_data_urls(payload.images)
        except ValueError as ve:
            raise HTTPException(400, str(ve))

    session_id = await _ensure_session(payload, current_user)
    history = await _load_history(session_id)
    rag = RAGEngine(get_vector_store())

    profile = await users_col().find_one({"id": current_user["sub"]}, {"_id": 0, "jurisdiction": 1})
    user_juris = (profile or {}).get("jurisdiction")
    sme_corrections = await get_relevant_annotations(payload.content)

    user_msg_id = str(uuid.uuid4())
    assistant_msg_id = str(uuid.uuid4())
    created_at = _now_iso()
    final_text_holder: dict = {"text": "", "sources": [], "confidence_score": None, "meta": {},
                                "followups": [], "high_risk": False}

    async def event_gen():
        # Force Railway/Cloudflare/Envoy to flush headers + initial bytes
        # immediately by padding with a comment line. SSE spec says lines
        # starting with `:` are comments and ignored by the client.
        # 2KB pad defeats most proxy buffer-until-2KB heuristics.
        yield ":" + (" " * 2048) + "\n\n"
        yield f"event: session\ndata: {json.dumps({'session_id': session_id, 'message_id': assistant_msg_id})}\n\n"

        # Keepalive ping every 2s — keeps the response from idling out at the
        # proxy AND forces TCP to flush. Runs in parallel with the RAG stream.
        ping_stop = asyncio.Event()

        async def keepalive_pings(queue: asyncio.Queue):
            try:
                while not ping_stop.is_set():
                    try:
                        await asyncio.wait_for(ping_stop.wait(), timeout=2.0)
                    except asyncio.TimeoutError:
                        await queue.put(":ping\n\n")
            except asyncio.CancelledError:
                pass

        # Merge keepalive pings + real stream events through a queue so each
        # `yield` is a single coherent SSE frame.
        queue: asyncio.Queue = asyncio.Queue()
        SENTINEL = object()

        async def produce_events():
            try:
                async for event in rag.stream(
                    query=payload.content,
                    session_id=session_id,
                    history=history,
                    company_id=current_user.get("company_id"),
                    user_jurisdiction=user_juris,
                    sme_corrections=sme_corrections,
                    images_b64=images_b64 or None,
                ):
                    etype = event["type"]
                    data = event.get("data")
                    if etype == "sources":
                        # The LLM still gets the full retrieved context
                        # (global + regional + company) so answer quality
                        # stays high — but the UI only shows the user
                        # SOURCES THEY CAN ACT ON: i.e. their OWN company's
                        # docs. We must match BOTH tier=company AND
                        # company_id=current_user.company_id — filtering on
                        # tier alone would leak Acme's chunks to a Beta
                        # admin (or to a superadmin with no company).
                        caller_company_id = current_user.get("company_id")
                        all_sources = data or []
                        if caller_company_id:
                            company_sources = [
                                s for s in all_sources
                                if s.get("tier") == "company"
                                and s.get("company_id") == caller_company_id
                            ]
                        else:
                            # Superadmin / user without a company: no
                            # "their" company → zero company sources. The
                            # external_count summary still shows; the LLM
                            # still uses the full retrieved context.
                            company_sources = []
                        external_count = len(all_sources) - len(company_sources)
                        # Persist the FULL list to Mongo (for audit) but
                        # send only the filtered view down the wire.
                        final_text_holder["sources"] = data
                        final_text_holder["meta"] = event.get("retrieval_meta", {})
                        final_text_holder["high_risk"] = event.get("retrieval_meta", {}).get("high_risk", False)
                        wire_payload = {
                            "sources": company_sources,
                            "external_count": external_count,
                        }
                        await queue.put(f"event: sources\ndata: {json.dumps(wire_payload)}\n\n")
                    elif etype == "token":
                        await queue.put(f"event: token\ndata: {json.dumps(data)}\n\n")
                    elif etype == "done":
                        final_text_holder["text"] = data.get("final_text", "")
                        final_text_holder["confidence_score"] = data.get("confidence_score")
                        final_text_holder["followups"] = data.get("suggested_followups", [])
                        await queue.put(f"event: done\ndata: {json.dumps(data)}\n\n")
                    elif etype == "error":
                        await queue.put(f"event: error\ndata: {json.dumps({'message': data})}\n\n")
            finally:
                await queue.put(SENTINEL)

        producer = asyncio.create_task(produce_events())
        pinger = asyncio.create_task(keepalive_pings(queue))
        try:
            while True:
                item = await queue.get()
                if item is SENTINEL:
                    break
                yield item
        finally:
            ping_stop.set()
            pinger.cancel()
            try:
                await pinger
            except (asyncio.CancelledError, Exception):
                pass
            if not producer.done():
                producer.cancel()
                try:
                    await producer
                except (asyncio.CancelledError, Exception):
                    pass
            try:
                await chat_messages_col().insert_many([
                    {"id": user_msg_id, "session_id": session_id, "role": "user",
                     "content": payload.content, "sources": [], "confidence_score": None,
                     "pii_categories": detect_pii(payload.content),
                     "injection_signal": final_text_holder["meta"].get("injection_signal", False),
                     "has_images": bool(images_b64),
                     "image_count": len(images_b64),
                     "created_at": created_at},
                    {"id": assistant_msg_id, "session_id": session_id, "role": "assistant",
                     "content": final_text_holder["text"],
                     "sources": final_text_holder["sources"],
                     "confidence_score": final_text_holder["confidence_score"],
                     "retrieval_meta": final_text_holder["meta"],
                     "is_high_risk": final_text_holder["high_risk"],
                     "suggested_followups": final_text_holder["followups"],
                     "created_at": _now_iso()},
                ])
                await chat_sessions_col().update_one(
                    {"id": session_id}, {"$set": {"updated_at": _now_iso()}}
                )
            except Exception:
                pass

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.get("/sessions", response_model=list[ChatSessionOut])
async def list_sessions(current_user: dict = Depends(get_current_user)):
    sessions = await chat_sessions_col().find(
        {"user_id": current_user.get("sub")}, {"_id": 0}
    ).sort("updated_at", -1).limit(50).to_list(50)

    out = []
    for s in sessions:
        count = await chat_messages_col().count_documents({"session_id": s["id"]})
        out.append(ChatSessionOut(
            id=s["id"], title=s.get("title"),
            created_at=_parse_dt(s["created_at"]),
            updated_at=_parse_dt(s["updated_at"]),
            message_count=count,
        ))
    return out


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageOut])
async def get_messages(session_id: str, current_user: dict = Depends(get_current_user)):
    # Ownership check — prevent IDOR
    session = await chat_sessions_col().find_one({"id": session_id}, {"_id": 0, "user_id": 1})
    if not session:
        raise HTTPException(404, "Session not found")
    if session.get("user_id") != current_user.get("sub"):
        raise HTTPException(403, "You don't have access to this chat session")

    msgs = await chat_messages_col().find(
        {"session_id": session_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(1000)
    return [
        ChatMessageOut(
            message_id=m["id"], session_id=m["session_id"], role=m["role"],
            content=m["content"],
            sources=[SourceReference(**s) for s in (m.get("sources") or [])],
            confidence_score=m.get("confidence_score"),
            feedback=m.get("feedback"),
            is_high_risk=m.get("is_high_risk", False),
            suggested_followups=m.get("suggested_followups", []),
            acknowledged_at=_parse_dt(m.get("acknowledged_at")) if m.get("acknowledged_at") else None,
            created_at=_parse_dt(m["created_at"]),
        )
        for m in msgs
    ]


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    res = await chat_sessions_col().delete_one({"id": session_id, "user_id": current_user["sub"]})
    if res.deleted_count == 0:
        raise HTTPException(404, "Session not found")
    await chat_messages_col().delete_many({"session_id": session_id})
    await audit(user=current_user, action="delete_chat_session", resource_type="chat_session",
                resource_id=session_id, request=request)


@router.delete("/sessions", status_code=200)
async def delete_all_sessions(request: Request, current_user: dict = Depends(get_current_user)):
    """Delete every session + message owned by the current user."""
    sessions = await chat_sessions_col().find(
        {"user_id": current_user["sub"]}, {"_id": 0, "id": 1}
    ).to_list(None)
    session_ids = [s["id"] for s in sessions]
    if not session_ids:
        return {"deleted_sessions": 0, "deleted_messages": 0}
    msg_res = await chat_messages_col().delete_many({"session_id": {"$in": session_ids}})
    sess_res = await chat_sessions_col().delete_many({"user_id": current_user["sub"]})
    await audit(user=current_user, action="delete_all_chat_sessions", resource_type="chat_session",
                resource_id=None, request=request,
                details={"deleted_sessions": sess_res.deleted_count, "deleted_messages": msg_res.deleted_count})
    return {"deleted_sessions": sess_res.deleted_count, "deleted_messages": msg_res.deleted_count}


@router.delete("/messages/{message_id}", status_code=200)
async def delete_message(message_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    """
    Delete an individual message. If it is a user message, also delete the immediately
    following assistant message (the Q&A pair). If it is an assistant message, delete the
    preceding user message too. Acknowledged assistant messages cannot be deleted (compliance).
    """
    msg = await chat_messages_col().find_one({"id": message_id}, {"_id": 0})
    if not msg:
        raise HTTPException(404, "Message not found")

    # Ownership check via session
    session = await chat_sessions_col().find_one({"id": msg["session_id"], "user_id": current_user["sub"]}, {"_id": 0, "id": 1})
    if not session:
        raise HTTPException(403, "Not allowed")

    if msg.get("acknowledged_at"):
        raise HTTPException(409, "This message has been compliance-acknowledged and cannot be deleted")

    # Find sibling message in the Q&A pair (same session, adjacent created_at)
    session_id = msg["session_id"]
    role = msg["role"]
    created_at = msg["created_at"]
    sibling = None
    if role == "user":
        sibling = await chat_messages_col().find_one(
            {"session_id": session_id, "role": "assistant", "created_at": {"$gte": created_at}, "id": {"$ne": message_id}},
            {"_id": 0}, sort=[("created_at", 1)],
        )
    else:
        sibling = await chat_messages_col().find_one(
            {"session_id": session_id, "role": "user", "created_at": {"$lte": created_at}, "id": {"$ne": message_id}},
            {"_id": 0}, sort=[("created_at", -1)],
        )

    ids_to_delete = [message_id]
    if sibling and not sibling.get("acknowledged_at"):
        ids_to_delete.append(sibling["id"])

    res = await chat_messages_col().delete_many({"id": {"$in": ids_to_delete}})
    await chat_sessions_col().update_one(
        {"id": session_id}, {"$set": {"updated_at": _now_iso()}}
    )
    await audit(user=current_user, action="delete_chat_message", resource_type="chat_message",
                resource_id=message_id, request=request,
                details={"deleted_count": res.deleted_count, "session_id": session_id})
    return {"deleted": res.deleted_count}


@router.post("/sessions/{session_id}/followups")
async def generate_followups(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Lazy follow-up generator. Called by the frontend AFTER the /chat/stream
    `done` event so the user sees the answer immediately. Cached on the
    assistant message so the call is idempotent. Returns within ~5-10s
    (Claude latency) but the user is already reading the answer.
    """
    session = await chat_sessions_col().find_one(
        {"id": session_id, "user_id": current_user["sub"]}, {"_id": 0, "id": 1},
    )
    if not session:
        raise HTTPException(404, "Session not found")

    # Find the most recent Q→A pair
    msgs = await chat_messages_col().find(
        {"session_id": session_id}, {"_id": 0},
    ).sort("created_at", -1).limit(2).to_list(2)
    if len(msgs) < 2:
        return {"followups": []}
    assistant_msg, user_msg = msgs[0], msgs[1]
    if assistant_msg.get("role") != "assistant" or user_msg.get("role") != "user":
        return {"followups": []}

    # Idempotent: return cached if already generated
    cached = assistant_msg.get("suggested_followups") or []
    if cached:
        return {"followups": cached, "cached": True}

    rag = RAGEngine(get_vector_store())
    followups = await rag.suggest_followups(
        query=user_msg.get("content", ""),
        answer=assistant_msg.get("content", ""),
    )
    await chat_messages_col().update_one(
        {"id": assistant_msg["id"]},
        {"$set": {"suggested_followups": followups}},
    )
    return {"followups": followups, "cached": False}
