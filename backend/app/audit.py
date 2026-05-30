"""
Audit logging service.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import Request
from loguru import logger

from app.db import db
from app.security import mask_secrets


def audit_logs_col():
    return db.audit_logs


async def ensure_audit_indexes():
    await audit_logs_col().create_index([("created_at", -1)])
    await audit_logs_col().create_index([("user_id", 1), ("created_at", -1)])
    await audit_logs_col().create_index([("action", 1), ("created_at", -1)])


def _client_ip(request: Optional[Request]) -> Optional[str]:
    if not request:
        return None
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


async def audit(
    *,
    user: Optional[dict],
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: Optional[dict] = None,
    request: Optional[Request] = None,
    status: str = "success",
) -> None:
    """
    Persist an audit-log entry. `action` is a verb_noun like 'upload_document'.
    """
    safe_details = {}
    if details:
        for k, v in details.items():
            safe_details[k] = mask_secrets(str(v)) if isinstance(v, str) else v
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": (user or {}).get("sub"),
        "user_email": (user or {}).get("email"),
        "user_role": (user or {}).get("role"),
        "company_id": (user or {}).get("company_id"),
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "details": safe_details,
        "status": status,
        "ip": _client_ip(request),
        "user_agent": request.headers.get("user-agent") if request else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await audit_logs_col().insert_one(doc)
    except Exception as e:
        logger.warning(f"Audit log insert failed: {e}")
