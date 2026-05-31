"""Pydantic schemas for API requests and responses."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field

from app.config import (
    DocumentType, DocumentSource, WebSourceScope, ScrapeFrequency,
)


# ── Auth & User ──────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    full_name: Optional[str] = None
    role: str = "user"
    company_id: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    role: str
    email: str
    full_name: Optional[str] = None
    company_id: Optional[str] = None
    needs_onboarding: bool = False


class UserOut(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    role: str
    company_id: Optional[str] = None
    is_active: bool = True
    created_at: datetime
    site: Optional[str] = None
    role_label: Optional[str] = None
    jurisdiction: Optional[str] = None
    industry_sector: Optional[str] = None
    needs_onboarding: bool = False


class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    site: Optional[str] = None
    role_label: Optional[str] = None
    jurisdiction: Optional[str] = None
    industry_sector: Optional[str] = None


# ── Documents ─────────────────────────────────────────────────────────────────

class DocumentOut(BaseModel):
    id: str
    filename: str
    original_filename: str
    doc_type: DocumentType
    source: DocumentSource
    title: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = []
    version: Optional[str] = None
    is_processed: bool = False
    chunk_count: int = 0
    file_size_bytes: Optional[int] = None
    uploaded_by: Optional[str] = None
    created_at: datetime
    processed_at: Optional[datetime] = None
    processing_error: Optional[str] = None
    expiry_date: Optional[datetime] = None
    supersedes_id: Optional[str] = None
    superseded_by_id: Optional[str] = None
    is_expired: bool = False
    jurisdiction: Optional[str] = None


class DocumentListResponse(BaseModel):
    items: List[DocumentOut]
    total: int


# ── Chat ──────────────────────────────────────────────────────────────────────

class ChatMessageIn(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)
    session_id: Optional[str] = None
    # Up to 3 images per message, each a data URL (data:image/jpeg;base64,...). ~5 MB cap each.
    images: Optional[list[str]] = Field(default=None, max_length=3)


class SourceReference(BaseModel):
    doc_id: str
    title: str
    filename: str
    doc_type: DocumentType
    source: DocumentSource
    chunk_text: str
    similarity_score: float
    page_number: Optional[int] = None
    last_updated: Optional[datetime] = None
    jurisdiction: Optional[str] = None


class ChatMessageOut(BaseModel):
    message_id: str
    session_id: str
    role: str
    content: str
    sources: List[SourceReference] = []
    confidence_score: Optional[float] = None
    created_at: datetime
    feedback: Optional[str] = None
    is_high_risk: bool = False
    suggested_followups: List[str] = []
    acknowledged_at: Optional[datetime] = None


class ChatSessionOut(BaseModel):
    id: str
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class FeedbackIn(BaseModel):
    rating: str = Field(..., pattern="^(up|down)$")
    comment: Optional[str] = None


class FeedbackAnnotateIn(BaseModel):
    annotation: str = Field(..., min_length=2, max_length=2000)


# ── Admin ─────────────────────────────────────────────────────────────────────

class CompanyCreate(BaseModel):
    name: str
    turnstile_instance_url: Optional[str] = None
    default_jurisdiction: Optional[str] = None


class CompanyOut(BaseModel):
    id: str
    name: str
    turnstile_instance_url: Optional[str] = None
    is_active: bool = True
    created_at: datetime
    default_jurisdiction: Optional[str] = None


class SystemStatsOut(BaseModel):
    total_documents: int = 0
    total_chunks_embedded: int = 0
    total_chat_sessions: int = 0
    total_messages: int = 0
    company_doc_count: int = 0
    base_corpus_count: int = 0
    qdrant_status: str = "unknown"
    total_web_sources: int = 0
    web_sources_pending_review: int = 0
    total_users: int = 0
    pending_feedback: int = 0
    expired_documents: int = 0


# ── Analytics ─────────────────────────────────────────────────────────────────

class AnalyticsOut(BaseModel):
    top_queries: List[dict] = []
    zero_result_queries: List[dict] = []
    low_confidence_queries: List[dict] = []
    top_cited_docs: List[dict] = []
    feedback_summary: dict = Field(default_factory=dict)
    daily_query_counts: List[dict] = []
    pii_flagged_count: int = 0
    injection_flagged_count: int = 0


# ── Web Sources ───────────────────────────────────────────────────────────────

class WebSourceCreate(BaseModel):
    url: str
    label: str = Field(..., min_length=2, max_length=200)
    description: Optional[str] = None
    scope: WebSourceScope = WebSourceScope.PLATFORM
    company_id: Optional[str] = None
    scrape_frequency: ScrapeFrequency = ScrapeFrequency.WEEKLY
    crawl_depth: int = Field(1, ge=1, le=2)
    include_patterns: List[str] = []
    exclude_patterns: List[str] = []
    doc_type: DocumentType = DocumentType.REGULATORY
    jurisdiction: Optional[str] = None


class WebSourceOut(BaseModel):
    id: str
    url: str
    label: str
    description: Optional[str] = None
    scope: WebSourceScope
    company_id: Optional[str] = None
    scrape_frequency: ScrapeFrequency
    crawl_depth: int = 1
    include_patterns: List[str] = []
    exclude_patterns: List[str] = []
    doc_type: DocumentType
    is_active: bool = True
    last_scraped_at: Optional[datetime] = None
    last_chunk_count: int = 0
    last_scrape_error: Optional[str] = None
    change_detected_at: Optional[datetime] = None
    is_change_pending_review: bool = False
    created_at: datetime
    jurisdiction: Optional[str] = None


class WebSourceScrapeResult(BaseModel):
    web_source_id: str
    url: str
    chunks_stored: int = 0
    content_hash: Optional[str] = None
    changed: bool = False
    significant_change: bool = False
    change_ratio: float = 0.0
    error: Optional[str] = None


# ── RAG internals ─────────────────────────────────────────────────────────────

class RetrievedChunk(BaseModel):
    doc_id: str
    chunk_id: str
    text: str
    doc_type: DocumentType
    source: DocumentSource
    title: str
    filename: str = ""
    raw_score: float
    boosted_score: float
    page_number: Optional[int] = None
    metadata: dict = Field(default_factory=dict)
