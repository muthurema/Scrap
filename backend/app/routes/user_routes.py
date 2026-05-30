"""User profile + onboarding routes."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request

from app.db import users_col
from app.schemas import UserOut, UserProfileUpdate
from app.auth import get_current_user
from app.audit import audit

router = APIRouter(prefix="/users", tags=["Users"])


def _parse_dt(v):
    if isinstance(v, str):
        return datetime.fromisoformat(v)
    return v


JURISDICTIONS = ["US", "UK", "EU", "AU", "IN", "CA", "GLOBAL"]
INDUSTRY_SECTORS = [
    "construction", "manufacturing", "oil_gas", "mining", "chemical",
    "pharma", "logistics", "utilities", "healthcare", "office",
    "agriculture", "marine", "other",
]


@router.get("/jurisdictions")
async def list_jurisdictions(current_user: dict = Depends(get_current_user)):
    return {"jurisdictions": JURISDICTIONS, "industry_sectors": INDUSTRY_SECTORS}


@router.patch("/me", response_model=UserOut)
async def update_me(payload: UserProfileUpdate, request: Request, current_user: dict = Depends(get_current_user)):
    update_doc = {}
    for k, v in payload.model_dump(exclude_unset=True).items():
        if k == "jurisdiction" and v and v not in JURISDICTIONS:
            raise HTTPException(400, f"Invalid jurisdiction. Allowed: {JURISDICTIONS}")
        if k == "industry_sector" and v and v not in INDUSTRY_SECTORS:
            raise HTTPException(400, f"Invalid industry sector. Allowed: {INDUSTRY_SECTORS}")
        update_doc[k] = v

    if update_doc:
        # If jurisdiction or industry_sector is being set, onboarding is complete
        if "jurisdiction" in update_doc or "industry_sector" in update_doc:
            update_doc["needs_onboarding"] = False
        await users_col().update_one({"id": current_user["sub"]}, {"$set": update_doc})
        await audit(user=current_user, action="update_profile", resource_type="user",
                    resource_id=current_user["sub"], request=request, details=update_doc)

    user = await users_col().find_one({"id": current_user["sub"]}, {"_id": 0, "hashed_password": 0})
    if isinstance(user.get("created_at"), str):
        user["created_at"] = _parse_dt(user["created_at"])
    return UserOut(**user)
