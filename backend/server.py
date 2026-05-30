"""
EHS Intelligent RAG — Main FastAPI app.
All endpoints under /api/*. Hybrid retrieval, streaming chat, audit logging, scheduled re-scrape.
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import init_indexes
from app.vector_store import get_vector_store
from app.audit import ensure_audit_indexes
from app.scheduler import start_scheduler, stop_scheduler
from app.routes.auth_routes import router as auth_router
from app.routes.chat_routes import router as chat_router
from app.routes.document_routes import router as docs_router
from app.routes.web_source_routes import router as web_sources_router
from app.routes.admin_routes import router as admin_router
from app.routes.audit_routes import router as audit_router

settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ehs-rag")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("EHS RAG starting up...")
    await init_indexes()
    await ensure_audit_indexes()
    logger.info("Mongo indexes ensured")
    vs = get_vector_store()
    await vs.ensure_collections()
    logger.info(f"Qdrant collections ready at {settings.qdrant_path}")

    # Pre-warm embedding models so first request isn't hit by lazy download race
    try:
        from app.embeddings import _get_dense, _get_sparse, _get_reranker
        _get_dense()
        _get_sparse()
        _get_reranker()
        logger.info("Embedding models pre-loaded (dense + BM25 + cross-encoder)")
    except Exception as e:
        logger.warning(f"Model pre-load failed: {e}")

    start_scheduler()
    yield
    stop_scheduler()
    logger.info("EHS RAG shutting down")


app = FastAPI(
    title="EHS Intelligent RAG API",
    description="Environment, Health & Safety AI assistant — hybrid RAG with re-ranking, streaming, OCR, and audit logging.",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")


@api.get("/")
async def root():
    return {"service": "EHS Intelligent RAG API", "version": "2.0.0"}


@api.get("/health")
async def health():
    vs = get_vector_store()
    status = await vs.health()
    return {"status": "healthy", "qdrant": status, "model": settings.claude_model}


api.include_router(auth_router)
api.include_router(chat_router)
api.include_router(docs_router)
api.include_router(web_sources_router)
api.include_router(admin_router)
api.include_router(audit_router)

app.include_router(api)
