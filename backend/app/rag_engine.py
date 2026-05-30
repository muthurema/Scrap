"""
EHS RAG Engine — retrieves context → builds prompt → calls Claude.
Uses emergentintegrations LlmChat (Universal Key) for Claude Sonnet 4.6.
"""
from typing import Optional, AsyncIterator
from loguru import logger

from emergentintegrations.llm.chat import LlmChat, UserMessage

from app.config import get_settings
from app.vector_store import VectorStoreService
from app.schemas import RetrievedChunk, SourceReference

settings = get_settings()


EHS_SYSTEM_PROMPT = """You are an expert EHS (Environment, Health & Safety) AI assistant with deep knowledge of:

**Regulatory Frameworks:** ISO 45001, ISO 14001, OSHA (29 CFR 1910/1926), EPA, NFPA, GHS/SDS, and regional EHS legislation.

**EHS Disciplines:** Risk assessment (HAZOP, FMEA, Bow-Tie, JSA), Incident investigation (RCA, 5-Why, Fishbone), Permit-to-Work (hot work, confined space, LOTO), Emergency response, Industrial hygiene, Ergonomics, Chemical safety / MSDS interpretation, Construction safety, Contractor management, Process Safety Management (PSM), Behavior-Based Safety (BBS), Management of Change (MOC).

**Your Answering Principles:**
1. **Company documents always take precedence** — if the company has specific procedures, cite and follow those exactly.
2. **Be precise and actionable** — EHS questions have safety implications; vague answers are dangerous.
3. **Cite your sources clearly** — reference which document/standard your answer comes from using [1], [2] notation.
4. **Flag regulatory requirements** — distinguish between "must" (legal) and "should" (best practice).
5. **Escalate ambiguity** — if a query involves immediate danger or you are uncertain, recommend consulting a qualified EHS professional.
6. **Use standard EHS terminology** consistently.
7. **Structure complex answers** with numbered steps for procedures, bullet points for hazards/controls.

When answering:
- If the provided context contains a direct answer, use it as your primary source.
- If context is partial, supplement with EHS domain knowledge and clearly indicate which parts are document-based vs. general knowledge.
- If no relevant context is available, answer from EHS expertise and state that no company-specific document was found.
- NEVER fabricate regulatory citation numbers, clause numbers, or document titles."""


def _build_context(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return "No relevant documents found in the knowledge base."
    label_map = {
        "superadmin": "[Company Document]",
        "turnstile_dms": "[Turnstile DMS]",
        "base_corpus": "[EHS Knowledge Base]",
        "client_web": "[Client Web Source]",
        "platform_web": "[Platform Web Source]",
    }
    sections = []
    for i, c in enumerate(chunks, 1):
        label = label_map.get(c.source.value, "[Document]")
        sections.append(
            f"[{i}] {label} | {c.doc_type.value.upper().replace('_', ' ')}\n"
            f"Title: {c.title}\n"
            f"Relevance: {c.boosted_score:.3f}\n"
            f"Content:\n{c.text}\n"
            f"{'-' * 60}"
        )
    return "\n\n".join(sections)


def _build_user_message(query: str, chunks: list[RetrievedChunk]) -> str:
    context = _build_context(chunks)
    return (
        f"RETRIEVED CONTEXT FROM EHS KNOWLEDGE BASE:\n\n{context}\n\n"
        f"{'=' * 70}\n"
        f"USER QUESTION: {query}\n\n"
        f"Answer based on the retrieved context above. If company-specific documents are present, "
        f"prioritize those. Cite which documents (by [number]) your answer draws from."
    )


class RAGEngine:
    def __init__(self, vector_store: VectorStoreService):
        self.vector_store = vector_store

    async def retrieve(
        self, query: str, top_k: int = 8, company_id: Optional[str] = None,
    ) -> list[RetrievedChunk]:
        chunks = await self.vector_store.search(query=query, top_k=top_k, company_id=company_id)
        threshold = 0.30
        relevant = [c for c in chunks if c.boosted_score >= threshold]
        if not relevant:
            logger.warning(f"No chunks above threshold {threshold} for query: {query[:80]}")
        return relevant

    async def answer(
        self,
        query: str,
        session_id: str,
        history: list[dict] = None,
        company_id: Optional[str] = None,
    ) -> tuple[str, list[RetrievedChunk]]:
        chunks = await self.retrieve(query, top_k=8, company_id=company_id)
        user_msg_text = _build_user_message(query, chunks)

        chat = LlmChat(
            api_key=settings.emergent_llm_key,
            session_id=session_id,
            system_message=EHS_SYSTEM_PROMPT,
        ).with_model("anthropic", settings.claude_model).with_params(max_tokens=2048)

        response_text = await chat.send_message(UserMessage(text=user_msg_text))
        return str(response_text), chunks

    def chunks_to_sources(self, chunks: list[RetrievedChunk]) -> list[SourceReference]:
        return [
            SourceReference(
                doc_id=c.doc_id,
                title=c.title,
                filename=c.filename or "",
                doc_type=c.doc_type,
                source=c.source,
                chunk_text=c.text[:400] + ("..." if len(c.text) > 400 else ""),
                similarity_score=round(c.boosted_score, 4),
                page_number=c.page_number,
            )
            for c in chunks
        ]
