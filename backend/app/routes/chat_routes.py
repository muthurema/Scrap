"""Chat routes."""
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException

from app.db import chat_sessions_col, chat_messages_col
from app.schemas import ChatMessageIn, ChatMessageOut, ChatSessionOut, SourceReference
from app.auth import get_current_user
from app.vector_store import get_vector_store
from app.rag_engine import RAGEngine

router = APIRouter(prefix="/chat", tags=["Chat"])


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(value):
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return value or datetime.now(timezone.utc)


@router.post("/", response_model=ChatMessageOut)
async def chat(payload: ChatMessageIn, current_user: dict = Depends(get_current_user)):
    user_id = current_user.get("sub")
    company_id = current_user.get("company_id")

    # session
    session_id = payload.session_id
    now = _now_iso()
    if session_id:
        session = await chat_sessions_col().find_one({"id": session_id})
        if not session:
            raise HTTPException(404, "Chat session not found")
    else:
        session_id = str(uuid.uuid4())
        await chat_sessions_col().insert_one({
            "id": session_id, "user_id": user_id, "company_id": company_id,
            "title": payload.content[:60], "created_at": now, "updated_at": now,
        })

    # history
    history_rows = await chat_messages_col().find(
        {"session_id": session_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(20)
    history = [{"role": m["role"], "content": m["content"]} for m in history_rows]

    # RAG
    rag = RAGEngine(get_vector_store())
    answer, chunks = await rag.answer(
        query=payload.content, session_id=session_id, history=history, company_id=company_id,
    )
    sources = rag.chunks_to_sources(chunks)
    avg_score = (sum(c.boosted_score for c in chunks) / len(chunks)) if chunks else None

    user_msg_id = str(uuid.uuid4())
    assistant_msg_id = str(uuid.uuid4())
    created_at = _now_iso()

    await chat_messages_col().insert_many([
        {"id": user_msg_id, "session_id": session_id, "role": "user",
         "content": payload.content, "sources": [], "confidence_score": None,
         "created_at": created_at},
        {"id": assistant_msg_id, "session_id": session_id, "role": "assistant",
         "content": answer, "sources": [s.model_dump(mode="json") for s in sources],
         "confidence_score": avg_score, "created_at": created_at},
    ])
    await chat_sessions_col().update_one(
        {"id": session_id}, {"$set": {"updated_at": created_at}}
    )

    return ChatMessageOut(
        message_id=assistant_msg_id, session_id=session_id, role="assistant",
        content=answer, sources=sources, confidence_score=avg_score,
        created_at=datetime.fromisoformat(created_at),
    )


@router.get("/sessions", response_model=list[ChatSessionOut])
async def list_sessions(current_user: dict = Depends(get_current_user)):
    user_id = current_user.get("sub")
    sessions = await chat_sessions_col().find(
        {"user_id": user_id}, {"_id": 0}
    ).sort("updated_at", -1).limit(50).to_list(50)

    out = []
    for s in sessions:
        count = await chat_messages_col().count_documents({"session_id": s["id"]})
        out.append(ChatSessionOut(
            id=s["id"],
            title=s.get("title"),
            created_at=_parse_dt(s["created_at"]),
            updated_at=_parse_dt(s["updated_at"]),
            message_count=count,
        ))
    return out


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageOut])
async def get_messages(session_id: str, current_user: dict = Depends(get_current_user)):
    msgs = await chat_messages_col().find(
        {"session_id": session_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(1000)
    return [
        ChatMessageOut(
            message_id=m["id"], session_id=m["session_id"], role=m["role"],
            content=m["content"],
            sources=[SourceReference(**s) for s in (m.get("sources") or [])],
            confidence_score=m.get("confidence_score"),
            created_at=_parse_dt(m["created_at"]),
        )
        for m in msgs
    ]


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, current_user: dict = Depends(get_current_user)):
    res = await chat_sessions_col().delete_one({"id": session_id, "user_id": current_user["sub"]})
    if res.deleted_count == 0:
        raise HTTPException(404, "Session not found")
    await chat_messages_col().delete_many({"session_id": session_id})
