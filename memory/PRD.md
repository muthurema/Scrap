# CIDSA RAG — GIS Knowledge Assistant (PRD)

## Original problem statement
Repurpose an existing production EHS (Environment, Health & Safety) RAG chatbot into **CIDSA RAG**, a **GIS (Geographic Information Systems)** knowledge assistant. Users upload their own GIS reference books; the assistant answers grounded questions and **cites every answer by book title + author**.

## Product decisions (user-approved, June 2026)
- **Brand**: "CIDSA RAG", tagline "GIS knowledge assistant". Emerald globe glyph logo (lucide/phosphor `GlobeHemisphereWest`), no external logo asset.
- **Single GLOBAL knowledge base** — all uploaded documents are shared globally (no company/regional tiers). Any logged-in user can query.
- **Citations show BOOK TITLE + AUTHOR** (documents carry an `author` field; surfaced in answer text and source cards).
- **Removed EHS features**: high-risk emergency detection + escalation banner, jurisdiction regulatory frameworks (OSHA/HSE/Factories Act) + jurisdiction retrieval boost, onboarding page (jurisdiction/industry), tenant-name redaction, auto web-source seeding.
- **Kept**: Compliance Acknowledgement workflow (generic "I understand") + `/admin/acknowledgements` + CSV export; confidence badge, citations, copy, thumbs up/down feedback, session history; multi-tenant user/RBAC for team management; web-source admin feature (user adds GIS URLs).

## Architecture
```
/app/backend/app
  routes/  (admin_routes, auth_routes, chat_routes, document_routes, web_source, acknowledgement_routes, feedback/analytics)
  rag_engine.py  → GIS_SYSTEM_PROMPT_BASE, HyDE, hybrid retrieve, cross-encoder rerank, Claude stream; cites book+author
  vector_store.py (Qdrant: collections ehs_base_knowledge, ehs_company_docs), ingestion.py, embeddings.py
  schemas.py (DocumentOut.author, SourceReference.author), config.py (DocumentType incl. BOOK), seed.py (empty corpus)
  wipe_corpus.py  → one-time data wipe helper (Mongo + files; Qdrant via /api/admin/qdrant/reset)
/app/frontend/src
  pages/ (ChatPage, LoginPage, Forgot/ResetPassword, admin/*)
  components/chat/ (ChatSidebar, EmptyState, MessageRow, SourceCard, constants.js)
  components/Logo.jsx (globe glyph)
```

## Tech stack
- Frontend: React, Tailwind, Shadcn UI, phosphor icons.
- Backend: FastAPI (Python 3.11), Motor/MongoDB, Qdrant (external Railway), LiteLLM via Emergent Universal Key (or direct Anthropic). Model: Claude Sonnet 4.6.

## Key endpoints
- `POST /api/documents/upload` — multipart incl. `title`, `author`, `doc_type` (validated against enum → 400 on invalid, never poisons DB), forced to global base_corpus.
- `GET /api/documents/` — resilient to malformed rows (skips + logs).
- `POST /api/chat/stream` — SSE; sources event = `{sources:[...with author], external_count:0}`.
- `POST /api/acknowledgements/`, `GET /api/acknowledgements/export/csv` (cidsa-*.csv).
- `GET /api/documents/upload-quota`, `POST /api/admin/qdrant/reset`.

## Status (June 2026)
- ✅ Full EHS→CIDSA GIS transformation complete & tested (5/5 backend pytest pass + full UI flow via testing agent).
- ✅ Knowledge base WIPED EMPTY and ready for the user's GIS books.
- ✅ Confidence badge clamped to 0–100%. doc_type=book accepted. Rebrand leaks fixed (Forgot/Reset/Acknowledgements/Companies/WebSources pages, superadmin display name).

## Backlog (user said: only when I say so)
- P3: SDS/PubChem-style live data — N/A for GIS; consider live geodata/EPSG lookup instead.
- P3: Knowledge graph linking related concepts.
- P3: Per-book reading progress / study mode.
- Note: favicon files in /app/frontend/public are still legacy-branded (low priority).

## Test credentials
See `/app/memory/test_credentials.md`. Superadmin: admin@ehsrag.com / Admin@12345.
