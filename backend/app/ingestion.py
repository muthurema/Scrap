"""
Document ingestion: parse → chunk (doc-type aware) → embed → store in Qdrant.
"""
import io
from typing import Optional
from loguru import logger

import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import (
    get_settings, DocumentType, DocumentSource,
    get_chunk_config, get_combined_boost, detect_doc_type,
)
from app.vector_store import VectorStoreService

settings = get_settings()
_tokenizer = tiktoken.get_encoding("cl100k_base")


def _count_tokens(text: str) -> int:
    return len(_tokenizer.encode(text))


# ── Parsers ───────────────────────────────────────────────────────────────────

def parse_pdf(file_bytes: bytes) -> str:
    import pdfplumber
    parts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t and t.strip():
                parts.append(t)
    return "\n\n".join(parts)


def parse_docx(file_bytes: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(file_bytes))
    parts = []
    for para in doc.paragraphs:
        if para.text.strip():
            parts.append(para.text)
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n\n".join(parts)


def parse_xlsx(file_bytes: bytes) -> str:
    import pandas as pd
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    parts = []
    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet)
        parts.append(f"[Sheet: {sheet}]\n{df.to_string(index=False)}")
    return "\n\n".join(parts)


def parse_txt(file_bytes: bytes) -> str:
    return file_bytes.decode("utf-8", errors="replace")


PARSERS = {
    "pdf": parse_pdf, "docx": parse_docx,
    "xlsx": parse_xlsx, "xls": parse_xlsx,
    "txt": parse_txt, "csv": parse_txt, "md": parse_txt,
}


def parse_document(file_bytes: bytes, file_ext: str) -> str:
    ext = file_ext.lower().lstrip(".")
    parser = PARSERS.get(ext)
    if not parser:
        raise ValueError(f"Unsupported file type: {file_ext}")
    return parser(file_bytes)


# ── Chunker ───────────────────────────────────────────────────────────────────

def chunk_text(
    text: str,
    doc_type: DocumentType,
    doc_id: str,
    title: str,
    source: DocumentSource,
    extra_metadata: Optional[dict] = None,
) -> list[dict]:
    cfg = get_chunk_config(doc_type)
    boost = get_combined_boost(doc_type, source)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=cfg.chunk_size,
        chunk_overlap=cfg.chunk_overlap,
        length_function=_count_tokens,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_text(text)
    out = []
    for i, c in enumerate(chunks):
        if not c.strip():
            continue
        chunk_id = f"{doc_id}_{i:04d}"
        payload = {
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "text": c,
            "doc_type": doc_type.value,
            "source": source.value,
            "title": title,
            "chunk_index": i,
            "priority_boost": boost,
            **(extra_metadata or {}),
        }
        out.append({"id": chunk_id, "text": c, "payload": payload})
    logger.info(f"Chunked doc {doc_id} → {len(out)} chunks (type={doc_type.value}, boost={boost})")
    return out


# ── Pipeline ──────────────────────────────────────────────────────────────────

class IngestionService:
    def __init__(self, vector_store: VectorStoreService):
        self.vector_store = vector_store

    async def ingest_document(
        self,
        file_bytes: bytes,
        file_ext: str,
        doc_id: str,
        title: str,
        doc_type: Optional[DocumentType],
        source: DocumentSource,
        extra_metadata: Optional[dict] = None,
    ) -> int:
        raw_text = parse_document(file_bytes, file_ext)
        if not raw_text.strip():
            raise ValueError("Document appears empty or unreadable.")

        if doc_type is None or doc_type == DocumentType.GENERAL:
            detected = detect_doc_type((title + " " + raw_text[:2000]))
            if detected != DocumentType.GENERAL:
                doc_type = detected
                logger.info(f"Auto-detected doc type: {doc_type.value}")
        if doc_type is None:
            doc_type = DocumentType.GENERAL

        chunks = chunk_text(
            text=raw_text,
            doc_type=doc_type,
            doc_id=doc_id,
            title=title,
            source=source,
            extra_metadata=extra_metadata,
        )
        if not chunks:
            raise ValueError("No usable chunks extracted from document.")

        collection = (
            settings.qdrant_collection_company
            if source in (DocumentSource.SUPERADMIN, DocumentSource.TURNSTILE_DMS, DocumentSource.CLIENT_WEB)
            else settings.qdrant_collection_base
        )
        await self.vector_store.upsert_chunks(collection, chunks)
        logger.info(f"Ingested {len(chunks)} chunks for doc {doc_id} → {collection}")
        return len(chunks)

    async def delete_document(self, doc_id: str) -> None:
        for coll in (settings.qdrant_collection_company, settings.qdrant_collection_base):
            await self.vector_store.delete_by_doc_id(coll, doc_id)
