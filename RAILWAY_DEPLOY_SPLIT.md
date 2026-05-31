# Railway Split Deployment — Backend + Frontend as Separate Services

Use this if you want the frontend on a CDN-edge nginx and the backend on its own scalable service. Compared to the single-service deploy in `RAILWAY_DEPLOY.md`:

| Aspect | One-service | Split (this doc) |
|---|---|---|
| Services to manage | 1 | 2 |
| Cold-start cost | shared | backend scales separately, frontend ~instant |
| Frontend caching | served by Python | nginx + Cloudflare-friendly |
| Build time | longer (one Docker build) | parallel builds |
| Cost (~Feb 2026) | ~$15/mo | ~$20-25/mo |

Estimated time: **20 minutes**.

---

## 1. Push to GitHub

Use Emergent's **"Save to GitHub"** button. The repo will contain:
- `Dockerfile.backend` — backend-only image
- `frontend/Dockerfile` + `frontend/nginx.conf` — frontend nginx image
- `Dockerfile` — the combined single-service image (you'll ignore this for the split deploy)

---

## 2. Create the BACKEND service on Railway

1. https://railway.com/new → **"Deploy from GitHub repo"** → pick your repo
2. Once the service appears, click it → **Settings**:
   - **Root Directory**: leave **empty**
   - **Builder**: **Dockerfile**
   - **Dockerfile Path**: `Dockerfile.backend`
3. **Variables** tab — add (MongoDB, secrets, LLM key):
   ```
   DB_NAME=ehs_rag
   SECRET_KEY=<openssl rand -hex 32>
   JWT_ALGORITHM=HS256
   ACCESS_TOKEN_EXPIRE_MINUTES=1440
   EMERGENT_LLM_KEY=sk-emergent-XXXXXXXXXX
   CLAUDE_MODEL=claude-sonnet-4-6
   EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
   EMBEDDING_DIMENSIONS=384
   MAX_UPLOAD_SIZE_MB=300
   ADMIN_EMAIL=admin@yourcompany.com
   ADMIN_PASSWORD=<a strong password>
   ADMIN_FULL_NAME=Platform Owner
   ```
   `MONGO_URL` will be set in step 3. `CORS_ORIGINS` will be set in step 6 (after we know the frontend URL).
4. **Volumes** tab → **+ New Volume** → mount path `/data`, size **5 GB**
5. **Settings → Resources** → Memory **≥2 GB** (4 GB recommended)
6. **Settings → Networking** → **Generate Domain** (copy this URL, e.g. `ehs-backend-production-1234.up.railway.app`)
7. **Don't deploy yet** — wait for Mongo.

---

## 3. Add MongoDB

Same as the one-service guide:

### A. Railway plugin (easy)
1. Project canvas → **+ New** → **Database** → **MongoDB**
2. Backend service → Variables → **+ New Variable Reference** → pick `MongoDB.MONGO_URL`

### B. MongoDB Atlas (free M0 tier)
1. https://cloud.mongodb.com → create M0 cluster
2. Network Access → allow `0.0.0.0/0`
3. Backend service → Variables → add `MONGO_URL=mongodb+srv://...`

---

## 4. Deploy the backend

Click **Deploy** on the backend service. Build takes ~5-8 min the first time (pre-downloads the embedding models). When done:

```
https://<your-backend>.up.railway.app/api/health
```
should return `{"status":"healthy", "models_ready": true, ...}`

If it doesn't, check **Deploy Logs** — usually a missing env var.

---

## 5. Create the FRONTEND service

1. In the same Railway project → **+ New** → **GitHub Repo** → same repo
2. Once the new service appears, click it → **Settings**:
   - **Root Directory**: `frontend`
   - **Builder**: **Dockerfile**
   - **Dockerfile Path**: `Dockerfile` (Railway will read `frontend/Dockerfile`)
3. **Variables** tab — add (the only one that matters):
   ```
   REACT_APP_BACKEND_URL=https://<your-backend>.up.railway.app
   ```
   > **CRITICAL**: This is baked in at build time. If you change it later, you MUST trigger a fresh build, not just a restart.
4. **Settings → Networking** → **Generate Domain** (copy the frontend URL, e.g. `ehs-frontend-production-5678.up.railway.app`)
5. **Settings → Resources** → Memory **256 MB** is plenty for nginx
6. **Deploy** → takes ~3-5 min.

---

## 6. Wire CORS

Back to the **backend** service → Variables:
```
CORS_ORIGINS=https://<your-frontend>.up.railway.app,https://rag.yourcompany.com
```
(comma-separated list of every origin that will call the backend). Railway redeploys the backend automatically.

---

## 7. Seed admin + base corpus

Backend service → top-right "..." menu → **"Open shell"** (Railway CLI works too: `railway shell`)

```bash
cd backend && python seed.py
```

Or skip the shell and just log in once at `https://<frontend-domain>` with your seeded `ADMIN_EMAIL` / `ADMIN_PASSWORD`, then click **Admin → Stats → Re-seed Corpus**.

---

## 8. Custom domains (optional)

- Backend service → Settings → Networking → **+ Custom Domain** → `api.rag.yourcompany.com`
- Frontend service → Settings → Networking → **+ Custom Domain** → `rag.yourcompany.com`
- After both have SSL provisioned, update the frontend's `REACT_APP_BACKEND_URL=https://api.rag.yourcompany.com` and the backend's `CORS_ORIGINS=https://rag.yourcompany.com` then redeploy each.

---

## Verify

1. Visit `https://<frontend-domain>` → React app loads
2. Open DevTools → Network → log in. The `/api/auth/login` request should hit your backend URL with status 200
3. Upload a textbook PDF — 201, no 413/520
4. Send a chat query — streams with citations

---

## Why split deploy fixes the OOM you hit on Emergent

- **Frontend service** is just nginx serving static files — almost zero RAM, scales to many concurrent users for free
- **Backend service** can be sized independently to **3-4 GB** so fastembed + Qdrant + the cross-encoder fit comfortably
- Frontend cold-starts are sub-second; only the backend does the heavy 30-60s model load (once, on volume cache hit it's instant)

---

## Updating

Push to GitHub → both services rebuild automatically. They share the repo but Railway's Watch Paths means only the service whose files changed actually redeploys (set `frontend/**` on the frontend, `backend/**` on the backend in Settings → Watch Paths if you want this optimisation).

---

## Cost (Feb 2026)

- Backend: 2-4 GB RAM, always-on → ~$10-15/mo
- Frontend: 256 MB nginx → ~$2-3/mo
- MongoDB plugin: ~$5/mo (or free Atlas M0)
- Volume (5 GB): ~$1.25/mo

**Total: ~$20-25/mo** for a fully-isolated, scalable, persistent production stack.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Frontend loads but every API call returns CORS error | `CORS_ORIGINS` not set or doesn't match frontend URL exactly | Update backend `CORS_ORIGINS` to include the exact frontend origin (no trailing slash) |
| Frontend loads but axios calls `http://localhost:8001` | `REACT_APP_BACKEND_URL` not set during build | Set it in frontend service Variables and **redeploy** (not just restart) |
| Login works but uploads return 413 | Cloudflare proxy in front of the backend | Disable proxy (gray cloud) or raise Cloudflare's max body size to 500 MB |
| `/api/health` returns 503 with `models_ready: false` | First boot still downloading models | Wait 60s; the volume caches them so subsequent boots are instant |
