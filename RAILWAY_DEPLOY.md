# Railway Deployment Guide — Turnstile360 RAG

This guide deploys the full app (React frontend + FastAPI backend) as a **single Railway service** using the provided `Dockerfile`. MongoDB is added as a separate Railway service. A persistent **volume** keeps Qdrant + uploaded PDFs + the HuggingFace model cache alive across redeploys.

Estimated time: **15 minutes**.

---

## 0. Prerequisites

- A Railway account (https://railway.com — pay-as-you-go, ~$5–10/mo for this stack)
- Your code on GitHub (Emergent's "Save to GitHub" button works perfectly)
- Your **Emergent Universal Key** (from Profile → Universal Key) — used for Claude calls

---

## 1. Push the latest code to GitHub

In the Emergent chat input, click **"Save to GitHub"** and pick a repo (e.g. `turnstile360-rag`). The Dockerfile, `.dockerignore`, and `railway.json` are already in the repo root.

---

## 2. Create the Railway project

1. Go to https://railway.com/new → **"Deploy from GitHub repo"** → pick your repo
2. **CRITICAL** — Once the service appears, click it → **Settings** → make these changes BEFORE you deploy:
   - **Root Directory**: leave **empty** (do NOT set to `/backend` — that makes Railway ignore our Dockerfile and use Railpack auto-detection instead, which causes the build to fail on private packages)
   - **Builder**: select **Dockerfile** (path: `Dockerfile`)
   - **Watch Paths**: `**` (rebuild on any change)
3. Railway will detect the `Dockerfile` at the repo root
4. **Do NOT click Deploy yet** — we need to add Mongo + a volume + env vars first

> If you already deployed and got the build error about `emergentintegrations==0.1.2`: open Service → Settings → switch Builder to **Dockerfile** with path `Dockerfile`, set Root Directory to empty, then redeploy.

---

## 3. Add MongoDB

Two options:

### Option A — Railway's MongoDB plugin (simplest)
1. In your Railway project canvas → **"+ New"** → **Database** → **MongoDB**
2. Railway provisions a Mongo instance and auto-creates a `MONGO_URL` variable inside the project
3. In your **backend service** → **Variables** tab → **"+ New Variable Reference"** → pick `MongoDB.MONGO_URL`
4. Add another variable: `DB_NAME=ehs_rag`

### Option B — MongoDB Atlas (free tier, more portable)
1. Create a free M0 cluster at https://cloud.mongodb.com
2. Network Access → "Allow access from anywhere" (0.0.0.0/0)
3. Database Access → create a user with `readWrite` on your DB
4. Get the connection string: `mongodb+srv://<user>:<pwd>@cluster.mongodb.net`
5. In the Railway backend service → Variables: `MONGO_URL=mongodb+srv://...` and `DB_NAME=ehs_rag`

---

## 4. Attach a persistent volume

Without this, every redeploy wipes Qdrant + uploaded PDFs + the model cache.

1. Click your backend service → **Volumes** tab → **"+ New Volume"**
2. **Mount path**: `/data`
3. Size: **5 GB** is plenty (Qdrant ~500 MB, uploads up to ~3 GB, HF cache ~150 MB)

The Dockerfile already symlinks `/app/backend/uploads`, `/app/backend/qdrant_data`, and the HF cache to `/data/*`, so this just works.

---

## 5. Set environment variables

In the backend service → **Variables** tab, add each line:

```
DB_NAME=ehs_rag
SECRET_KEY=<generate a 64-char random string, e.g. `openssl rand -hex 32`>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
EMERGENT_LLM_KEY=sk-emergent-XXXXXXXXXX
CLAUDE_MODEL=claude-sonnet-4-6
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
EMBEDDING_DIMENSIONS=384
MAX_UPLOAD_SIZE_MB=300
CORS_ORIGINS=*
ADMIN_EMAIL=admin@yourcompany.com
ADMIN_PASSWORD=<a strong password — you'll log in with this first>
ADMIN_FULL_NAME=Platform Owner
```

> `MONGO_URL` was already set in step 3. `PORT` is auto-injected by Railway — don't set it.

---

## 6. Configure resources

Railway service → **Settings** → **Resources**:

- **Memory**: **2 GB minimum** (4 GB recommended for comfort)
  - Why: fastembed dense + BM25 sparse + cross-encoder reranker + Qdrant + Python ~1.5 GB baseline. The OOM you saw on Emergent's deploy was the 1 GB default.
- **CPU**: 1 vCPU is fine; bumps to 2 if ingestion of textbook-sized PDFs feels slow

---

## 7. Deploy

1. Click **Deploy** on the backend service
2. Build takes **5–8 minutes** the first time (Docker pulls Python + downloads embedding models in the image so subsequent cold-starts are instant)
3. Watch the **Deploy Logs** — you should see:
   ```
   Embedding models pre-loaded (dense + BM25 + cross-encoder)
   Application startup complete.
   Uvicorn running on http://0.0.0.0:<PORT>
   ```
4. Once live, visit `https://<service>.up.railway.app/api/health` — should return `{"status":"healthy","models_ready":true,...}`

---

## 8. Seed the admin user + base corpus

Railway service → **Settings** → **Deploy** → open a shell, or use Railway CLI:

```bash
railway shell
cd backend && python seed.py
```

Output:
```
=== EHS RAG Seed ===
Created admin user: admin@yourcompany.com / <your-password>
  Created: 7, Skipped: 0, Failed: 0, Total chunks: 87
=== Seed complete ===
```

Or you can simply log in as the admin and hit **Admin → Stats → "Re-seed Corpus"** in the UI — it does the same thing without shelling in.

---

## 9. Custom domain (optional)

1. Railway service → **Settings** → **Networking** → **Generate Domain** (gives you `<service>.up.railway.app`)
2. Or **"+ Custom Domain"** → enter `rag.yourcompany.com`
3. Railway shows a CNAME target → add it in your DNS provider (Cloudflare, Namecheap, etc.)
4. Wait 1–5 minutes for SSL provisioning

---

## 10. Verify

1. Open `https://<your-domain>` → React app loads with Turnstile360 branding
2. Log in with the seeded admin credentials
3. Admin → Stats → confirm corpus is healthy (green card, ~85+ chunks)
4. Upload a 100 MB textbook PDF as a smoke test — should return 201 in a few seconds (no more 413/520/502)
5. Send a chat query — should stream with citations

---

## Updating / redeploying

Just push to GitHub. Railway auto-builds and deploys on every push to `main`. Your data on `/data` survives.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Build fails on `yarn install` | Network blip | Retry deploy |
| Container OOM-killed | < 2 GB RAM allocated | Bump memory in Settings → Resources |
| `/api/health` returns 503 with `models_ready: false` | HF download failed | Check egress; the retry logic gives up after 3 attempts, redeploy |
| `MONGO_URL` not set error on startup | Forgot step 3 | Add the variable, redeploy |
| Uploads return 413 | A reverse-proxy in front of Railway (Cloudflare?) caps body size | Disable Cloudflare proxy (gray cloud) OR raise the limit in Cloudflare → Network → Max Upload Size |
| Login returns "Invalid email or password" on first run | Seed didn't run | Run `python seed.py` via Railway shell |
| Backend logs show `Dense/Sparse search ... operands could not be broadcast together with shapes (N,) (M,)` | Qdrant index corrupted by a killed (OOM, restart) ingestion mid-write | In the app: **Admin → Stats → "Reset Base Index"** (or "Reset Company Index") to wipe + recreate that collection, then re-upload docs (or run **Force Re-seed Corpus** for the base corpus). The chat will still respond meanwhile but with no retrieved sources from the broken collection. |
| Chat answers appear all at once after a long pause instead of streaming token-by-token | Reverse-proxy (Railway/Cloudflare/Nginx) buffering the SSE response | Already handled in code: 2KB SSE pad on first chunk + `:ping` keepalive every 2 s + `X-Accel-Buffering: no` header. If still buffered, set Cloudflare → Network → "HTTP/3" **off** and ensure the orange cloud is **grey** for the backend hostname. |
| Backend pod OOMs repeatedly during large uploads or with a big corpus | Embedded Qdrant + 300MB upload limit + fastembed models all share the backend pod's RAM | (1) Lower max upload size: set `MAX_UPLOAD_SIZE_MB=50` on the backend service. (2) Move Qdrant out of the backend pod — see **"Optional: External Qdrant service"** below. |


## Optional: External Qdrant service (recommended at >1GB index size)

By default Qdrant runs **embedded in the backend pod** (file-mode SQLite + HNSW). This is simple but means the vector index lives in your backend's RAM. Once the index passes ~1GB, you'll see periodic OOMs even with healthy upload sizes.

**Fix:** Spin up Qdrant as a **separate Railway service** using the included `Dockerfile.qdrant` + `qdrant.railway.json`. Your backend then connects over Railway's internal network.

### Setup steps

1. **Create a new Railway service** from the same GitHub repo. Set:
   - **Root Directory:** `/` (repo root)
   - **Dockerfile Path:** `Dockerfile.qdrant`

2. **Attach a Railway Volume** to the Qdrant service:
   - Service → **Volumes → Add Volume**
   - **Mount path: `/qdrant/storage`** (must match `QDRANT__STORAGE__STORAGE_PATH` baked into the Dockerfile)
   - Size: 10 GB to start
   - ⚠️ **Do not add a `VOLUME` instruction to the Dockerfile** — Railway rejects images that declare Docker VOLUMEs at build time. The Dockerfile in this repo intentionally has none; the volume is attached via the dashboard.

3. **Expose the service internally.** Railway gives every service a private domain like `qdrant.railway.internal`. You do NOT need to expose a public domain.

4. **On your backend service**, reference the Qdrant service's dynamic port via Railway variable references:
   ```
   QDRANT_URL=http://qdrant.railway.internal:${{Qdrant.PORT}}
   ```
   Replace `Qdrant` with the exact name of your Qdrant service in Railway. The `${{...}}` syntax is Railway's service-discovery — it auto-resolves the Qdrant service's dynamically-assigned `$PORT` so the backend can reach it even after Railway rotates the port.

   (Optionally `QDRANT_API_KEY=<your-secret>` if you set `QDRANT__SERVICE__API_KEY` on the Qdrant service.)

5. **Redeploy the backend.** On boot you'll see `Connecting to external Qdrant at http://qdrant.railway.internal:<port>` in the logs.

6. **Bring over your existing data** (skip if you're OK re-seeding from scratch). Two helper scripts ship in `/app/backend`:

   **A. Migrate vectors from your old embedded Qdrant → the new remote service:**
   ```bash
   # Run on the backend pod BEFORE flipping QDRANT_URL (so the old data
   # is still accessible at the local volume path):
   QDRANT_LOCAL_PATH=/app/backend/qdrant_data \
   QDRANT_REMOTE_URL=http://qdrant.railway.internal:${{Qdrant.PORT}} \
   python /app/backend/migrate_qdrant_local_to_remote.py
   ```
   Idempotent: uses original point IDs so re-running just overwrites. ~200 points/batch. For a typical 5–10 k chunk corpus this runs in <60 s.

   **B. Backfill `tier` + `freshness_ts` on chunks ingested before v3.8:**
   ```bash
   # Run AFTER you've switched QDRANT_URL — fills in the diagram-parity
   # metadata on every existing chunk without re-embedding.
   QDRANT_URL=http://qdrant.railway.internal:${{Qdrant.PORT}} \
   python /app/backend/backfill_chunk_metadata.py
   ```

   Otherwise: skip these and use **Admin → Stats → Force Re-seed Corpus** to rebuild the base corpus from scratch (company docs must be re-uploaded manually).

### Why the Dockerfile uses a shell entrypoint
Railway assigns each service a dynamic `$PORT` at container start and routes **all health checks + internal network traffic** to that port. Qdrant defaults to port 6333 and ignores `$PORT`, so without a wrapper the healthcheck fails with "service unavailable" and Railway rolls the deploy back. The `Dockerfile.qdrant` in this repo runs a tiny `sh -c` entrypoint that exports `QDRANT__SERVICE__HTTP_PORT=${PORT:-6333}` before launching Qdrant — solves the issue with zero runtime overhead.

### Expected savings
- Backend pod RAM drops by **300-800 MB** typically (depending on corpus size)
- Backend OOMs disappear under normal load
- Qdrant service can be sized independently (Railway lets you set memory per service)
- The fastembed model constraint (single-worker) **still applies** to the backend, but is no longer the bottleneck

### Things to know
- **Network latency:** Internal Railway networking adds ~1-3ms per Qdrant call. Negligible vs the 5-50ms of the embedding itself.
- **Cold start:** External Qdrant starts in ~3-5s on Railway. If the backend boots faster, the first `/api/health/qdrant` may flap briefly — the `_ensure_collections_sync` call retries internally.
- **Rolling back:** Just remove the `QDRANT_URL` env var and redeploy. Backend reverts to embedded mode. (Data lives in the volume of the Qdrant service, so it's safe to leave the service running while you fall back.)

---

## Cost estimate (Railway pricing as of Feb 2026)

- **Hobby plan**: $5/mo base
- **Backend service**: ~$10/mo (2 GB RAM, 1 vCPU, always-on)
- **Mongo plugin**: ~$5/mo (or free with MongoDB Atlas M0)
- **Volume (5 GB)**: ~$1.25/mo

**Total: ~$15–20/mo** for a fully-isolated, persistent-data, autoscaling-ready production deployment.
