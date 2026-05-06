"""Tool: search_kb — calls HybridRetriever."""
from __future__ import annotations

from app.core.resilience import with_tool_retry


@with_tool_retry(max_attempts=2)
async def search_kb(query: str, intent: str = "", confidence: float = 0.5, **kwargs) -> dict:
    from app.rag.retriever import hybrid_retriever

    chunks = await hybrid_retriever.retrieve(
        query=query, intent=intent, confidence=confidence, top_k=3
    )
    return {
        "results": [
            {"source": c.source, "text": c.text[:500], "score": c.score, "doc_type": c.doc_type}
            for c in chunks
        ],
        "count": len(chunks),
    }
