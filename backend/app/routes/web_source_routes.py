"""Web Sources routes — with SSRF protection + audit logging."""
import uuid
import hashlib
import re
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from app.db import web_sources_col
from app.schemas import WebSourceCreate, WebSourceOut, WebSourceScrapeResult
from app.auth import get_current_user, require_superadmin
from app.config import DocumentType, DocumentSource, WebSourceScope
from app.vector_store import get_vector_store
from app.ingestion import IngestionService
from app.security import is_safe_url
from app.audit import audit

router = APIRouter(prefix="/web-sources", tags=["Web Sources"])


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(v):
    if isinstance(v, str):
        return datetime.fromisoformat(v)
    return v


def _ws_to_out(ws: dict) -> WebSourceOut:
    ws = {k: v for k, v in ws.items() if k != "_id"}
    for fld in ("created_at", "last_scraped_at", "change_detected_at"):
        if ws.get(fld):
            ws[fld] = _parse_dt(ws[fld])
    return WebSourceOut(**ws)


def _extract_text(html: str, url: str) -> str:
    try:
        import trafilatura
        text = trafilatura.extract(html, include_tables=True, favor_precision=True, url=url)
        return text or ""
    except Exception:
        clean = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", clean).strip()


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _fetch_url(url: str) -> tuple[str, str]:
    safe, err = is_safe_url(url)
    if not safe:
        raise ValueError(f"URL blocked by SSRF check: {err}")
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=30.0,
        headers={"User-Agent": "EHSBot/1.0 (EHS knowledge aggregator)"},
    ) as client:
        r = await client.get(url)
        r.raise_for_status()
        # Final URL must also be safe (defeat open-redirect SSRF)
        final = str(r.url)
        safe2, err2 = is_safe_url(final)
        if not safe2:
            raise ValueError(f"Redirected URL blocked by SSRF check: {err2}")
        return r.text, final


def _can_manage(user: dict, source: dict) -> bool:
    if user.get("role") == "superadmin":
        return True
    if source.get("scope") == WebSourceScope.CLIENT.value:
        return source.get("company_id") == user.get("company_id")
    return False


@router.post("/", response_model=WebSourceOut, status_code=201)
async def create_web_source(payload: WebSourceCreate, request: Request, current_user: dict = Depends(get_current_user)):
    if payload.scope == WebSourceScope.PLATFORM and current_user.get("role") != "superadmin":
        raise HTTPException(403, "Only superadmin can add platform-level web sources")

    safe, err = is_safe_url(str(payload.url))
    if not safe:
        raise HTTPException(400, f"URL rejected: {err}")

    existing = await web_sources_col().find_one({"url": str(payload.url)})
    if existing:
        raise HTTPException(409, f"URL already registered: {payload.url}")

    company_id = payload.company_id
    if payload.scope == WebSourceScope.CLIENT and not company_id:
        company_id = current_user.get("company_id")
    if payload.scope == WebSourceScope.PLATFORM:
        company_id = None

    doc = {
        "id": str(uuid.uuid4()),
        "url": str(payload.url),
        "label": payload.label,
        "description": payload.description,
        "scope": payload.scope.value,
        "company_id": company_id,
        "scrape_frequency": payload.scrape_frequency.value,
        "crawl_depth": payload.crawl_depth,
        "include_patterns": payload.include_patterns,
        "exclude_patterns": payload.exclude_patterns,
        "doc_type": payload.doc_type.value,
        "is_active": True,
        "last_scraped_at": None,
        "last_content_hash": None,
        "last_chunk_count": 0,
        "last_scrape_error": None,
        "change_detected_at": None,
        "is_change_pending_review": False,
        "added_by": current_user.get("sub"),
        "created_at": _now_iso(),
    }
    await web_sources_col().insert_one(doc)
    await audit(user=current_user, action="create_web_source", resource_type="web_source",
                resource_id=doc["id"], request=request,
                details={"url": doc["url"], "scope": doc["scope"]})
    return _ws_to_out(doc)


@router.get("/", response_model=list[WebSourceOut])
async def list_web_sources(current_user: dict = Depends(get_current_user)):
    company_id = current_user.get("company_id")
    query = {"$or": [{"scope": WebSourceScope.PLATFORM.value}]}
    if company_id:
        query["$or"].append({"company_id": company_id})
    cursor = web_sources_col().find(query, {"_id": 0}).sort("created_at", -1)
    items = await cursor.to_list(200)
    return [_ws_to_out(x) for x in items]


@router.delete("/{source_id}", status_code=204)
async def delete_web_source(source_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    src = await web_sources_col().find_one({"id": source_id})
    if not src:
        raise HTTPException(404, "Web source not found")
    if not _can_manage(current_user, src):
        raise HTTPException(403, "Access denied")

    ingestion = IngestionService(get_vector_store())
    doc_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"web:{source_id}"))
    await ingestion.delete_document(doc_id)
    await web_sources_col().delete_one({"id": source_id})
    await audit(user=current_user, action="delete_web_source", resource_type="web_source",
                resource_id=source_id, request=request, details={"url": src.get("url")})


async def _scrape_source(source_id: str) -> WebSourceScrapeResult:
    src = await web_sources_col().find_one({"id": source_id})
    if not src:
        raise HTTPException(404, "Web source not found")

    result = {
        "web_source_id": source_id, "url": src["url"],
        "chunks_stored": 0, "content_hash": src.get("last_content_hash"),
        "changed": False, "significant_change": False, "change_ratio": 0.0, "error": None,
    }

    try:
        html, final_url = await _fetch_url(src["url"])
        text = _extract_text(html, final_url)
        if not text.strip():
            raise ValueError("No extractable text content found at URL")

        new_hash = _content_hash(text)
        last_hash = src.get("last_content_hash")
        if last_hash and new_hash == last_hash:
            await web_sources_col().update_one(
                {"id": source_id},
                {"$set": {"last_scraped_at": _now_iso(), "last_scrape_error": None}},
            )
            result["content_hash"] = new_hash
            return WebSourceScrapeResult(**result)

        result["changed"] = True
        result["content_hash"] = new_hash
        if last_hash:
            result["significant_change"] = True
            result["change_ratio"] = 1.0

        ingestion = IngestionService(get_vector_store())
        doc_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"web:{source_id}"))
        await ingestion.delete_document(doc_id)

        scope = WebSourceScope(src["scope"])
        qdrant_src = DocumentSource.CLIENT_WEB if scope == WebSourceScope.CLIENT else DocumentSource.PLATFORM_WEB

        chunk_count, _ = await ingestion.ingest_document(
            file_bytes=text.encode("utf-8"), file_ext="txt",
            doc_id=doc_id, title=src["label"],
            doc_type=DocumentType(src["doc_type"]), source=qdrant_src,
            extra_metadata={
                "web_source_id": source_id, "url": src["url"],
                "company_id": src.get("company_id") or "", "filename": src["url"],
                "scope": src["scope"],
            },
        )
        result["chunks_stored"] = chunk_count

        update = {
            "last_scraped_at": _now_iso(),
            "last_content_hash": new_hash,
            "last_chunk_count": chunk_count,
            "last_scrape_error": None,
        }
        if result["significant_change"]:
            update["change_detected_at"] = _now_iso()
            update["is_change_pending_review"] = True
        await web_sources_col().update_one({"id": source_id}, {"$set": update})

    except Exception as e:
        result["error"] = str(e)
        await web_sources_col().update_one(
            {"id": source_id},
            {"$set": {"last_scraped_at": _now_iso(), "last_scrape_error": str(e)}},
        )

    return WebSourceScrapeResult(**result)


@router.post("/{source_id}/scrape", response_model=WebSourceScrapeResult)
async def scrape_now(source_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    src = await web_sources_col().find_one({"id": source_id})
    if not src:
        raise HTTPException(404, "Web source not found")
    if not _can_manage(current_user, src):
        raise HTTPException(403, "Access denied")
    res = await _scrape_source(source_id)
    await audit(user=current_user, action="scrape_web_source", resource_type="web_source",
                resource_id=source_id, request=request,
                details={"url": src.get("url"), "chunks_stored": res.chunks_stored,
                         "changed": res.changed, "error": res.error})
    return res


@router.post("/{source_id}/acknowledge-change", response_model=WebSourceOut)
async def acknowledge(source_id: str, request: Request, current_user: dict = Depends(require_superadmin)):
    src = await web_sources_col().find_one_and_update(
        {"id": source_id}, {"$set": {"is_change_pending_review": False}},
        return_document=True,
    )
    if not src:
        raise HTTPException(404, "Web source not found")
    await audit(user=current_user, action="acknowledge_change", resource_type="web_source",
                resource_id=source_id, request=request)
    return _ws_to_out(src)
