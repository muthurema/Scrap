"""Auth routes."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException

from app.db import users_col
from app.schemas import UserCreate, UserLogin, TokenResponse, UserOut
from app.auth import hash_password, verify_password, create_access_token, get_current_user, generate_id

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(payload: UserCreate):
    existing = await users_col().find_one({"email": payload.email})
    if existing:
        raise HTTPException(400, "Email already registered")

    # First user becomes superadmin automatically
    total = await users_col().count_documents({})
    role = "superadmin" if total == 0 else (payload.role if payload.role in ("user", "superadmin") else "user")

    user_id = generate_id()
    doc = {
        "id": user_id,
        "email": payload.email,
        "hashed_password": hash_password(payload.password),
        "full_name": payload.full_name,
        "role": role,
        "company_id": payload.company_id,
        "is_active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await users_col().insert_one(doc)

    token = create_access_token({
        "sub": user_id, "email": payload.email, "role": role,
        "company_id": payload.company_id,
    })
    return TokenResponse(
        access_token=token, user_id=user_id, role=role,
        email=payload.email, full_name=payload.full_name, company_id=payload.company_id,
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
    )


@router.get("/me", response_model=UserOut)
async def me(current_user: dict = Depends(get_current_user)):
    user = await users_col().find_one({"id": current_user["sub"]}, {"_id": 0, "hashed_password": 0})
    if not user:
        raise HTTPException(404, "User not found")
    if isinstance(user.get("created_at"), str):
        user["created_at"] = datetime.fromisoformat(user["created_at"])
    return UserOut(**user)
