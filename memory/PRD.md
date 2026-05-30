# EHS Intelligent RAG — Product Requirements Document

## Original Problem Statement
User uploaded `ehs-rag.zip` — a production-grade backend for an **EHS (Environment, Health & Safety) Intelligent RAG chatbot** designed for **Turnstile360** integration. Original backend was FastAPI + Qdrant (Docker) + Claude + OpenAI embeddings + SQLite. User asked: *"Can you create this? First plan and tell me"* and confirmed the following adaptations to the Emergent platform:

- **Qdrant** → in-process file-based local mode (no Docker)
- **SQLite** → **MongoDB** (motor)
- **Frontend** → full React UI required
- **API keys** → Emergent Universal Key (Claude only; OpenAI embeddings replaced with local fastembed)
- **Turnstile DMS sync** → stubbed/mock

## Architecture (Implemented)

| Layer | Tech |
|---|---|
| Backend | FastAPI on port 8001, all routes under `/api/*` |
| LLM | Claude `claude-sonnet-4-6` via `emergentintegrations.LlmChat` |
| Embeddings | `fastembed` ONNX (`BAAI/bge-small-en-v1.5`, 384-dim, local) |
| Vector DB | Qdrant local file mode at `/app/backend/qdrant_data` (2 collections: `ehs_company_docs` + `ehs_base_knowledge`) |
| Metadata DB | MongoDB (motor) — users, companies, documents, chat_sessions, chat_messages, web_sources |
| Auth | JWT (python-jose) + bcrypt; first registered user → superadmin |
| Frontend | React 19 + Tailwind + Shadcn UI + Phosphor icons + react-markdown + remark-gfm |
| Fonts | Chivo (display) + IBM Plex Sans (body) + IBM Plex Mono (labels) |

## User Personas
1. **Safety Engineer / EHS Officer** — asks technical EHS questions, reads dense citations
2. **Plant Manager** — wants quick procedure summaries (permits, incident response)
3. **Compliance Officer (Superadmin)** — uploads SOPs, manages web sources, reviews regulatory changes

## Core Requirements (Static)
- RAG retrieval with **priority boosting**:
  - Company uploads = 1.5× (Superadmin source)
  - Turnstile DMS sync = 1.3×
  - Base EHS corpus (OSHA/ISO) = 1.0×
- Doc-type-aware chunking (8 types × custom chunk_size / overlap / type-boost)
- Multi-format ingestion: PDF, DOCX, XLSX, TXT, CSV, MD
- Inline citation chips `[1]…[n]` in answers, hoverable source preview, dedicated sources panel
- Confidence score badge (avg of retrieved chunk boosted scores)
- Web source scraping with change detection (hash-diff) + pending-review flag
- Chat session history, multi-turn conversation, delete sessions
- Admin: stats dashboard (live), documents CRUD with reprocess, web sources CRUD with scrape-now

## What's Been Implemented (2026-05-30)

### Backend (`/app/backend`)
- `server.py` — FastAPI entry, mounts `/api` router
- `app/config.py` — Settings, DocumentType/Source enums, chunk configs, source boosts, doc-type auto-detect keywords
- `app/db.py` — Motor connection + collection accessors + indexes
- `app/auth.py` — bcrypt + JWT helpers, dependency injectors (`get_current_user`, `require_superadmin`)
- `app/embeddings.py` — fastembed local embeddings, asyncio.to_thread wrapped
- `app/vector_store.py` — Qdrant local file-mode singleton, upsert / search / delete / health
- `app/ingestion.py` — parsers (PDF/DOCX/XLSX/TXT) + RecursiveCharacterTextSplitter + chunking
- `app/rag_engine.py` — EHS system prompt, context builder, retrieve+answer via Claude
- `app/routes/auth_routes.py` — `/auth/register`, `/auth/login`, `/auth/me`
- `app/routes/chat_routes.py` — `/chat/`, `/chat/sessions`, `/chat/sessions/{id}/messages`
- `app/routes/document_routes.py` — upload (multipart, background processing), list, delete, reprocess
- `app/routes/web_source_routes.py` — CRUD + `/scrape` + change detection
- `app/routes/admin_routes.py` — `/admin/stats`, `/admin/companies`, `/admin/sync/turnstile` (stub)
- `seed.py` — creates admin user + 7 base-corpus EHS documents

### Frontend (`/app/frontend`)
- `App.js` — React Router with protected routes
- `lib/auth-context.js` — login/register/logout + localStorage persistence
- `lib/api.js` — Axios instance with Bearer token interceptor + 401 redirect
- `pages/LoginPage.jsx` — Swiss-aesthetic split layout, brand panel with priority boost cards, demo creds
- `pages/ChatPage.jsx` — Left session sidebar, center conversation, right sources panel (xl+), suggestion grid empty state, inline citations
- `pages/admin/AdminLayout.jsx` — Side nav for superadmin
- `pages/admin/StatsPage.jsx` — Live stat tiles (auto-refresh 10s), priority boost cards, chunking strategy table
- `pages/admin/DocumentsPage.jsx` — Upload dialog, document table with status badges + reprocess/delete
- `pages/admin/WebSourcesPage.jsx` — Add URL dialog, sources table with scrape-now + delete
- `components/MarkdownRenderer.jsx` — react-markdown with remark-gfm + inline `[n]` → citation chip transformer

### Seeded Data
- Admin user: `admin@ehsrag.com` / `Admin@12345` (superadmin)
- 7 base-corpus EHS documents, 9 embedded chunks total:
  1. OSHA Confined Space Entry (29 CFR 1910.146)
  2. ISO 45001 OH&S Management Systems
  3. Hot Work Permit Procedure
  4. LOTO — 29 CFR 1910.147
  5. Job Safety Analysis (JSA) Methodology
  6. Incident Investigation RCA Best Practices
  7. Chemical Safety — GHS, SDS, HazCom

## Test Status (iteration_1.json)
- **Backend:** 100% pass (16/16 pytest cases)
- **Frontend:** ~95% pass, all flows working
- Verified live: chat answer for "Explain the 6-step LOTO procedure" returns 8 sources w/ confidence 0.625; LOTO doc cited as primary source [1]
- Bug fixed: nested `<button>` in session sidebar (replaced outer with `<div role="button">`)
- Bug fixed: reprocess endpoint no longer crashes on inline-seeded docs (returns 400 with helpful message)

## Backlog / Future Enhancements

### P0 (Critical user value)
- ✅ Multi-tenant company isolation (data model already in place; needs UI for company-scoped views)

### P1 (High-impact features)
- Streaming chat (SSE via Anthropic streaming endpoint) — currently single-shot response
- Wire real Turnstile360 DMS API (currently stubbed in `/api/admin/sync/turnstile/{company_id}`)
- Background scheduler for periodic web-source scraping (APScheduler installed, not yet wired)
- OCR fallback for scanned PDFs (tesseract integration)
- Export answer with citations as PDF / share-link

### P2 (Polish)
- Add `DialogDescription` to Radix dialogs (a11y warning)
- Confidence/relevance threshold slider in admin
- Per-company embedding model selection
- Audit log of all chat queries (for compliance review)
- Voice input (Whisper STT via Universal Key)

## Mocked Integrations
- **Turnstile360 DMS sync** — `/api/admin/sync/turnstile/{company_id}` returns a mock summary `{new:0, updated:0, skipped:0, errors:0}` with a `note` field explaining the stub. Real HTTP integration deferred until customer provides the Turnstile API spec.

## Next Tasks
1. Test the new `<div role="button">` fix in browser (hot reload should pick up)
2. Wire streaming chat (Anthropic supports SSE; emergentintegrations has streaming support)
3. Activate APScheduler-based weekly web-source re-scrape on startup
4. Hook real Turnstile API once spec is provided
