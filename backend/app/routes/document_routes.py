"""Document upload / management routes (superadmin)."""
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks

from app.db import documents_col
from app.schemas import DocumentOut, DocumentListResponse
from app.auth import get_current_user, require_superadmin
from app.config import get_settings, DocumentType, DocumentSource
from app.vector_store import get_vector_store
from app.ingestion import IngestionService

settings = get_settings()
router = APIRouter(prefix="/documents", tags=["Documents"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xls", ".txt", ".csv", ".md"}
MAX_SIZE_BYTES = settings.max_upload_size_mb * 1024 * 1024


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
    return DocumentOut(**doc)


async def _process_document_bg(doc_id: str, file_path: str, file_ext: str):
    ingestion = IngestionService(get_vector_store())
    try:
        doc = await documents_col().find_one({"id": doc_id})
        if not doc:
            return
        with open(file_path, "rb") as f:
            file_bytes = f.read()

        chunk_count = await ingestion.ingest_document(
            file_bytes=file_bytes,
            file_ext=file_ext,
            doc_id=doc_id,
            title=doc.get("title") or doc["original_filename"],
            doc_type=DocumentType(doc["doc_type"]),
            source=DocumentSource(doc["source"]),
            extra_metadata={
                "company_id": doc.get("company_id") or "",
                "filename": doc["original_filename"],
            },
        )
        await documents_col().update_one(
            {"id": doc_id},
            {"$set": {
                "is_processed": True,
                "chunk_count": chunk_count,
                "processed_at": _now_iso(),
                "processing_error": None,
            }},
        )
    except Exception as e:
        await documents_col().update_one(
            {"id": doc_id},
            {"$set": {"is_processed": False, "processing_error": str(e)}},
        )


@router.post("/upload", response_model=DocumentOut, status_code=201)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    doc_type: str = Form(DocumentType.GENERAL.value),
    source: str = Form(DocumentSource.SUPERADMIN.value),
    tags: Optional[str] = Form(None),
    version: Optional[str] = Form(None),
    current_user: dict = Depends(require_superadmin),
):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"File type {ext} not supported. Allowed: {sorted(ALLOWED_EXTENSIONS)}")

    contents = await file.read()
    if len(contents) > MAX_SIZE_BYTES:
        raise HTTPException(413, f"File exceeds {settings.max_upload_size_mb}MB limit")

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    doc_id = str(uuid.uuid4())
    safe_filename = f"{doc_id}{ext}"
    file_path = upload_dir / safe_filename
    with open(file_path, "wb") as f:
        f.write(contents)

    tag_list = [t.strip() for t in tags.split(",")] if tags else []

    doc = {
        "id": doc_id,
        "company_id": current_user.get("company_id"),
        "filename": safe_filename,
        "original_filename": file.filename,
        "file_path": str(file_path),
        "file_type": ext.lstrip("."),
        "file_size_bytes": len(contents),
        "mime_type": file.content_type,
        "doc_type": doc_type,
        "source": source,
        "title": title or Path(file.filename).stem,
        "description": description,
        "tags": tag_list,
        "version": version,
        "is_processed": False,
        "chunk_count": 0,
        "uploaded_by": current_user.get("sub"),
        "created_at": _now_iso(),
        "processed_at": None,
        "processing_error": None,
    }
    await documents_col().insert_one(doc)

    background_tasks.add_task(_process_document_bg, doc_id, str(file_path), ext.lstrip("."))

    return _doc_to_out(doc)


@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    page: int = 1,
    page_size: int = 50,
    doc_type: Optional[str] = None,
    source: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    query = {}
    company_id = current_user.get("company_id")
    if company_id and current_user.get("role") != "superadmin":
        query["$or"] = [{"company_id": company_id}, {"company_id": None}]
    if doc_type:
        query["doc_type"] = doc_type
    if source:
        query["source"] = source

    total = await documents_col().count_documents(query)
    cursor = documents_col().find(query, {"_id": 0}).sort("created_at", -1).skip((page - 1) * page_size).limit(page_size)
    docs = await cursor.to_list(page_size)
    return DocumentListResponse(items=[_doc_to_out(d) for d in docs], total=total)


@router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: str, current_user: dict = Depends(require_superadmin)):
    doc = await documents_col().find_one({"id": doc_id})
    if not doc:
        raise HTTPException(404, "Document not found")

    ingestion = IngestionService(get_vector_store())
    await ingestion.delete_document(doc_id)

    fp = doc.get("file_path")
    if fp and Path(fp).exists():
        Path(fp).unlink()

    await documents_col().delete_one({"id": doc_id})


@router.post("/{doc_id}/reprocess", response_model=DocumentOut)
async def reprocess_document(
    doc_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_superadmin),
):
    doc = await documents_col().find_one({"id": doc_id})
    if not doc:
        raise HTTPException(404, "Document not found")

    ingestion = IngestionService(get_vector_store())
    await ingestion.delete_document(doc_id)

    await documents_col().update_one(
        {"id": doc_id},
        {"$set": {"is_processed": False, "chunk_count": 0, "processing_error": None, "processed_at": None}},
    )
    background_tasks.add_task(_process_document_bg, doc_id, doc["file_path"], doc["file_type"])

    doc = await documents_col().find_one({"id": doc_id}, {"_id": 0})
    return _doc_to_out(doc)
