"""Auth routes — JWT-based, with invite-code + email-allowlist signup gating."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException

from app.db import users_col, invites_col, allowlist_col, companies_col
from app.schemas import UserCreate, UserLogin, TokenResponse, UserOut
from app.auth import hash_password, verify_password, create_access_token, get_current_user, generate_id

router = APIRouter(prefix="/auth", tags=["Auth"])


def _now():
    return datetime.now(timezone.utc).isoformat()


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(payload: UserCreate):
    existing = await users_col().find_one({"email": payload.email})
    if existing:
        raise HTTPException(400, "Email already registered")

    total = await users_col().count_documents({})
    role = "user"
    company_id = None
    consumed_invite_id = None
    consumed_allowlist_id = None

    # ── 1. First user ever → superadmin (bootstrap path) ────────────────────
    if total == 0:
        role = "superadmin"

    # ── 2. Invite code provided → role + company come from the invite ───────
    elif payload.invite_code:
        code = payload.invite_code.strip().upper()
        invite = await invites_col().find_one({"code": code}, {"_id": 0})
        if not invite or not invite.get("is_active"):
            raise HTTPException(400, "Invalid or revoked invite code")
        # Expiry check
        try:
            expires_at = datetime.fromisoformat(invite["expires_at"])
        except Exception:
            raise HTTPException(400, "Invalid invite code (expiry malformed)")
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(400, "Invite code has expired")
        if invite.get("uses", 0) >= invite.get("max_uses", 1):
            raise HTTPException(400, "Invite code has reached its usage limit")
        role = invite.get("role", "user")
        company_id = invite.get("company_id")
        consumed_invite_id = invite["id"]

    # ── 3. Email allowlist match (no code) → role + company from allowlist ──
    else:
        email_lower = payload.email.lower()
        entry = await allowlist_col().find_one({"email": email_lower}, {"_id": 0})
        if not entry:
            raise HTTPException(
                403,
                "Sign-ups are by invitation only. Ask your org admin for an invite code "
                "or to add your email to the allowlist.",
            )
        role = entry.get("role", "user")
        company_id = entry.get("company_id")
        consumed_allowlist_id = entry["id"]

    # Sanity: admin/user MUST have a company. Superadmin may have none.
    if role in ("admin", "user") and not company_id:
        raise HTTPException(400, "This account requires a company assignment — contact your admin")

    user_id = generate_id()
    doc = {
        "id": user_id,
        "email": payload.email,
        "hashed_password": hash_password(payload.password),
        "full_name": payload.full_name,
        "role": role,
        "company_id": company_id,
        "is_active": True,
        "needs_onboarding": True,
        "created_at": _now(),
    }
    await users_col().insert_one(doc)

    # Burn the invite / mark the allowlist entry
    if consumed_invite_id:
        await invites_col().update_one(
            {"id": consumed_invite_id},
            {"$inc": {"uses": 1}, "$set": {"last_used_at": _now()}},
        )
    if consumed_allowlist_id:
        await allowlist_col().update_one(
            {"id": consumed_allowlist_id},
            {"$set": {"used_at": _now(), "used_by_user_id": user_id}},
        )

    token = create_access_token({
        "sub": user_id, "email": payload.email, "role": role, "company_id": company_id,
    })
    return TokenResponse(
        access_token=token, user_id=user_id, role=role,
        email=payload.email, full_name=payload.full_name, company_id=company_id,
        needs_onboarding=True,
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: UserLogin):
    user = await users_col().find_one({"email": payload.email})
    if not user or not verify_password(payload.password, user["hashed_password"]):
        raise HTTPException(401, "Invalid email or password")
    if not user.get("is_active", True):
        raise HTTPException(403, "Account is disabled")

    token = create_access_token({
        "sub": user["id"], "email": user["email"], "role": user["role"],
        "company_id": user.get("company_id"),
    })
    return TokenResponse(
        access_token=token, user_id=user["id"], role=user["role"],
        email=user["email"], full_name=user.get("full_name"),
        company_id=user.get("company_id"),
        needs_onboarding=user.get("needs_onboarding", False),
    )


@router.get("/me", response_model=UserOut)
async def me(current_user: dict = Depends(get_current_user)):
    user = await users_col().find_one({"id": current_user["sub"]}, {"_id": 0, "hashed_password": 0})
    if not user:
        raise HTTPException(404, "User not found")
    if isinstance(user.get("created_at"), str):
        user["created_at"] = datetime.fromisoformat(user["created_at"])
    return UserOut(**user)


@router.get("/lookup-company")
async def lookup_company(code: str):
    """Public — used by the register form to show 'Joining: Acme Corp' once the code is typed."""
    if not code:
        return {"valid": False}
    inv = await invites_col().find_one({"code": code.strip().upper(), "is_active": True}, {"_id": 0})
    if not inv:
        return {"valid": False}
    # Don't disclose details once exhausted/expired
    try:
        expires_at = datetime.fromisoformat(inv["expires_at"])
    except Exception:
        expires_at = None
    if expires_at and expires_at < datetime.now(timezone.utc):
        return {"valid": False}
    if inv.get("uses", 0) >= inv.get("max_uses", 1):
        return {"valid": False}
    company = await companies_col().find_one({"id": inv.get("company_id")}, {"_id": 0, "name": 1}) if inv.get("company_id") else None
    return {
        "valid": True,
        "role": inv.get("role"),
        "company_id": inv.get("company_id"),
        "company_name": company.get("name") if company else None,
    }
