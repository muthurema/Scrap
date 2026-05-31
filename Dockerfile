# ─── Stage 1: build React frontend ───────────────────────────────────────────
FROM node:20-alpine AS frontend-build
WORKDIR /frontend

# Install deps with cache. Copy package.json (and yarn.lock if present) then install.
# We use a glob so the build doesn't fail when yarn.lock isn't committed to the repo.
COPY frontend/package.json ./
COPY frontend/yarn.loc[k] ./
RUN if [ -f yarn.lock ]; then \
        yarn install --frozen-lockfile --network-timeout 600000; \
    else \
        yarn install --network-timeout 600000; \
    fi

# Build (BACKEND_URL is empty → same-origin axios calls, perfect for one-service deploy)
COPY frontend/ ./
ENV CI=false
ENV REACT_APP_BACKEND_URL=""
RUN yarn build


# ─── Stage 2: Python backend + bundled frontend ──────────────────────────────
FROM python:3.11-slim

# System libs needed by fastembed / qdrant / pytesseract / pdf parsing
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    tesseract-ocr \
    poppler-utils \
    libmagic1 \
    curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps (cached layer)
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r /tmp/requirements.txt \
 && pip install --no-cache-dir emergentintegrations \
      --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/

# Pre-download the 3 embedding models at build time so cold starts don't fetch
# them. ~120 MB extra image weight in exchange for 30-60s faster first request.
RUN python -c "from fastembed import TextEmbedding, SparseTextEmbedding; \
    TextEmbedding(model_name='BAAI/bge-small-en-v1.5'); \
    SparseTextEmbedding(model_name='Qdrant/bm25')"
RUN python -c "from huggingface_hub import snapshot_download; \
    snapshot_download('Xenova/ms-marco-MiniLM-L-6-v2')" || true

# Application code
COPY backend/ /app/backend/

# Frontend build artefacts → /app/frontend_build (mounted by server.py)
COPY --from=frontend-build /frontend/build /app/frontend_build

# Persistent data lives under /data on the Railway volume. Default paths in
# config.py write to /app/backend/uploads + /app/backend/qdrant_data, which we
# symlink to /data so a volume mount survives redeploys.
RUN mkdir -p /data/uploads /data/qdrant /data/hf_cache \
 && ln -sf /data/uploads /app/backend/uploads \
 && ln -sf /data/qdrant  /app/backend/qdrant_data

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/data/hf_cache \
    UPLOAD_DIR=/app/backend/uploads \
    QDRANT_PATH=/app/backend/qdrant_data \
    FRONTEND_BUILD_DIR=/app/frontend_build \
    PORT=8001

EXPOSE 8001
WORKDIR /app/backend

# Railway sets $PORT; bind there. The volume at /data replaces build-time
# contents on mount, so we create the required subdirs at runtime before
# uvicorn starts. Single worker since fastembed/Qdrant aren't fork-safe.
CMD ["sh", "-c", "mkdir -p /data/uploads /data/qdrant /data/hf_cache && exec uvicorn server:app --host 0.0.0.0 --port ${PORT:-8001} --workers 1 --timeout-keep-alive 75"]
