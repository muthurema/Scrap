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
- **Acknowledgement workflow** (user clicks "I understand" on critical procedures → audit trail)
- **Compliance digest email** (Monday 8am with new pending reviews + top unanswered queries)
- **Refresh-token rotation** for production JWT
- **Mobile-responsive polish** for field tablet use

## Next Tasks
1. Multi-language support (largest competitive moat for international rollouts)
2. Incident-report integration (when Turnstile API spec lands)
3. Photo/image input (low effort, very high field impact — Claude vision already available)
4. Acknowledgement workflow (legal/compliance requirement)
