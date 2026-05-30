"""Analytics routes — query stats, gaps, and dashboard data."""
from datetime import datetime, timezone, timedelta
from collections import Counter
from fastapi import APIRouter, Depends, Query

from app.db import chat_messages_col, documents_col
from app.routes.feedback_routes import feedback_col
from app.schemas import AnalyticsOut
from app.auth import require_superadmin

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/", response_model=AnalyticsOut)
async def analytics(
    days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(require_superadmin),
):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    # Fetch all user messages in window
    user_msgs = await chat_messages_col().find(
        {"role": "user", "created_at": {"$gte": cutoff}},
        {"_id": 0, "content": 1, "created_at": 1, "session_id": 1, "pii_categories": 1, "injection_signal": 1},
    ).to_list(5000)

    # Fetch all assistant messages in window
    asst_msgs = await chat_messages_col().find(
        {"role": "assistant", "created_at": {"$gte": cutoff}},
        {"_id": 0, "content": 1, "sources": 1, "confidence_score": 1, "created_at": 1, "session_id": 1, "feedback": 1},
    ).to_list(5000)

    # Top queries (top N user query prefixes)
    q_counter = Counter()
    for m in user_msgs:
        q = (m.get("content") or "")[:120].strip()
        if q:
            q_counter[q] += 1
    top_queries = [
        {"query": q, "count": c}
        for q, c in q_counter.most_common(15)
    ]

    # Match assistant msgs to user queries via session_id sequence — heuristic
    # Build session timeline
    session_pairs = {}
    for m in user_msgs:
        session_pairs.setdefault(m["session_id"], []).append({"t": m["created_at"], "q": m["content"], "kind": "u"})
    for m in asst_msgs:
        session_pairs.setdefault(m["session_id"], []).append({
            "t": m["created_at"], "content": m["content"], "sources": m.get("sources") or [],
            "score": m.get("confidence_score"), "feedback": m.get("feedback"), "kind": "a",
        })
    for sid in session_pairs:
        session_pairs[sid].sort(key=lambda x: x["t"])

    zero_result = []
    low_conf = []
    cited_doc_counter = Counter()
    feedback_pos = 0
    feedback_neg = 0
    for sid, events in session_pairs.items():
        for i, e in enumerate(events):
            if e["kind"] == "u" and i + 1 < len(events) and events[i+1]["kind"] == "a":
                a = events[i+1]
                if not a["sources"]:
                    zero_result.append({"query": e["q"][:120], "session_id": sid, "created_at": e["t"]})
                elif a["score"] is not None and a["score"] < 0.30:
                    low_conf.append({
                        "query": e["q"][:120], "session_id": sid,
                        "score": round(a["score"], 3), "created_at": e["t"],
                    })
                for s in a["sources"]:
                    cited_doc_counter[s.get("title", "Unknown")] += 1
                if a.get("feedback") == "up":
                    feedback_pos += 1
                elif a.get("feedback") == "down":
                    feedback_neg += 1

    top_cited = [{"title": t, "count": c} for t, c in cited_doc_counter.most_common(10)]

    # Daily counts
    daily = Counter()
    for m in user_msgs:
        day = (m.get("created_at") or "")[:10]
        if day:
            daily[day] += 1
    daily_counts = [{"date": d, "count": c} for d, c in sorted(daily.items())]

    pii_count = sum(1 for m in user_msgs if m.get("pii_categories"))
    injection_count = sum(1 for m in user_msgs if m.get("injection_signal"))

    pending_feedback = await feedback_col().count_documents({"rating": "down", "is_reviewed": False})

    return AnalyticsOut(
        top_queries=top_queries,
        zero_result_queries=zero_result[:15],
        low_confidence_queries=low_conf[:15],
        top_cited_docs=top_cited,
        feedback_summary={
            "thumbs_up": feedback_pos,
            "thumbs_down": feedback_neg,
            "total_assistant_messages": len(asst_msgs),
            "pending_review": pending_feedback,
        },
        daily_query_counts=daily_counts,
        pii_flagged_count=pii_count,
        injection_flagged_count=injection_count,
    )
