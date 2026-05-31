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
    REGIONAL_BASE = "regional_base"  # Country/region-specific authoritative content (UK HSE, Safe Work AU, etc.)
    CLIENT_WEB = "client_web"
    PLATFORM_WEB = "platform_web"


class KnowledgeTier(str, Enum):
    """Diagram-parity 3-tier knowledge model.

    GLOBAL   — International regulators + standards (ILO, ISO, GHS, OSHA when used as global reference)
    REGIONAL — Jurisdiction-specific authoritative content (UK HSE, Safe Work AU, Singapore MOM, India Factories Act…)
    COMPANY  — Tenant-specific SOPs, policies, audits, permits (always highest precedence on conflict)
    """
    GLOBAL = "global"
    REGIONAL = "regional"
    COMPANY = "company"


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
    DocumentSource.REGIONAL_BASE: 1.05,
    DocumentSource.BASE_CORPUS: 1.0,
}


# Static map: DocumentSource → KnowledgeTier (used at ingest time to stamp
# every chunk's payload with `tier`. Retrieval uses this for the per-tier
# boost in rag_engine.retrieve.)
SOURCE_TO_TIER: dict[DocumentSource, KnowledgeTier] = {
    DocumentSource.SUPERADMIN: KnowledgeTier.COMPANY,
    DocumentSource.TURNSTILE_DMS: KnowledgeTier.COMPANY,
    DocumentSource.CLIENT_WEB: KnowledgeTier.COMPANY,
    DocumentSource.PLATFORM_WEB: KnowledgeTier.GLOBAL,
    DocumentSource.BASE_CORPUS: KnowledgeTier.GLOBAL,
    DocumentSource.REGIONAL_BASE: KnowledgeTier.REGIONAL,
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
        # Fail-fast with a clear error when a required env var is missing
        def _required(name: str) -> str:
            v = os.environ.get(name)
            if not v:
                raise RuntimeError(
                    f"Required env var '{name}' is not set. "
                    f"Set it in your Railway service Variables tab and redeploy."
                )
            return v

        self.mongo_url = _required("MONGO_URL")
        self.db_name = _required("DB_NAME")
        self.secret_key = _required("SECRET_KEY")
        self.cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
        self.emergent_llm_key = os.environ.get("EMERGENT_LLM_KEY", "")
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
        # Cap ONNX intra-op threads for embedding models so background
        # ingestion can't monopolize every CPU core (which would slow down
        # bcrypt-based login and chat streaming). Default: half the cores,
        # min 2, max 8 — leaves room for concurrent request handling.
        _cpu = os.cpu_count() or 4
        self.embed_onnx_threads = int(
            os.environ.get("EMBED_ONNX_THREADS", str(max(2, min(8, _cpu // 2))))
        )
        # HyDE query rewrite is run in PARALLEL with raw retrieval. If it
        # doesn't return within this budget we ignore its result and rely
        # on the raw-query results. Keeps p95 latency bounded.
        self.hyde_timeout_s = float(os.environ.get("HYDE_TIMEOUT_S", "2.5"))

        # ── Optional direct Anthropic path (enables prompt caching) ──
        # If ANTHROPIC_API_KEY is set we bypass the Emergent universal-key
        # proxy and call Anthropic directly via litellm's native anthropic
        # provider. This unlocks `cache_control` on the system prompt
        # (~10x faster + 90% cheaper on cached input tokens). When unset,
        # falls back to the existing Emergent proxy path automatically.
        self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY") or ""
        self.anthropic_direct_model = os.environ.get(
            "ANTHROPIC_DIRECT_MODEL", "claude-sonnet-4-5-20250929",
        )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
