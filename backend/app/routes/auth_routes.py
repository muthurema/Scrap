"""Auth routes — JWT-based, with invite-code + email-allowlist signup gating."""
import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request

from app.db import users_col, invites_col, allowlist_col, companies_col
from app.schemas import (
    UserCreate, UserLogin, TokenResponse, UserOut,
    PasswordResetRequest, PasswordResetConfirm,
)
from app.auth import (
    hash_password_async, verify_password_async,
    create_access_token, get_current_user, generate_id,
)
from app import password_reset as pwr

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
        "hashed_password": await hash_password_async(payload.password),
        "full_name": payload.full_name,
        "role": role,
        "company_id": company_id,
        "is_active": True,
        "needs_onboarding": False,
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
        needs_onboarding=False,
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: UserLogin):
    user = await users_col().find_one({"email": payload.email})
    if not user or not await verify_password_async(payload.password, user["hashed_password"]):
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


# ── Password reset (self-service) ────────────────────────────────────────────
# Two endpoints. Intentionally always-200 on request to defeat email
# enumeration; the magic link is emailed only when the address is real.

@router.post("/password-reset/request", status_code=200)
async def password_reset_request(payload: PasswordResetRequest, request: Request):
    email = payload.email.lower().strip()

    # Same 200 response shape for every code path below — no information
    # leaks about whether the address is registered.
    generic_ok = {
        "ok": True,
        "message": "If that email is registered, a reset link has been sent.",
    }

    # Soft rate-limit per email so an attacker can't burn a mailbox or
    # exhaust SMTP quotas. Returns generic OK so the rate-limited caller
    # also can't distinguish a real account from a fake one.
    if await pwr.is_rate_limited(email):
        return generic_ok

    user = await users_col().find_one({"email": email}, {"_id": 0, "id": 1, "email": 1})
    if not user:
        return generic_ok

    raw_token = await pwr.create_reset_record(email=email, user_id=user["id"])

    # Build the magic link. PASSWORD_RESET_FRONTEND_URL is set in Railway
    # (e.g. https://chat.turnstile360.com); for local dev we fall back to
    # the request's own origin so the link still works against the
    # preview URL during development.
    frontend_url = os.environ.get("PASSWORD_RESET_FRONTEND_URL", "").rstrip("/")
    if not frontend_url:
        frontend_url = f"{request.url.scheme}://{request.url.netloc}"
    reset_url = f"{frontend_url}/reset-password?token={raw_token}"

    await pwr.send_reset_email(
        to_email=email,
        reset_url=reset_url,
        expires_min=pwr.TOKEN_TTL_MINUTES,
    )
    return generic_ok


@router.post("/password-reset/confirm", status_code=200)
async def password_reset_confirm(payload: PasswordResetConfirm):
    row = await pwr.consume_reset_token(payload.token)
    if not row:
        # 400 (not 401) — the request is well-formed but the token is no
        # longer valid. Frontend turns this into "Link expired — request
        # a new one" so the UX is unambiguous.
        raise HTTPException(400, "Reset link is invalid or has expired. Request a new one.")

    # Rotate the password — bcrypt hashing offloaded so the event loop
    # stays responsive under concurrent load.
    new_hash = await hash_password_async(payload.new_password)
    res = await users_col().update_one(
        {"id": row["user_id"]},
        {"$set": {"hashed_password": new_hash, "password_updated_at": _now()}},
    )
    if res.matched_count == 0:
        # Account was deleted between request and confirm. Token is now
        # consumed; user should re-register or contact admin.
        raise HTTPException(400, "Account no longer exists.")
    return {"ok": True, "message": "Password updated. You can now sign in."}
