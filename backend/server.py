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
from app.routes.user_routes import router as user_router
from app.routes.feedback_routes import router as feedback_router, ensure_feedback_indexes
from app.routes.analytics_routes import router as analytics_router
from app.routes.acknowledgement_routes import router as ack_router, ensure_ack_indexes
from app.routes.team_routes import router as team_router

settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ehs-rag")


_models_ready = {"value": False, "error": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("EHS RAG starting up...")
    await init_indexes()
    await ensure_audit_indexes()
    await ensure_feedback_indexes()
    await ensure_ack_indexes()
    logger.info("Mongo indexes ensured")
    vs = get_vector_store()
    await vs.ensure_collections()
    logger.info(f"Qdrant collections ready at {settings.qdrant_path}")

    # Pre-warm embedding models with retries — HuggingFace cold downloads
    # occasionally flap on first deploy. Try up to 3 times with backoff.
    import asyncio
    from app.embeddings import _get_dense, _get_sparse, _get_reranker
    for attempt in range(1, 4):
        try:
            _get_dense()
            _get_sparse()
            _get_reranker()
            _models_ready["value"] = True
            _models_ready["error"] = None
            logger.info("Embedding models pre-loaded (dense + BM25 + cross-encoder)")
            break
        except Exception as e:
            _models_ready["error"] = str(e)
            wait = 5 * attempt
            logger.warning(f"Model pre-load attempt {attempt}/3 failed: {e} — retrying in {wait}s")
            if attempt < 3:
                await asyncio.sleep(wait)
    if not _models_ready["value"]:
        logger.error(f"Model pre-load FAILED after 3 attempts: {_models_ready['error']}")

    # Auto-seed first-run admin user if the users collection is empty. Env vars:
    #   ADMIN_EMAIL / SEED_ADMIN_EMAIL → "admin@ehsrag.com"
    #   ADMIN_PASSWORD / SEED_ADMIN_PASSWORD → "Admin@12345"
    #   ADMIN_FULL_NAME → "EHS Superadmin"
    # This makes Railway deploys self-bootstrap — no shell-in needed.
    try:
        import os
        import uuid
        from datetime import datetime, timezone
        from app.db import users_col
        from app.auth import hash_password

        user_count = await users_col().count_documents({})
        if user_count == 0:
            admin_email = os.environ.get("ADMIN_EMAIL") or os.environ.get("SEED_ADMIN_EMAIL", "admin@ehsrag.com")
            admin_password = os.environ.get("ADMIN_PASSWORD") or os.environ.get("SEED_ADMIN_PASSWORD", "Admin@12345")
            admin_name = os.environ.get("ADMIN_FULL_NAME", "Platform Owner")
            await users_col().insert_one({
                "id": str(uuid.uuid4()),
                "email": admin_email,
                "hashed_password": hash_password(admin_password),
                "full_name": admin_name,
                "role": "superadmin",
                "company_id": None,
                "is_active": True,
                "needs_onboarding": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            logger.info(f"Auto-seeded first superadmin user: {admin_email}")
    except Exception as e:
        logger.warning(f"Auto-seed of admin user skipped: {e}")

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
    expose_headers=["*"],
)


# ── Global exception handler ────────────────────────────────────────────────
# Without this, an uncaught exception in a route returns a response that
# CORSMiddleware can't always wrap (Starlette can short-circuit before the
# CORS `send` hook runs). The browser then reports a misleading
# "No Access-Control-Allow-Origin header" CORS error and a generic
# `net::ERR_FAILED` instead of the real 500. Catching here guarantees a
# JSON response is sent, which CORSMiddleware *can* decorate with
# `Access-Control-Allow-Origin` so the client sees the real error message.
from fastapi.responses import JSONResponse
from fastapi import Request as _Request


@app.exception_handler(Exception)
async def _global_exception_handler(request: _Request, exc: Exception):
    logger.exception(f"Unhandled error on {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)[:200]},
    )

api = APIRouter(prefix="/api")


@api.get("/")
async def root():
    return {"service": "EHS Intelligent RAG API", "version": "2.0.0"}


@api.get("/health")
async def health():
    """
    Liveness probe — always returns 200 if the FastAPI process is up. The
    `models_ready` flag lets clients distinguish "alive but warming" from
    "fully ready". Returning 200 here (instead of 503) means Railway / k8s
    don't kill the pod while embedding models finish loading on first boot.

    NOTE: We intentionally do NOT call qdrant here. Qdrant's local file mode
    serializes every operation behind a single lock, so calling it during a
    big upsert would block the healthcheck for seconds. Qdrant status is
    available on the separate /api/health/qdrant endpoint.
    """
    return {
        "status": "healthy" if _models_ready["value"] else "warming",
        "model": settings.claude_model,
        "models_ready": _models_ready["value"],
        "models_error": _models_ready["error"],
    }


@api.get("/health/qdrant")
async def health_qdrant():
    """Detailed qdrant status — separate from /api/health so a slow vector
    store can't block the liveness probe."""
    vs = get_vector_store()
    try:
        qdrant_status = await vs.health()
    except Exception as e:
        qdrant_status = f"error: {e}"
    return {"qdrant": qdrant_status}


@api.get("/health/ready")
async def health_ready():
    """Strict readiness — 503 until embedding models loaded. Use this for k8s readiness probes."""
    from fastapi import Response
    if _models_ready["value"]:
        return {"ready": True}
    return Response(
        content=__import__("json").dumps({"ready": False, "error": _models_ready["error"]}),
        status_code=503, media_type="application/json",
    )


api.include_router(auth_router)
api.include_router(user_router)
api.include_router(chat_router)
api.include_router(docs_router)
api.include_router(web_sources_router)
api.include_router(admin_router)
api.include_router(audit_router)
api.include_router(feedback_router)
api.include_router(analytics_router)
api.include_router(ack_router)
api.include_router(team_router)

app.include_router(api)


# ── Static frontend (single-service deploy) ───────────────────────────────────
# When the React build exists at /app/frontend_build (e.g. inside the Railway
# Docker image), serve it from the same origin so REACT_APP_BACKEND_URL can be
# empty. /api/* routes already take precedence above.
import os
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

_FRONTEND_BUILD = Path(os.environ.get("FRONTEND_BUILD_DIR", "/app/frontend_build"))
if _FRONTEND_BUILD.is_dir() and (_FRONTEND_BUILD / "index.html").exists():
    # Cache-bust hashed assets, but keep index.html short-cache so deploys roll out fast
    app.mount("/static", StaticFiles(directory=_FRONTEND_BUILD / "static"), name="static")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # /api/* is already handled by the router above; this only fires for unmatched paths
        candidate = _FRONTEND_BUILD / full_path
        if full_path and candidate.exists() and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_FRONTEND_BUILD / "index.html")

    logger.info(f"Serving React build from {_FRONTEND_BUILD}")
else:
    logger.info(f"No React build at {_FRONTEND_BUILD}; backend-only mode")
