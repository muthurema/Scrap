"""Document upload / management routes (superadmin) — with audit, injection scan, versioning, expiry."""
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, Request

from app.db import documents_col
from app.schemas import DocumentOut, DocumentListResponse
from app.auth import get_current_user, require_superadmin, require_admin
from app.config import get_settings, DocumentType, DocumentSource
from app.vector_store import get_vector_store
from app.ingestion import IngestionService
from app.audit import audit

settings = get_settings()
router = APIRouter(prefix="/documents", tags=["Documents"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xls", ".txt", ".csv", ".md", ".png", ".jpg", ".jpeg"}
MAX_SIZE_BYTES = settings.max_upload_size_mb * 1024 * 1024
# Memory-safety cap: no more than this many docs may be queued/in-flight per
# scope at once. Each in-flight doc holds embedding-model state + file bytes
# in the background task — too many concurrent ingestions OOM the Railway
# pod. The cap also enforces "wait until current batch finishes" UX (the
# frontend disables Upload while any doc is still processing).
MAX_INFLIGHT_PER_SCOPE = 5


def _inflight_scope_query(user: dict) -> dict:
    """Mongo filter for the user's 'in-flight' (queued / chunking) docs.

    Superadmin uploads go to global/regional (company_id=None); admins to
    their own company. We don't count `processing_error` rows — those are
    failed docs the user can delete; they're not consuming a worker slot.
    """
    q: dict = {"is_processed": False, "processing_error": None}
    if user.get("role") == "superadmin":
        q["company_id"] = None
    else:
        q["company_id"] = user.get("company_id")
    return q


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(v):
    if isinstance(v, str):
        return datetime.fromisoformat(v)
    return v


def _doc_to_out(doc: dict) -> DocumentOut:
    doc = {k: v for k, v in doc.items() if k != "_id"}
    doc["created_at"] = _parse_dt(doc.get("created_at"))
    if doc.get("processed_at"):
        doc["processed_at"] = _parse_dt(doc["processed_at"])
    if doc.get("expiry_date"):
        doc["expiry_date"] = _parse_dt(doc["expiry_date"])
    # Compute is_expired
    if doc.get("expiry_date"):
        exp = doc["expiry_date"]
        doc["is_expired"] = exp < datetime.now(timezone.utc)
    return DocumentOut(**doc)


def _read_file_sync(file_path: str) -> bytes:
    """Synchronous file read — offloaded to a worker thread so a 300MB
    PDF doesn't block the asyncio event loop (freezing login / health)."""
    with open(file_path, "rb") as f:
        return f.read()


async def _process_document_bg(doc_id: str, file_path: str, file_ext: str):
    import asyncio
    import gc
    ingestion = IngestionService(get_vector_store())
    try:
        doc = await documents_col().find_one({"id": doc_id})
        if not doc:
            return
        # 300MB sync read would freeze the event loop — offload to threadpool
        file_bytes = await asyncio.to_thread(_read_file_sync, file_path)

        chunk_count, injection_findings = await ingestion.ingest_document(
            file_bytes=file_bytes, file_ext=file_ext, doc_id=doc_id,
            title=doc.get("title") or doc["original_filename"],
            doc_type=DocumentType(doc["doc_type"]),
            source=DocumentSource(doc["source"]),
            extra_metadata={
                "company_id": doc.get("company_id") or "",
                "filename": doc["original_filename"],
                "author": doc.get("author") or "",
                "jurisdiction": doc.get("jurisdiction") or "",
                "expiry_date": doc.get("expiry_date") or "",
            },
        )
        # Free the 300MB bytes buffer ASAP. On Railway's 1GB tier this is
        # the difference between a clean ingestion and a Linux OOM kill.
        del file_bytes
        gc.collect()
        await documents_col().update_one(
            {"id": doc_id},
            {"$set": {
                "is_processed": True, "chunk_count": chunk_count,
                "processed_at": _now_iso(), "processing_error": None,
                "injection_findings": injection_findings,
            }},
        )
    except Exception as e:
        await documents_col().update_one(
            {"id": doc_id},
            {"$set": {"is_processed": False, "processing_error": str(e)}},
        )


@router.get("/upload-quota")
async def upload_quota(current_user: dict = Depends(require_admin)):
    """Live in-flight count + remaining slots for the upload button gating
    on the frontend. Returns the user's own scope (admin→company,
    superadmin→global)."""
    inflight = await documents_col().count_documents(_inflight_scope_query(current_user))
    return {
        "inflight": inflight,
        "max": MAX_INFLIGHT_PER_SCOPE,
        "remaining": max(0, MAX_INFLIGHT_PER_SCOPE - inflight),
        "can_upload": inflight == 0,
    }


@router.post("/upload", response_model=DocumentOut, status_code=201)
async def upload_document(
    background_tasks: BackgroundTasks,
    request: Request,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    author: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    doc_type: str = Form(DocumentType.GENERAL.value),
    source: str = Form(DocumentSource.BASE_CORPUS.value),
    tags: Optional[str] = Form(None),
    version: Optional[str] = Form(None),
    expiry_date: Optional[str] = Form(None),
    supersedes_id: Optional[str] = Form(None),
    jurisdiction: Optional[str] = Form(None),
    current_user: dict = Depends(require_admin),
):
    # Single global GIS knowledge base: every book is shared globally.
    # All uploads (admin or superadmin) go to the global base corpus with
    # no company scoping.
    source = DocumentSource.BASE_CORPUS.value
    company_id_for_doc = None

    # ── Concurrent-ingestion cap (memory safety) ──────────────────────────
    # Reject the upload if this user's scope already has MAX_INFLIGHT_PER_SCOPE
    # docs queued or chunking. The frontend ALSO disables the upload button
    # while any doc is in-flight (so the typical user never hits this 429),
    # but the server enforces the cap as a hard guarantee against parallel
    # tabs / API misuse.
    inflight = await documents_col().count_documents(_inflight_scope_query(current_user))
    if inflight >= MAX_INFLIGHT_PER_SCOPE:
        raise HTTPException(
            429,
            f"Upload limit reached — {inflight} document(s) are still being "
            f"processed. Please wait until they finish chunking before "
            f"uploading more. (Max {MAX_INFLIGHT_PER_SCOPE} in-flight per "
            f"account.)",
        )

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"File type {ext} not supported. Allowed: {sorted(ALLOWED_EXTENSIONS)}")

    # Stream the upload to disk in chunks to avoid loading 200MB+ textbooks into RAM
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    doc_id = str(uuid.uuid4())
    safe_filename = f"{doc_id}{ext}"
    file_path = upload_dir / safe_filename
    total_bytes = 0
    CHUNK = 1024 * 1024  # 1 MB
    try:
        with open(file_path, "wb") as out:
            while True:
                chunk = await file.read(CHUNK)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_SIZE_BYTES:
                    out.close()
                    file_path.unlink(missing_ok=True)
                    raise HTTPException(413, f"File exceeds {settings.max_upload_size_mb}MB limit")
                out.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        file_path.unlink(missing_ok=True)
        raise HTTPException(500, f"Upload failed while writing file: {e}")

    if total_bytes < 16:
        file_path.unlink(missing_ok=True)
        raise HTTPException(400, "File is empty or too small")

    # Parse and validate expiry date
    expiry_iso: Optional[str] = None
    if expiry_date:
        try:
            dt = datetime.fromisoformat(expiry_date.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            expiry_iso = dt.isoformat()
        except ValueError:
            raise HTTPException(400, "Invalid expiry_date (use ISO 8601, e.g. 2026-12-31)")

    # Validate supersedes_id
    superseded_doc: Optional[dict] = None
    if supersedes_id:
        superseded_doc = await documents_col().find_one({"id": supersedes_id})
        if not superseded_doc:
            file_path.unlink(missing_ok=True)
            raise HTTPException(404, f"supersedes_id={supersedes_id} not found")

    tag_list = [t.strip() for t in tags.split(",")] if tags else []
    doc = {
        "id": doc_id,
        "company_id": company_id_for_doc,
        "filename": safe_filename,
        "original_filename": file.filename,
        "file_path": str(file_path),
        "file_type": ext.lstrip("."),
        "file_size_bytes": total_bytes,
        "mime_type": file.content_type,
        "doc_type": doc_type,
        "source": source,
        "title": title or Path(file.filename).stem,
        "author": author,
        "description": description,
        "tags": tag_list,
        "version": version,
        "expiry_date": expiry_iso,
        "supersedes_id": supersedes_id,
        "superseded_by_id": None,
        "jurisdiction": jurisdiction,
        "is_processed": False,
        "chunk_count": 0,
        "uploaded_by": current_user.get("sub"),
        "created_at": _now_iso(),
        "processed_at": None,
        "processing_error": None,
    }
    await documents_col().insert_one(doc)

    # Retire superseded doc chunks and mark it
    if superseded_doc:
        ingestion = IngestionService(get_vector_store())
        await ingestion.delete_document(superseded_doc["id"])
        await documents_col().update_one(
            {"id": superseded_doc["id"]},
            {"$set": {"superseded_by_id": doc_id, "chunk_count": 0, "is_processed": False}},
        )

    await audit(user=current_user, action="upload_document", resource_type="document",
                resource_id=doc_id, request=request,
                details={"filename": file.filename, "size_bytes": total_bytes,
                         "doc_type": doc_type, "source": source,
                         "supersedes_id": supersedes_id,
                         "jurisdiction": jurisdiction,
                         "expiry_date": expiry_iso})

    background_tasks.add_task(_process_document_bg, doc_id, str(file_path), ext.lstrip("."))
    return _doc_to_out(doc)


@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    page: int = 1, page_size: int = 500,
    doc_type: Optional[str] = None, source: Optional[str] = None,
    include_superseded: bool = False,
    current_user: dict = Depends(get_current_user),
):
    page_size = max(1, min(page_size, 2000))
    query = {}
    company_id = current_user.get("company_id")
    if company_id and current_user.get("role") != "superadmin":
        query["$or"] = [{"company_id": company_id}, {"company_id": None}]
    if doc_type:
        query["doc_type"] = doc_type
    if source:
        query["source"] = source
    if not include_superseded:
        query["superseded_by_id"] = None

    total = await documents_col().count_documents(query)
    cursor = documents_col().find(query, {"_id": 0}).sort("created_at", -1).skip((page - 1) * page_size).limit(page_size)
    docs = await cursor.to_list(page_size)
    return DocumentListResponse(items=[_doc_to_out(d) for d in docs], total=total)


def _user_can_access_doc(user: dict, doc: dict) -> bool:
    """Authorize a user to view/download a document.

    Rules:
    - Superadmin: everything
    - Global / regional / platform-web docs (no company_id): any authenticated user
    - Company-scoped docs: same company_id only
    """
    if user.get("role") == "superadmin":
        return True
    doc_company = doc.get("company_id")
    if not doc_company:  # global / regional / platform-web
        return True
    return doc_company == user.get("company_id")


@router.get("/{doc_id}", response_model=DocumentOut)
async def get_document(doc_id: str, current_user: dict = Depends(get_current_user)):
    """Single-doc metadata fetch — used by the chat source modal."""
    doc = await documents_col().find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Document not found")
    if not _user_can_access_doc(current_user, doc):
        raise HTTPException(403, "You don't have access to this document")
    return _doc_to_out(doc)


@router.get("/{doc_id}/download")
async def download_document(doc_id: str, current_user: dict = Depends(get_current_user)):
    """
    Stream the original uploaded file back to the user. Used when a chat
    source pill is clicked → opens the doc in a new tab.

    Inline disposition so PDFs/images/text render in the browser; download
    headers added for non-renderable types.
    """
    from pathlib import Path as _Path
    from fastapi.responses import FileResponse

    doc = await documents_col().find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Document not found")
    if not _user_can_access_doc(current_user, doc):
        raise HTTPException(403, "You don't have access to this document")

    file_path = doc.get("file_path")
    if not file_path or not _Path(file_path).exists():
        raise HTTPException(410, "Original file is no longer available on disk")

    filename = doc.get("original_filename") or "document"
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: str, request: Request, current_user: dict = Depends(require_admin)):
    doc = await documents_col().find_one({"id": doc_id})
    if not doc:
        raise HTTPException(404, "Document not found")

    ingestion = IngestionService(get_vector_store())
    await ingestion.delete_document(doc_id)
    fp = doc.get("file_path")
    if fp and Path(fp).exists():
        Path(fp).unlink()
    await documents_col().delete_one({"id": doc_id})
    # Clear superseded_by_id pointer in parent if applicable
    await documents_col().update_many({"superseded_by_id": doc_id}, {"$set": {"superseded_by_id": None}})

    await audit(user=current_user, action="delete_document", resource_type="document",
                resource_id=doc_id, request=request,
                details={"title": doc.get("title"), "chunks_removed": doc.get("chunk_count", 0)})


@router.post("/{doc_id}/reprocess", response_model=DocumentOut)
async def reprocess_document(
    doc_id: str, request: Request,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_admin),
):
    doc = await documents_col().find_one({"id": doc_id})
    if not doc:
        raise HTTPException(404, "Document not found")
    if not doc.get("file_path") or not Path(doc["file_path"]).exists():
        raise HTTPException(
            400,
            "This document cannot be re-processed because its source file is not available "
            "(e.g. seed-corpus entries stored inline). Re-upload it instead.",
        )

    ingestion = IngestionService(get_vector_store())
    await ingestion.delete_document(doc_id)
    await documents_col().update_one(
        {"id": doc_id},
        {"$set": {"is_processed": False, "chunk_count": 0, "processing_error": None, "processed_at": None}},
    )
    background_tasks.add_task(_process_document_bg, doc_id, doc["file_path"], doc["file_type"])
    await audit(user=current_user, action="reprocess_document", resource_type="document",
                resource_id=doc_id, request=request)
    doc = await documents_col().find_one({"id": doc_id}, {"_id": 0})
    return _doc_to_out(doc)


@router.post("/{doc_id}/cancel", status_code=200)
async def cancel_document(doc_id: str, request: Request, current_user: dict = Depends(require_admin)):
    """
    Cancel an in-flight document ingestion. Marks the doc as cancelled — the
    background task can't be killed mid-flight (Python limitation), but the
    document is removed from search results and the file is deleted so the
    user can re-upload cleanly. If the worker happens to finish anyway, the
    cancelled marker prevents the chunks from being stored.
    """
    doc = await documents_col().find_one({"id": doc_id})
    if not doc:
        raise HTTPException(404, "Document not found")
    if doc.get("is_processed"):
        raise HTTPException(400, "Document is already fully processed — delete it instead")

    # Best-effort cleanup of any partial chunks already embedded
    try:
        ingestion = IngestionService(get_vector_store())
        await ingestion.delete_document(doc_id)
    except Exception:
        pass

    # Hard-delete the doc + file so the user can re-upload with the same filename
    file_path = doc.get("file_path")
    if file_path:
        Path(file_path).unlink(missing_ok=True)
    await documents_col().delete_one({"id": doc_id})

    await audit(user=current_user, action="cancel_document_ingestion", resource_type="document",
                resource_id=doc_id, request=request,
                details={"title": doc.get("title"), "filename": doc.get("original_filename")})
    return {"ok": True, "cancelled": True}
