# EHS Intelligent RAG — PRD v3.0

## Original Problem Statement
EHS (Environment, Health & Safety) RAG chatbot for Turnstile360 — adapted from uploaded zip with Qdrant in-process, MongoDB, full React UI, Emergent Universal Key (Claude), stubbed Turnstile sync. **v3** addresses comprehensive RAG-quality + security + product-feature audit from user.

## Architecture (v3.0)

### Backend
- FastAPI on port 8001, all `/api/*` prefixed
- **LLM**: Claude `claude-sonnet-4-6` via `litellm` → Emergent proxy (streaming + non-streaming)
- **Dense embeddings**: `fastembed` `BAAI/bge-small-en-v1.5` (384-dim ONNX)
- **Sparse embeddings**: `fastembed` BM25 (`Qdrant/bm25`)
- **Cross-encoder re-ranker**: `Xenova/ms-marco-MiniLM-L-6-v2`
- **HyDE**: Claude rewrites query into synthetic answer before retrieval
- **Vector DB**: Qdrant local file mode, NAMED vectors (`dense` + `bm25`)
- **Retrieval**: Hybrid (dense + sparse) → RRF fusion → cross-encoder rerank → jurisdiction boost
- **Metadata DB**: MongoDB collections — users, companies, documents, chat_sessions, chat_messages, web_sources, audit_logs, **feedback**
- **Auth**: JWT (bcrypt + python-jose); first user → superadmin; **needs_onboarding** flag
- **Scheduler**: APScheduler hourly tick, per-source due-check
- **OCR**: Tesseract + pdf2image + pytesseract (PDFs <50 chars or JPG/PNG uploads)

### Frontend
- React 19 + Tailwind + Shadcn + Phosphor + react-markdown + remark-gfm
- Routes: `/login`, `/onboarding`, `/chat`, `/admin/{stats,analytics,documents,web-sources,feedback}`
- **Typewriter buffer** (`lib/typewriter.js`) reveals burst-streamed tokens at ~80 chars/sec for smooth UX despite proxy buffering
- Fonts: Chivo (display) + IBM Plex Sans (body) + IBM Plex Mono (labels)

## v3.0 Features

### Streaming
- Server-side bursts confirmed (Emergent proxy buffers, not litellm) — fix is impossible server-side
- **Frontend typewriter** smooths bursts at ~80 chars/sec; queue drains gracefully on completion
- SSE order: `session` → `sources` → `token` (multi) → `done` (with `is_high_risk`, `suggested_followups`)
- Client swaps temp message_id with server-issued id on `session` event (enables feedback POST)

### Trust & Transparency (per user audit)
- **Source citations** with inline `[n]` chips + footer pills with hover preview
- **Source timestamps**: `last_updated` ISO date on every SourceReference
- **Source jurisdiction badge** on cards/hovers
- **"I don't know"** behaviour: enforced via system prompt
- **Confidence badge**: avg boosted_score × 100% on every assistant message
- **Hallucination guardrails**: never invent regulation/clause numbers, CAS, OEL/PEL/TLV unless verbatim in context
- **Disclaimer footer**: "AI-generated — not a substitute for professional EHS advice. Verify before acting."

### Safety-specific
- **High-risk auto-detection** via keywords (chemical spill, fire, emergency, fatal, H2S, electrocution, collapse, unconscious...)
- **Escalation banner** auto-prepended to high-risk answers: "⚠️ Immediate safety concern detected. If active emergency, stop and call EHS officer / emergency services NOW."
- **High-Risk badge** on assistant message header (rose color)

### Usability
- **5 suggested starter questions** on empty chat state
- **3 AI-generated suggested follow-ups** after every answer (Claude generates JSON array)
- **Copy answer button** on every assistant message (clipboard API + toast)
- **Thumbs up/down feedback** persisted to `feedback` collection, one row per message_id
- **Session history sidebar** (left panel, persisted, click-to-resume)

### Document management
- **Document versioning** via `supersedes_id` form field — uploading retires old doc's chunks from Qdrant and links the pair
- **Replace button** (ArrowsLeftRight icon) in documents table opens upload dialog pre-filled with old doc's metadata + "Replacing X" banner
- **Document expiry** via `expiry_date` field — expired docs excluded from RAG retrieval (`_is_doc_expired` filter); EXPIRED badge in admin UI
- **`include_superseded` query param** in GET /api/documents/

### Feedback review pipeline
- New `/admin/feedback` page — thumbs-down items with full chat context
- **SME annotation textarea** + save → `is_reviewed=true`
- **Annotations feed back into RAG**: `get_relevant_annotations` heuristic (≥2 long-word overlap) injects "## SME CORRECTIONS FROM PRIOR SIMILAR QUERIES" block into the prompt context as authoritative override
- Pending vs Reviewed filter tabs

### Analytics dashboard
- New `/admin/analytics` page
- **4 stat tiles**: Total Queries, Thumbs Up, Thumbs Down, PII/Injection
- **Daily Query Volume** bar chart
- **Top Queries** (top 15 by frequency)
- **Zero-Result Queries** (no sources retrieved — your document-ingestion backlog)
- **Low-Confidence Queries** (score <0.30 — gap analysis)
- **Top Cited Documents** (most-retrieved)

### User context (Batch E)
- New `/onboarding` page (one-time, post-register) — site, role label, jurisdiction, industry sector
- **7 jurisdictions** supported: US, UK, EU, AU, IN, CA, GLOBAL
- **13 industry sectors**: construction, manufacturing, oil_gas, mining, chemical, pharma, etc.
- `PATCH /api/users/me` updates profile + clears `needs_onboarding`
- **Jurisdiction-aware retrieval**: same-juris docs boosted ×1.15, different-juris docs ×0.85 — cross-juris citations get a "Note: this references [other-juris] guidance — verify against your local [user-juris] requirements" flag in the answer

### Security (carried + enhanced)
- Prompt-injection sanitization (input + document scan + jailbreak refusal phrase)
- SSRF protection (private IPs, loopback, AWS 169.254.169.254, multicast, link-local; pre-fetch + post-redirect)
- Audit logging for every destructive action (audit_logs collection + Stats widget)
- Secret masking + PII heuristic flag
- Hallucination guardrails on regulatory citations

## Test Status

| Iteration | Backend | Frontend | Notes |
|---|---|---|---|
| iter1 | 16/16 PASS | ~95% | 2 bugs fixed (nested button, reprocess crash) |
| iter2 | 14/14 PASS | ~98% | 0 critical bugs |
| iter3 | 22/22 PASS | ~70% → fixed | 3 frontend bugs fixed: missing useState, onboarding redirect, message_id swap |

## Mocked
- Turnstile360 DMS sync `/api/admin/sync/turnstile/{company_id}` returns mock summary — awaiting real Turnstile API spec

## v3.1 — Acknowledgement Workflow (NEW)

**Compliance evidence layer** — turns advisory chatbot into auditable EHS management tool. Required in most jurisdictions for demonstrating that workers received and accepted safety information.

### Backend
- New `acknowledgements` MongoDB collection with unique index on `(message_id, user_id)`
- `POST /api/acknowledgements/` with `{message_id}` — creates immutable ack
- `GET /api/acknowledgements/me` — user's own acks (last 50)
- `GET /api/acknowledgements/?high_risk_only=&user_id=` — superadmin
- `GET /api/acknowledgements/export/csv?high_risk_only=` — CSV download for regulatory audit
- **Snapshot at moment of ack** preserves: answer text, source titles, confidence score, user query, user site/role/jurisdiction/industry, IP, user-agent
- **Idempotent** — duplicate POST returns existing ack with `already=true`
- Chat message marked with `acknowledged_at` + `acknowledged_by` so reload shows status
- Every ack creates an `audit_logs` entry (`acknowledge_message` action)

### Frontend
- **`<CheckSquare/> Acknowledge (required)`** button on **high_risk** answers (amber, animate-pulse)
- **`<CheckSquare/> I understand`** button on normal answers (subtle, neutral)
- After ack: **`<SealCheck/> Acknowledged`** badge (emerald, immutable — no unack to preserve compliance integrity)
- New admin page `/admin/acknowledgements` — filterable table (All / High-Risk Only), expandable detail showing immutable answer snapshot + source titles + confidence + IP + user context, **Export CSV** button

### Test verification
- End-to-end: high-risk chat → ack POST → admin list shows entry with full user context (HQ / safety_officer / US juris / manufacturing) → CSV exports with all compliance fields → second ack returns `already=true`
- 6 admin nav items now: Stats, Analytics, Documents, Web Sources, Feedback Review, Acknowledgements

## Backlog

### Each is its own session
- **Multi-language detection + bilingual answers** (Claude can; needs UI + retrieval language tag)
- **Photo/image input** via Claude vision (drum labels, PPE photos, hazard photos)
- **Voice I/O** (Whisper STT + TTS) for hands-free field use
- **Incident report integration** with Turnstile360 (pre-fill incident from chat context)
- **SDS / chemical database integration** (PubChem API for live SDS lookup)
- **Offline / PWA mode** for low-connectivity field workers
- **Knowledge graph layer** on top of vectors for multi-hop reasoning
- **Notification & alerts** (regulation changes in your juris, permit renewals, document expiry warnings)
- **Compliance digest email** (Monday 8am with new pending reviews + top unanswered queries)
- **Refresh-token rotation** for production JWT

## v3.1 — Mobile / Tablet Responsiveness (Feb 2026)

### Implemented
- **ChatPage**: sidebar slides as drawer below `lg` (1024px) with backdrop overlay; hamburger trigger in header; "Online" short label on small screens; EmptyState `text-3xl sm:text-4xl lg:text-5xl`; chat input padding tightened; textarea `text-base` to prevent iOS Safari auto-zoom; message-action toolbar wraps
- **AdminLayout**: sidebar slides as drawer below `lg`; new mobile top-bar with hamburger + current section title; nav items auto-close drawer on tap
- **All Admin pages** (Stats, Analytics, Documents, WebSources, Feedback, Acknowledgements): `p-4 sm:p-6 lg:p-8`; headers stack vertically on small screens (`flex-col sm:flex-row`); H1 `text-3xl sm:text-4xl`; tables wrapped in `overflow-x-auto` with sensible `min-w-*` to preserve readability while scrolling horizontally
- **Stats / Analytics tiles**: `grid-cols-2` baseline so mobile shows 2×N instead of 1×N (more glanceable)
- **Dialogs** (Upload, WebSource): `w-[calc(100%-2rem)] max-h-[90vh] overflow-y-auto` so they never overflow viewport
- **LoginPage**: form padding `p-6 sm:p-8`; H2 `text-2xl sm:text-3xl`; renamed obscure `Authenticate` eyebrow → `Sign in`
- **OnboardingPage**: padding tightened on mobile
- Uses `h-[100dvh]` so iOS Safari url-bar resizing doesn't clip the layout

### Verified
- 375 × 800 (iPhone SE / 13 mini): chat drawer, EmptyState, suggestion grid, send button, admin grid all render without horizontal overflow
- 768 × 1024 (iPad portrait): admin tables scroll horizontally, headers wrap, chat full-width with hamburger

## v3.2 — Branding, Bulk Upload, Chat Refactor, Re-seed (Feb 2026)

### Implemented
- **Branding**: title `Turnstile360 RAG`, Turnstile360 logo as favicon (16/32/64/.ico) + login brand panel + chat sidebar + admin sidebar; "Made with Emergent" badge removed from `index.html` with CSS guard
- **Bulk document upload**: file picker `multiple={true}` with per-file progress bar + failure surface; settings apply to entire batch
- **Chat delete UX**: per-message Q&A pair delete, per-session sidebar delete (always-visible trash icon moved to the LEFT side of each row), header-level "delete current chat", "Clear all" bulk wipe; backend endpoints `DELETE /api/chat/messages/{id}`, `DELETE /api/chat/sessions`, `DELETE /api/chat/sessions/{id}`. Acknowledged messages are protected (409).
- **ChatPage refactor**: split 700-line `ChatPage.jsx` into `components/chat/{ChatSidebar,EmptyState,MessageRow,SourceCard,constants}.jsx`. Page now contains only state + controllers.
- **Admin Re-seed Corpus**: new endpoint `POST /api/admin/reseed-corpus?force=bool` and "Knowledge base health" panel on the Stats page with a one-click re-seed (idempotent) and a Force re-seed (red, confirms; deletes existing base-corpus docs before re-ingesting). Auto-detects empty corpus and shows an amber "Corpus is empty" warning.
- **DialogDescription** added to upload + web-source dialogs (fixes Radix a11y console warning)
- **seed.py** `import os` fix + `reseed_base_corpus()` extracted as a reusable async function

### Verified
- Streaming chat still works after refactor (sources retrieved, answer rendered)
- `POST /api/admin/reseed-corpus` returns 200 with `{ok, created, skipped, failed, total_chunks, errors}`
- Bulk upload tested back-to-back: 2 docs → both 201, count grew correctly
- Login / chat / admin all use the Turnstile360 logo at 32-40px

## v3.3 — Photo Input + IDOR Patches + Doodle Backdrop (Feb 2026)

### Implemented
- **🔒 IDOR fixes** (chat history isolation):
  - `GET /api/chat/sessions/{id}/messages` now checks ownership → 403 for other users
  - `POST /api/chat/stream` with someone else's `session_id` → 403
  - Verified via curl: cross-user read = 403, cross-user inject = 403, cross-user delete = 404
- **📎 Photo / image input via Claude vision**:
  - Paperclip button on chat input (left side of textarea); JPG/PNG/WEBP up to 5 MB each, max 3 per message
  - Thumbnails preview with × remove before send
  - User's images shown inline in the assistant's reply thread
  - Backend `/api/chat/stream` accepts `images: [data-url]` field; validated in `app/vision.py` (`parse_data_urls` + size/mime guards)
  - Non-streaming vision path via `emergentintegrations.LlmChat` + `ImageContent(image_base64=...)` model `claude-sonnet-4-6`
  - Single-shot SSE delivery so the existing frontend typewriter still gives a smooth reveal; RAG retrieval still runs and sources are still emitted
  - Test: red-triangle "DANGER FLAMMABLE" image → Claude correctly identified the hazard and cross-cited GHS/HazCom 2012, hot-work permit LEL <10%, JSA, ISO 45001 [1][2][3][4][5]
- **🎨 EHS doodle backdrop**:
  - Login left brand panel (inverted for dark bg, low opacity)
  - Chat empty-state with masked fade so it doesn't compete with the suggestions
- **📝 `/app/image_testing.md`** saved with the testing-agent rules from the playbook
- **schema**: `ChatMessageIn.images: Optional[list[str]]` (max 3)

### Skipped (per user)
- Multi-language detection / bilingual answers
- PWA / offline mode
- Incident-report integration with Turnstile360 (deferred until API spec)

## v3.4 — RBAC + Multi-tenant Roles (Feb 2026, Phase B)

### Implemented
**Roles & hierarchy**
- `superadmin` (app owner) — manages base corpus, all companies, all admins, global analytics
- `admin` (org head) — uploads org-scoped docs + URLs, manages org users, sees org analytics
- `user` (chat-only) — must belong to a company

**Backend**
- `app/auth.py` — new `require_admin` dependency + `generate_invite_code()` helper (8-char URL-safe)
- `app/db.py` — new collections `invites`, `allowlist` with indexes
- `app/schemas.py` — new models: `InviteCreate/Out`, `AllowlistAdd/Out`, `TeamMemberOut`; `UserCreate.invite_code`
- `app/routes/team_routes.py` (new) — full CRUD for invite codes, email allowlist, team members, deactivate user
- `app/routes/auth_routes.py` — register now gates by: (1) first user → superadmin; (2) invite code → role+company from code; (3) email allowlist match; (4) else 403
- `app/routes/document_routes.py` — admins upload to their company; superadmin to base_corpus; cross-tenant delete/reprocess blocked
- `app/routes/web_source_routes.py` — superadmin → platform scope, admin → client scope (their company), enforced server-side
- `GET /api/auth/lookup-company?code=...` — public endpoint so the register form can preview "Joining Acme Industries as user"

**Frontend**
- New page `admin/CompaniesPage` (superadmin only) — create + list companies
- New page `admin/TeamPage` (admin + superadmin) — tabs: Invite codes / Email allowlist / Members
  - Create invite (role, company for super, max-uses, expiry)
  - Just-created code shown in a copy-able green banner
  - Revoke / copy / status badges
  - Allowlist add/remove with role + company scope
  - Members table with role badges + deactivate button (admins can't deactivate other admins)
- `App.js` — admin routes accept `["superadmin", "admin"]`; Companies route nested with `["superadmin"]` guard; onboarding skipped for non-user roles
- `AdminLayout.jsx` — nav items filtered per role
- `ChatSidebar.jsx` — Admin Panel link shown to admin too
- `LoginPage.jsx` — register form gains an **Invite code** input with live company-name preview (debounced lookup via /auth/lookup-company)

### Verified (curl + browser)
1. Superadmin → creates Acme Industries company ✓
2. Superadmin → mints `admin` invite for Acme ✓
3. Register `acmeadmin@test.com` with code → returns `role=admin`, `company_id=<acme>` ✓
4. New admin logs in → lands on `/admin/stats` (no onboarding) ✓
5. Admin mints `user` invite ✓
6. Admin tries to mint `admin` invite → 403 ✓
7. Register `acmeworker@test.com` with code → role=user ✓
8. Register without invite or allowlist → 403 ✓
9. Admin adds email to allowlist → register with that email → role=user, joined Acme ✓
10. Regular user navigates to `/admin/*` → redirected to `/chat` (or `/onboarding` if needed) ✓
11. Bad code in register form → red "not recognised"; valid code → green "Joining Acme Industries" ✓

## Backlog
- Per-company analytics filtering (currently superadmin sees all; admin already filtered via `company_id` query in feedback/acks)
- Voice I/O (Whisper STT + TTS)
- Incident report integration with Turnstile360 (pending API spec)
- SDS / chemical database integration (PubChem)
- Diagnose production hang at rag.turnstile360.com (use Re-seed Corpus button after redeploy)
- Cleanup `// authenticate` placeholder comments across frontend/backend (P2)

## v3.11 — Bug fix: "answer is generated but not displayed; refresh shows it" (Feb 2026, P0)

### Symptom
User reported that after sending a chat message, the assistant message stayed empty during streaming but the answer appeared after a page refresh.

### Root cause
1. The Emergent LLM Key proxy occasionally throws `litellm.MidStreamFallbackError: ... Error building chunks for logging/streaming usage calculation` — a transient hiccup inside litellm's post-stream usage-accounting path. When this fires AFTER tokens were already streamed, our rag_engine jumped to `except`, yielded `event: error`, and never yielded `event: done`.
2. Frontend's error handler called `throw` → outer `catch` removed both temp messages with `setMessages((prev) => prev.filter(...))`. The user's question and the streamed answer disappeared from the UI.
3. Mongo's `final_text_holder["text"]` was only populated on the `done` event. Since `done` never arrived on the error path, the assistant message saved to Mongo had `content=""`. (The user occasionally saw answers after refresh because *some* requests completed cleanly — those persisted normally.)

### Fix
- `app/rag_engine.py stream()` — wrapped the `async for part in response:` token loop in try/except. If litellm raises AFTER the loop has produced >50 chars of content, we log the upstream warning and proceed to `done` with the partial; only re-raise (→ error event) when zero usable content was streamed.
- `app/routes/chat_routes.py event_gen()` — on every `token` event, append the delta to `final_text_holder["text"]` continuously. Mongo persistence in the `finally` block now always saves whatever was streamed, regardless of whether `done` arrived.
- `app/rag_engine.py done event` — `followups_pending` is now `True` only when the stream completed cleanly (else the lazy followups call would generate suggestions for a possibly-truncated answer).
- `ChatPage.jsx` error handler — on `event: error`, if the typewriter has revealed > 20 chars, mark the message `_streaming: false`, set `content` to the revealed text, flag `_partial: true`, and show a friendly warning toast instead of throwing. Outer catch only fires on a true zero-content failure.

### Verified
- Live SSE smoke ("What is OSHA?") with cleanly-completing stream: **18 token events streamed in 8 s**, `done` arrives, full answer rendered.
- Backend regression: 27/27 across iter5 + iter7 still passing.

## v3.10 — Hybrid Anthropic direct path + multi-tenant source filtering + clickable sources (Feb 2026)

User picked option (a) from v3.9. Three product changes, all tested end-to-end.

### 1. Hybrid Anthropic direct path (prompt caching support)
- `app/config.py` — new `ANTHROPIC_API_KEY` + `ANTHROPIC_DIRECT_MODEL` (default `claude-sonnet-4-5-20250929`) env vars (both unset by default)
- `app/rag_engine.py _litellm_params` — when `ANTHROPIC_API_KEY` is set, switches to direct litellm `anthropic/<model>` provider, converts the system message to Anthropic's content-block list with `cache_control={"type": "ephemeral"}`, and attaches the `anthropic-beta: prompt-caching-2024-07-31` header. When unset, falls back to the existing Emergent universal-key proxy path. Zero-risk activation/deactivation via env var.
- User can flip on by setting `ANTHROPIC_API_KEY=sk-ant-...` in Railway; expected ~1-3s TTFT win + ~90% input-token cost cut on cached calls; instant rollback by removing the env var.

### 2. Chat sources panel — company-only with multi-tenant isolation
- `app/routes/chat_routes.py` — the `sources` SSE event payload is now a typed envelope `{sources: [...company-only...], external_count: N}` instead of a bare array. The LLM still receives ALL retrieved chunks (global + regional + company) so answer quality is unchanged — ONLY the wire payload to the UI is filtered.
- Filter requires **BOTH** `tier == "company"` AND `company_id == current_user.company_id`. Critical: filtering on tier alone would have leaked Acme's chunks to a Beta admin or to a superadmin.
- Superadmin / users without a company see zero company sources by design + the `external_count` summary.
- `app/rag_engine.py chunks_to_sources` — now also stamps `company_id` on every `SourceReference` so the chat-route filter can match it.
- `app/schemas.py SourceReference` — new `company_id: Optional[str]` field.
- Frontend `ChatPage.jsx` — handles the new envelope shape with backward-compat for legacy bare-array payloads. Sources panel header renamed `RETRIEVED SOURCES` → `COMPANY SOURCES`. Empty-state copy now explains why ("external EHS guidance only — no internal SOPs matched") when external_count > 0. New `+N external references` pill at the bottom of the source list.

### 3. Clickable sources + doc preview
- New backend endpoints (both behind `_user_can_access_doc` ACL: superadmin everything / global+regional+platform-web open to all authenticated / company docs restricted to same company_id):
  - `GET /api/documents/{doc_id}` — single doc metadata for the preview modal
  - `GET /api/documents/{doc_id}/download` — streams the original file with `Content-Disposition: inline` so PDFs/images render in-browser
- Frontend `SourceCard.jsx` — refactored to render as a `<button>` when `onOpen` is provided; hover state + "⌕ Click to open" hint
- Frontend `ChatPage.jsx` — new `docPreview` state + shadcn `<Dialog>` modal showing: retrieved excerpt, jurisdiction/expiry/version metadata, and an "Open original file" button that downloads the blob via authenticated axios and pops it open in a new tab

### Verified
- **iteration_7 backend testing**: 14/15 → fixed cross-tenant leak → re-ran with iter6+iter7 → **29/29 PASSED**. Plus 12/12 iter5 regression = **41/41 across all suites**.
- Smoke: superadmin asking "What PPE for confined space?" → 0 company sources + 5 external_count (correct); answer still cites those external refs in-prose.

## v3.9 — Optimization audit follow-up (Feb 2026)

User shared a 12-point optimization guide. Audit: 8/12 already done in v3.6-v3.8, 2 quick wins applied, 2 we deliberately skip (with reason).

### Applied
- `rag_engine.retrieve()` default `top_n` lowered **6 → 5**. Saves ~200 prompt tokens per chat ⇒ ~300-600ms TTFT win, no quality loss observed.

### Investigated, NOT applied (with reason)
- **Anthropic prompt caching (`cache_control`)** — would save ~1-3s TTFT *if* it worked. It does not work through the current Emergent LLM Key proxy path (`litellm.acompletion` with `custom_llm_provider="openai"` against Emergent's `/llm` endpoint). The proxy normalizes to OpenAI chat-completions schema, which doesn't carry Anthropic's `cache_control` field. Enabling this would require switching to direct Anthropic API with the user's own Anthropic key — documented as a future backlog item.
- **Semantic answer cache** — declined: cross-tenant data leak risk (same question must return different company-tier answers per user), plus safety liability if a stale answer is served after an SOP update.
- **BART chunk compression** — declined: BART-large-CNN is ~1.5GB and ~300ms/chunk on CPU; on a Railway 2GB pod this would *increase* peak memory above what fastembed already uses, with a net latency loss.
- **Cluster-filtered search** — declined: pays off at 100k+ chunks; our largest collection is <10k. Existing `company_id` + `tier` payload filters already cut search space 80%+.

### Verified
- Smoke test post-restart: 18s total stream, sources at 4.8s, no errors, 27 tokens streamed.

## v3.8 — Latency optimizations + 3-tier knowledge architecture (Feb 2026)

User picked option (c) — full plan: latency P0+P1 plus diagram-parity 3-tier model and global URL seed.

### Latency wins (measured)
- `sources` SSE event: **7s → 4.8s** (parallel HyDE retrieval — raw + rewritten search in `asyncio.gather`, 2.5s HyDE timeout fallback)
- Total stream duration: **22-29s → 16s** (followups no longer block `done`; new lazy `POST /api/chat/sessions/{id}/followups` endpoint, idempotent + cached on the assistant message)
- Cached followups call: **159ms** (sub-second after first generation)
- Skip-rerank when ≤3 candidates: avoids 500ms-2s of cross-encoder CPU work on narrow queries
- LRU embedding cache (1000-entry, ~1.5 MB) for dense+sparse query vectors with whitespace-normalized SHA256 keys

### 3-tier knowledge architecture
- New `KnowledgeTier` enum: `GLOBAL` / `REGIONAL` / `COMPANY`
- New `DocumentSource.REGIONAL_BASE` for jurisdiction-specific authoritative content (UK HSE, Safe Work AU, Singapore MOM, India Factories Act, etc.)
- `SOURCE_TO_TIER` mapping stamps `tier` on every chunk payload at ingest time
- Every chunk now also carries `freshness_ts` (ISO UTC) — diagram parity item
- Retrieval-time tier boost: COMPANY 1.20× / REGIONAL 1.05× / GLOBAL 1.0× — compounds with existing jurisdiction boost
- Updated system prompt rule #1: "Three-tier precedence on conflict" with explicit COMPANY > REGIONAL > GLOBAL ordering
- `SourceReference.tier` field now exposed to the frontend (lets the chat UI show "Regional UK" / "Global ISO" / "Company SOP" badges)
- Superadmin upload route now accepts `source ∈ {base_corpus, regional_base}` — `regional_base` requires `jurisdiction` to be set (400 error otherwise)
- DocumentsPage UI updated: source dropdown now exposes Global vs Regional with helper text

### Pre-seeded global corpus
- New `python /app/backend/seed_global_sources.py` (idempotent) — registers 19 authoritative URLs as `WebSource` rows with `tier=global`, `scrape_frequency=weekly`:
  - International: ILO ×2, WHO, UNEP, UN GHS Purple Book
  - US: OSHA ×2, EPA, NIOSH
  - EU: EU-OSHA, ECHA, EU CSRD
  - ISO: 45001, 14001, 14064
  - Best practice: IOSH, NSC, EHS Daily Advisor, Campbell Institute

### Verified
- **iteration_6**: 14/14 PASSED + iter5 regression 12/12 PASSED, 0 critical
- Smoke: regional upload without jurisdiction → 400; with jurisdiction → 201 → tier=regional in chunks; delete → 204
- All existing chat / auth / docs / web-source flows intact

## v3.7 — CORS error on DELETE /documents/{id} in production (Feb 2026, P0 follow-up)

### Problem
User reported `Access to XMLHttpRequest at ... has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present` plus `net::ERR_FAILED` when deleting documents from chat.turnstile360.com. Misleading symptom — actually a downstream bug, not CORS misconfiguration. GET/POST/upload from the same origin worked.

### Root cause
`VectorStoreService._delete_sync` had no try/except. When the operator hit DELETE on a doc whose chunks live in the corrupted `ehs_base_knowledge` collection (the same one throwing `operands could not be broadcast`), qdrant raised an unhandled exception. Starlette terminated the response before CORSMiddleware's `send` hook could attach headers, so the browser saw an aborted connection and reported it as a CORS error.

### Fix
- `vector_store.py _delete_sync` — wrapped the qdrant `client.delete` call in try/except (like the search methods). On failure: logs a warning pointing the operator at `/api/admin/qdrant/reset`. The DELETE route now always completes (Mongo doc + file get cleaned up; chunks orphaned until the next collection reset).
- `server.py` — added a global `@app.exception_handler(Exception)` that returns a JSON 500 with CORS-decorated headers. Defense in depth — even an exception we missed will now show the real error in the browser instead of a misleading CORS error.
- Added `expose_headers=["*"]` to the CORS middleware so SSE-related headers (e.g. cache-control) are visible to client code.

### Verified
- DELETE on a freshly-uploaded doc: 204 + full CORS headers (`access-control-allow-origin`, `allow-methods: ...DELETE...`, `allow-credentials: true`, `expose-headers: *`)
- DELETE on a non-existent doc: 404 + same CORS headers
- SSE chat stream regression: 22-event flow still completes in ~20s
- Lint: clean

## v3.6 — Production hang on chat.turnstile360.com (Railway) — three stacked bugs (Feb 2026, P0)

### Problem
On the Railway production deployment, chat answers never appeared on screen. Three contributing root causes (the OOM corrupted the index, the corruption made retrieval return empty, the buffering hid streaming progress):

1. Railway/Cloudflare/Envoy proxies were **buffering the SSE response** until ~2KB of body accumulated, hiding all tokens until end of stream
2. **Qdrant local index in `ehs_base_knowledge` was corrupted** (`operands could not be broadcast together with shapes (4669,) (4667,)`) after Railway OOM-killed an in-flight ingestion
3. Per-doc **memory footprint during ingestion** (300MB raw bytes + BATCH=64 upsert + chunks) caused the Railway OOMs that produced (2)

### Fixes (all verified by testing agent iteration_5)
- `chat_routes.py event_gen` — first SSE frame is now a 2KB `:` comment pad to flush proxy buffers immediately; parallel `keepalive_pings` task emits `:ping\n\n` every 2s through a shared `asyncio.Queue` so live tokens and pings interleave; correct cancellation/cleanup in `finally`
- `admin_routes.py` — new `POST /api/admin/qdrant/reset?collection=<name>&confirm=true` (superadmin-only) wipes + recreates a Qdrant collection and marks affected Mongo docs as not-processed; allowlist of two collection names; `asyncio.to_thread` for the blocking delete/create
- `StatsPage.jsx` — new "Reset Base Index" / "Reset Company Index" buttons on Admin → Stats (next to Force Re-seed)
- `vector_store.py upsert_chunks` — BATCH 64 → 16, `gc.collect()` every 8 batches, explicit `del` of intermediate buffers per iteration
- `ingestion.py ingest_document` — drops `raw_text` inside the worker thread; calls `chunks.clear()` + `gc.collect()` after upsert
- `document_routes._process_document_bg` — explicit `del file_bytes; gc.collect()` after ingest returns
- `RAILWAY_DEPLOY.md` — added troubleshooting rows for both the `operands could not be broadcast` symptom (with pointer to the new admin button) and SSE buffering

### Verified
- 12/12 iter5 tests passed + 13/13 iter4 regression passed (0 critical, 0 minor that need action)
- Local smoke: first SSE byte at 88 ms; `:ping` every 2 s; full session→sources→tokens→done in 22 s
- Ingestion of 105-chunk doc: 27 s (vs 62 s under BATCH=64) — faster *and* lower memory
- Regression: event-loop responsiveness from v3.5 still holds (login p95 = 326 ms during ingest)
- Regression baselines: `/app/backend/tests/test_ehs_rag_iteration5.py`, `/app/backend/tests/test_ehs_rag_iteration4.py`

## v3.5 — Event-loop responsiveness during ingestion (Feb 2026, P0 fix)

### Problem
Admin uploads of a large document froze the entire FastAPI process — concurrent `/api/health` and `/api/auth/login` calls hung indefinitely with no errors. Root cause: synchronous CPU-bound work running on the asyncio event loop in a single-worker uvicorn (workers must stay at 1 because fastembed + qdrant local-file mode aren't fork-safe).

### Fixes
- `app/auth.py` — new `hash_password_async` / `verify_password_async` wrappers (bcrypt offloaded to threadpool); applied in `auth_routes.py` for register + login
- `app/routes/document_routes.py` — background processor now reads the uploaded file via `asyncio.to_thread` (a 300MB sync `f.read()` no longer blocks the loop)
- `app/vector_store.py` — `upsert_chunks` batches by 64 with `asyncio.sleep(0)` between batches (yields to event loop, bounds memory for huge docs)
- `app/embeddings.py` — fastembed models constructed with `threads=settings.embed_onnx_threads` (default = half-cores, range 2-8) so embedding can't saturate every core, leaving CPU headroom for login/chat
- `app/config.py` — new `EMBED_ONNX_THREADS` env var
- `server.py` — `/api/health` no longer touches qdrant (qdrant's local-file mode serializes ops, was causing health spikes during upsert); split to new `/api/health/qdrant` route

### Verified
Backend testing agent (iteration_4) — 13/13 passed, 0 critical, 0 minor. During concurrent ingestion of a 134-chunk doc:
- `/api/health` median 106ms / max 135ms (was hanging)
- `/api/auth/login` median 326ms / max 341ms (was hanging)
- 0 errors over 10 concurrent iterations
Regression test baseline: `/app/backend/tests/test_ehs_rag_iteration4.py`
