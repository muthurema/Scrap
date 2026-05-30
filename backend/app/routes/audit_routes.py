"""Audit log routes — superadmin-only read access."""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query

from app.db import db
from app.auth import require_superadmin


def audit_logs_col():
    return db.audit_logs


router = APIRouter(prefix="/audit", tags=["Audit"])


def _parse_dt(v):
    if isinstance(v, str):
        return datetime.fromisoformat(v)
    return v


@router.get("/")
async def list_audit_logs(
    limit: int = Query(50, ge=1, le=500),
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    current_user: dict = Depends(require_superadmin),
):
    query = {}
    if action:
        query["action"] = action
    if resource_type:
        query["resource_type"] = resource_type
    cursor = audit_logs_col().find(query, {"_id": 0}).sort("created_at", -1).limit(limit)
    items = await cursor.to_list(limit)
    for it in items:
        it["created_at"] = _parse_dt(it.get("created_at"))
    return {"items": items, "total": await audit_logs_col().count_documents(query)}
