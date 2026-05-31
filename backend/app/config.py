"""
Configuration: settings, document type / source enums, chunking strategies.
"""
import os
from enum import Enum
from dataclasses import dataclass
from functools import lru_cache


# ── Enums ─────────────────────────────────────────────────────────────────────

class DocumentType(str, Enum):
    SOP = "sop"
    INCIDENT_REPORT = "incident_report"
    RISK_ASSESSMENT = "risk_assessment"
    REGULATORY = "regulatory"
    TRAINING = "training"
    PERMIT = "permit"
    POLICY = "policy"
    MSDS = "msds"
    GENERAL = "general"


class DocumentSource(str, Enum):
    SUPERADMIN = "superadmin"
    TURNSTILE_DMS = "turnstile_dms"
    BASE_CORPUS = "base_corpus"
    CLIENT_WEB = "client_web"
    PLATFORM_WEB = "platform_web"


class WebSourceScope(str, Enum):
    PLATFORM = "platform"
    CLIENT = "client"


class ScrapeFrequency(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


# ── Chunking ──────────────────────────────────────────────────────────────────

@dataclass
class ChunkConfig:
    chunk_size: int
    chunk_overlap: int
    priority_boost: float


CHUNK_CONFIGS: dict[DocumentType, ChunkConfig] = {
    DocumentType.SOP: ChunkConfig(512, 100, 1.2),
    DocumentType.INCIDENT_REPORT: ChunkConfig(256, 50, 1.1),
    DocumentType.RISK_ASSESSMENT: ChunkConfig(512, 128, 1.3),
    DocumentType.REGULATORY: ChunkConfig(768, 150, 1.0),
    DocumentType.TRAINING: ChunkConfig(384, 75, 1.0),
    DocumentType.PERMIT: ChunkConfig(512, 100, 1.1),
    DocumentType.POLICY: ChunkConfig(512, 100, 1.4),
    DocumentType.MSDS: ChunkConfig(384, 64, 1.2),
    DocumentType.GENERAL: ChunkConfig(512, 100, 1.0),
}

SOURCE_BOOSTS: dict[DocumentSource, float] = {
    DocumentSource.SUPERADMIN: 1.5,
    DocumentSource.TURNSTILE_DMS: 1.3,
    DocumentSource.CLIENT_WEB: 1.3,
    DocumentSource.PLATFORM_WEB: 1.1,
    DocumentSource.BASE_CORPUS: 1.0,
}


def get_chunk_config(doc_type: DocumentType) -> ChunkConfig:
    return CHUNK_CONFIGS.get(doc_type, CHUNK_CONFIGS[DocumentType.GENERAL])


def get_combined_boost(doc_type: DocumentType, source: DocumentSource) -> float:
    type_boost = CHUNK_CONFIGS.get(doc_type, CHUNK_CONFIGS[DocumentType.GENERAL]).priority_boost
    source_boost = SOURCE_BOOSTS.get(source, 1.0)
    return round(type_boost * source_boost, 4)


DOC_TYPE_KEYWORDS: dict[DocumentType, list[str]] = {
    DocumentType.SOP: ["procedure", "standard operating", "step-by-step", "work instruction", "process flow", "safe work method"],
    DocumentType.INCIDENT_REPORT: ["incident", "accident", "near miss", "injury", "investigation", "root cause", "corrective action", "occurrence"],
    DocumentType.RISK_ASSESSMENT: ["hazard", "risk assessment", "hazop", "likelihood", "consequence", "control measure", "risk matrix", "bow-tie", "job safety analysis", "jsa"],
    DocumentType.REGULATORY: ["iso 45001", "iso 14001", "osha", "regulation", "standard", "clause", "compliance", "legal requirement", "statutory"],
    DocumentType.TRAINING: ["training", "induction", "competency", "learning objective", "assessment", "certification", "module"],
    DocumentType.PERMIT: ["permit to work", "hot work", "confined space", "excavation permit", "electrical isolation", "lock-out tag-out", "loto"],
    DocumentType.POLICY: ["policy", "commitment", "management system", "objectives", "scope", "responsibilities", "ehs policy"],
    DocumentType.MSDS: ["safety data sheet", "sds", "msds", "ghs", "hazardous substance", "flashpoint", "nfpa", "cas number"],
}


def detect_doc_type(text: str) -> DocumentType:
    text_lower = text.lower()
    scores = {dt: sum(1 for kw in kws if kw in text_lower) for dt, kws in DOC_TYPE_KEYWORDS.items()}
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else DocumentType.GENERAL


# ── Settings ──────────────────────────────────────────────────────────────────

class Settings:
    def __init__(self):
        self.mongo_url = os.environ["MONGO_URL"]
        self.db_name = os.environ["DB_NAME"]
        self.cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
        self.emergent_llm_key = os.environ.get("EMERGENT_LLM_KEY", "")
        self.secret_key = os.environ["SECRET_KEY"]
        self.jwt_algorithm = os.environ.get("JWT_ALGORITHM", "HS256")
        self.access_token_expire_minutes = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
        self.upload_dir = os.environ.get("UPLOAD_DIR", "/app/backend/uploads")
        self.qdrant_path = os.environ.get("QDRANT_PATH", "/app/backend/qdrant_data")
        self.qdrant_collection_company = os.environ.get("QDRANT_COLLECTION_COMPANY", "ehs_company_docs")
        self.qdrant_collection_base = os.environ.get("QDRANT_COLLECTION_BASE", "ehs_base_knowledge")
        self.embedding_model = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
        self.embedding_dimensions = int(os.environ.get("EMBEDDING_DIMENSIONS", "384"))
        self.claude_model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
        self.max_upload_size_mb = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "300"))


@lru_cache()
def get_settings() -> Settings:
    return Settings()
