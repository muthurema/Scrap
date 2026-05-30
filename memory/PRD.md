# EHS Intelligent RAG — Product Requirements Document

## Original Problem Statement
User uploaded `ehs-rag.zip` — production-grade backend for an EHS (Environment, Health & Safety) Intelligent RAG chatbot designed for Turnstile360 integration. Adapted to Emergent platform: Qdrant in-process local mode, MongoDB metadata, full React UI, Emergent Universal Key for Claude, Turnstile DMS sync stubbed. **Iteration 2** added streaming, security hardening, and RAG quality improvements per user-provided RAG/security best-practices guidance.

## Architecture (v2.0)

| Layer | Tech |
|---|---|
| Backend | FastAPI on port 8001, all routes under `/api/*` |
| LLM | Claude `claude-sonnet-4-6` via `litellm` → Emergent proxy (streaming + non-streaming) |
| Dense embeddings | `fastembed` ONNX `BAAI/bge-small-en-v1.5` (384-dim) |
| Sparse embeddings | `fastembed` BM25 (`Qdrant/bm25`) |
| Re-ranker | Cross-encoder `Xenova/ms-marco-MiniLM-L-6-v2` |
| Query expansion | **HyDE** — Claude rewrites query into synthetic answer for better retrieval |
| Vector DB | Qdrant local file mode at `/app/backend/qdrant_data`; collections have NAMED vectors (`dense` + `bm25`) |
| Retrieval | Dense + Sparse parallel search → Reciprocal Rank Fusion → Cross-encoder rerank |
| Metadata DB | MongoDB (motor) — users, companies, documents, chat_sessions, chat_messages, web_sources, **audit_logs** |
| Auth | JWT (python-jose) + bcrypt; first user → superadmin |
| Scheduler | APScheduler (hourly tick, per-source due-check by frequency) |
| OCR | Tesseract + pdf2image + pytesseract (fallback for image-only PDFs and JPG/PNG uploads) |
| Frontend | React 19 + Tailwind + Shadcn UI + Phosphor icons + react-markdown + remark-gfm |

## Security Posture (v2.0)
1. **Prompt-injection sanitization** — input cleaning of ChatML/role tags + injection-pattern scan; documents scanned on ingest with findings logged
2. **Jailbreak refusal** — hardened system prompt with exact refusal phrase
3. **Hallucination guardrails** — model instructed to never invent regulation numbers, ISO clauses, OEL/PEL/TLV, or CAS numbers; must cite verbatim or decline
4. **SSRF protection** — `is_safe_url()` blocks private RFC1918, loopback, link-local (incl. AWS 169.254.169.254 metadata), multicast, CGNAT; checks both initial URL and final redirected URL
5. **Audit logging** — every superadmin destructive action (upload/delete/reprocess/web-source CRUD/scrape/acknowledge/session-delete) logged with user_id, email, role, IP, user-agent, resource_type, resource_id, masked details, status
6. **Secret masking** in audit details (`sk-emergent-*`, `sk-ant-*`, JWTs)
7. **PII heuristic flag** on user queries (email/phone/SSN/credit-card patterns logged to msg record)
8. **Chunk text capped at 300 chars** in SourceReference (no verbatim long-passage leak)
9. **Conversation history capped at 8 turns** sent to LLM

## RAG Quality (v2.0)
- **HyDE query rewriting** — Claude generates a synthetic answer for the query, embedded along with original query
- **Hybrid retrieval** — Dense + BM25 sparse vectors searched in parallel
- **Reciprocal Rank Fusion** — merges 4 result lists (2 collections × 2 vector types) with k=60
- **Cross-encoder re-rank** — top-18 candidates re-scored by `ms-marco-MiniLM-L-6-v2`
- **Chunk deduplication** on ingest via SHA-256 of normalized text
- **Doc-type-aware chunking** preserved (8 types × custom chunk_size/overlap/type-boost)
- **Source-priority boost** retained (Company 1.5× / Turnstile 1.3× / Base 1.0×)

## Streaming UX
- **SSE endpoint** `POST /api/chat/stream` emits events in order: `session` → `sources` (sources-first per user preference) → `token` (multiple) → `done`
- Frontend ChatPage uses `fetch` + `ReadableStream` reader; assistant message bubble grows incrementally with blinking cursor; sources panel populates before text streams
- Buffering note: litellm/Emergent proxy may flush tokens in bursts (10-100 chars) rather than one-by-one

## Implementation Timeline

### 2026-05-30 — Iteration 1 (MVP)
- Backend skeleton, dense-only retrieval, non-streaming chat, JWT auth, doc upload, web scraping
- Frontend Login + Chat + Admin (Stats / Documents / Web Sources)
- 7 base-corpus EHS docs seeded
- Tests: 16/16 backend pytest pass; ~95% frontend (2 bugs fixed)

### 2026-05-30 — Iteration 2 (Hardening + RAG Quality)
- **Added:** SSE streaming chat, HyDE, BM25 sparse + RRF, cross-encoder rerank, hallucination guardrails, prompt-injection sanitization, SSRF protection, audit logging + UI widget, APScheduler weekly auto-scrape, OCR fallback (Tesseract), chunk deduplication
- Tests: 14/14 new backend pytest pass (iter2.py) + 16/16 iter1 still pass; ~98% frontend

## Test Status
- iteration_1.json: backend 16/16, frontend ~95% — all bugs fixed
- iteration_2.json: backend 14/14, frontend ~98% — no critical bugs

## Mocked Integrations
- **Turnstile360 DMS sync** — `/api/admin/sync/turnstile/{company_id}` returns mock summary; real HTTP integration deferred until customer provides API spec

## Backlog / Future

### P1
- **Streaming buffering** — investigate enabling true token-by-token via SSE `text-event-stream` flushing (may require uvicorn config changes or a different proxy path)
- **Wire real Turnstile360 API** when spec is shared
- **Eval & monitoring** — log retrieval-answer pairs, admin metrics dashboard (avg score per query, % below threshold, top dead queries, top cited docs), thumbs up/down feedback (Batch D from session 2)
- **Compliance digest email** — weekly Monday 8am email to safety officers with: new pending-review web sources + top 5 unanswered chat queries

### P2
- Replace native title-attribute citation tooltips with Radix Tooltip for animated UX
- Voice input (Whisper STT via Universal Key)
- PDF export of answers with citations
- Per-tenant embedding model selection
- Refresh-token rotation for production JWT
- Multi-tenant company-scoped admin views

## Next Tasks
1. Eval & monitoring dashboard (Batch D)
2. Wire real Turnstile360 API once spec is shared
3. Investigate true token-by-token streaming (currently bursts)
4. Compliance digest email feature
