"""Team & invitation routes — invite codes + email allowlist per company."""
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request

from app.db import users_col, companies_col, invites_col, allowlist_col
from app.schemas import (
    InviteCreate, InviteOut, AllowlistAdd, AllowlistEntryOut, TeamMemberOut,
)
from app.auth import get_current_user, require_admin, generate_id, generate_invite_code
from app.audit import audit

router = APIRouter(prefix="/team", tags=["Team"])


def _now():
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(v):
    return datetime.fromisoformat(v) if isinstance(v, str) else v


def _resolve_org_scope(current_user: dict, requested_company_id: Optional[str]) -> str:
    """
    Admin can only act on their own company. Superadmin may target any company_id.
    Returns the company_id that the action will apply to.
    """
    role = current_user.get("role")
    user_cid = current_user.get("company_id")
    if role == "superadmin":
        if not requested_company_id:
            raise HTTPException(400, "Superadmin must specify a company_id")
        return requested_company_id
    if not user_cid:
        raise HTTPException(400, "Admin must belong to a company")
    if requested_company_id and requested_company_id != user_cid:
        raise HTTPException(403, "You can only manage your own company")
    return user_cid


# ── Invite codes ────────────────────────────────────────────────────────────


@router.post("/invites", response_model=InviteOut, status_code=201)
async def create_invite(
    payload: InviteCreate, request: Request,
    current_user: dict = Depends(require_admin),
):
    company_id = _resolve_org_scope(current_user, payload.company_id)
    # Verify company exists
    company = await companies_col().find_one({"id": company_id}, {"_id": 0, "name": 1})
    if not company:
        raise HTTPException(404, "Company not found")
    # Admins cannot create admin invites (only super can mint new admins)
    role = payload.role
    if role == "admin" and current_user.get("role") != "superadmin":
        raise HTTPException(403, "Only a superadmin can invite new admins")

    code = generate_invite_code()
    # Extremely low collision but be safe
    while await invites_col().find_one({"code": code}):
        code = generate_invite_code()

    expires_at = (datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days)).isoformat()
    doc = {
        "id": generate_id(),
        "code": code,
        "role": role,
        "company_id": company_id,
        "max_uses": payload.max_uses,
        "uses": 0,
        "is_active": True,
        "expires_at": expires_at,
        "created_at": _now(),
        "created_by_user_id": current_user["sub"],
        "created_by_email": current_user["email"],
    }
    await invites_col().insert_one(doc)
    await audit(user=current_user, action="create_invite", resource_type="invite",
                resource_id=doc["id"], request=request,
                details={"role": role, "company_id": company_id, "max_uses": payload.max_uses})

    return InviteOut(
        id=doc["id"], code=code, role=role, company_id=company_id,
        company_name=company.get("name"), max_uses=payload.max_uses, uses=0,
        is_active=True, expires_at=_parse_dt(expires_at), created_at=_parse_dt(doc["created_at"]),
        created_by_email=current_user["email"],
    )


@router.get("/invites", response_model=list[InviteOut])
async def list_invites(current_user: dict = Depends(require_admin)):
    q = {} if current_user.get("role") == "superadmin" else {"company_id": current_user.get("company_id")}
    rows = await invites_col().find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    # Bulk fetch company names
    cids = list({r["company_id"] for r in rows if r.get("company_id")})
    cmap = {c["id"]: c["name"] for c in await companies_col().find({"id": {"$in": cids}}, {"_id": 0, "id": 1, "name": 1}).to_list(len(cids) or 1)} if cids else {}
    return [
        InviteOut(
            id=r["id"], code=r["code"], role=r["role"],
            company_id=r.get("company_id"), company_name=cmap.get(r.get("company_id")),
            max_uses=r["max_uses"], uses=r["uses"], is_active=r["is_active"],
            expires_at=_parse_dt(r["expires_at"]),
            created_at=_parse_dt(r["created_at"]),
            created_by_email=r.get("created_by_email"),
        ) for r in rows
    ]


@router.delete("/invites/{invite_id}", status_code=200)
async def revoke_invite(invite_id: str, request: Request, current_user: dict = Depends(require_admin)):
    inv = await invites_col().find_one({"id": invite_id}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Invite not found")
    if current_user.get("role") != "superadmin" and inv.get("company_id") != current_user.get("company_id"):
        raise HTTPException(403, "Not your company")
    await invites_col().update_one({"id": invite_id}, {"$set": {"is_active": False}})
    await audit(user=current_user, action="revoke_invite", resource_type="invite",
                resource_id=invite_id, request=request)
    return {"ok": True}


# ── Email allowlist ─────────────────────────────────────────────────────────


@router.post("/allowlist", response_model=AllowlistEntryOut, status_code=201)
async def add_allowlist(
    payload: AllowlistAdd, request: Request,
    company_id: Optional[str] = None,
    current_user: dict = Depends(require_admin),
):
    company_id_resolved = _resolve_org_scope(current_user, company_id)
    if payload.role == "admin" and current_user.get("role") != "superadmin":
        raise HTTPException(403, "Only a superadmin can allowlist admins")
    company = await companies_col().find_one({"id": company_id_resolved}, {"_id": 0, "name": 1})
    if not company:
        raise HTTPException(404, "Company not found")
    email_lower = payload.email.lower()

    existing = await allowlist_col().find_one({"email": email_lower, "company_id": company_id_resolved})
    if existing:
        raise HTTPException(409, "Email already on allowlist for this company")

    doc = {
        "id": generate_id(),
        "email": email_lower,
        "role": payload.role,
        "company_id": company_id_resolved,
        "created_at": _now(),
        "created_by_user_id": current_user["sub"],
        "used_at": None,
    }
    await allowlist_col().insert_one(doc)
    await audit(user=current_user, action="add_allowlist", resource_type="allowlist",
                resource_id=doc["id"], request=request, details={"email": email_lower, "role": payload.role})
    return AllowlistEntryOut(
        id=doc["id"], email=email_lower, role=payload.role,
        company_id=company_id_resolved, company_name=company.get("name"),
        created_at=_parse_dt(doc["created_at"]), used_at=None,
    )


@router.get("/allowlist", response_model=list[AllowlistEntryOut])
async def list_allowlist(current_user: dict = Depends(require_admin)):
    q = {} if current_user.get("role") == "superadmin" else {"company_id": current_user.get("company_id")}
    rows = await allowlist_col().find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    cids = list({r["company_id"] for r in rows if r.get("company_id")})
    cmap = {c["id"]: c["name"] for c in await companies_col().find({"id": {"$in": cids}}, {"_id": 0, "id": 1, "name": 1}).to_list(len(cids) or 1)} if cids else {}
    return [
        AllowlistEntryOut(
            id=r["id"], email=r["email"], role=r["role"],
            company_id=r["company_id"], company_name=cmap.get(r["company_id"]),
            created_at=_parse_dt(r["created_at"]),
            used_at=_parse_dt(r["used_at"]) if r.get("used_at") else None,
        ) for r in rows
    ]


@router.delete("/allowlist/{entry_id}", status_code=200)
async def remove_allowlist(entry_id: str, request: Request, current_user: dict = Depends(require_admin)):
    entry = await allowlist_col().find_one({"id": entry_id}, {"_id": 0})
    if not entry:
        raise HTTPException(404, "Entry not found")
    if current_user.get("role") != "superadmin" and entry.get("company_id") != current_user.get("company_id"):
        raise HTTPException(403, "Not your company")
    await allowlist_col().delete_one({"id": entry_id})
    await audit(user=current_user, action="remove_allowlist", resource_type="allowlist",
                resource_id=entry_id, request=request)
    return {"ok": True}


# ── Members listing ─────────────────────────────────────────────────────────


@router.get("/members", response_model=list[TeamMemberOut])
async def list_members(current_user: dict = Depends(require_admin)):
    q = {} if current_user.get("role") == "superadmin" else {"company_id": current_user.get("company_id")}
    rows = await users_col().find(q, {"_id": 0, "hashed_password": 0}).sort("created_at", -1).to_list(500)
    return [
        TeamMemberOut(
            id=r["id"], email=r["email"], full_name=r.get("full_name"),
            role=r.get("role", "user"), company_id=r.get("company_id"),
            site=r.get("site"), role_label=r.get("role_label"),
            is_active=r.get("is_active", True),
            created_at=_parse_dt(r["created_at"]),
        ) for r in rows
    ]


@router.patch("/members/{user_id}/deactivate", status_code=200)
async def deactivate_member(user_id: str, request: Request, current_user: dict = Depends(require_admin)):
    target = await users_col().find_one({"id": user_id}, {"_id": 0, "company_id": 1, "role": 1, "email": 1})
    if not target:
        raise HTTPException(404, "User not found")
    if current_user.get("role") != "superadmin":
        if target.get("company_id") != current_user.get("company_id"):
            raise HTTPException(403, "Not your company")
        if target.get("role") in ("admin", "superadmin"):
            raise HTTPException(403, "Admin cannot deactivate another admin/superadmin")
    if user_id == current_user["sub"]:
        raise HTTPException(400, "You cannot deactivate yourself")
    await users_col().update_one({"id": user_id}, {"$set": {"is_active": False}})
    await audit(user=current_user, action="deactivate_member", resource_type="user",
                resource_id=user_id, request=request, details={"email": target.get("email")})
    return {"ok": True}
