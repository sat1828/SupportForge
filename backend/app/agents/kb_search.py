"""
KB Search Agent Node — calls HybridRetriever and updates AgentState.
Tracks kb_search_count for Invariant 3.
"""
from __future__ import annotations

import logging

from app.agents.state import AgentState

logger = logging.getLogger(__name__)


async def kb_search_node(state: AgentState) -> AgentState:
    """Retrieve relevant KB chunks and inject into state."""
    from app.rag.retriever import hybrid_retriever

    state["budget"]["kb_search_count"] += 1

    intent = state.get("intent")
    conf = (state.get("calibrated_confidence") or {}).get("llm_confidence", 0.0)

    # Collect already-cited sources to avoid duplication
    cited = [r.get("source", "") for r in state.get("kb_results", [])]

    try:
        chunks = await hybrid_retriever.retrieve(
            query=state["messages"][-1].content if state["messages"] else "",
            intent=intent,
            confidence=conf,
            metadata_filter={"language": state.get("language", "en")},
            conversation_history=cited,
            top_k=3,
        )

        new_results = [
            {
                "chunk_id": c.chunk_id,
                "source": c.source,
                "text": c.text,
                "score": c.score,
                "doc_type": c.doc_type,
            }
            for c in chunks
        ]

        state["kb_results"] = state.get("kb_results", []) + new_results

        # Update RAG relevance score in confidence
        if chunks and state.get("calibrated_confidence"):
            top_score = chunks[0].score if chunks else 0.0
            state["calibrated_confidence"]["rag_relevance_score"] = top_score  # type: ignore[index]

            from app.core.confidence import confidence_scorer, ConfidenceInputs
            inputs = ConfidenceInputs(
                llm_confidence=state["calibrated_confidence"].get("llm_confidence", 0.5),  # type: ignore[union-attr]
                rag_relevance_score=top_score,
                tool_execution_success=state["calibrated_confidence"].get("tool_execution_success", 1.0),  # type: ignore[union-attr]
                historical_accuracy=state["calibrated_confidence"].get("historical_accuracy", 0.5),  # type: ignore[union-attr]
            )
            result = confidence_scorer.compute(inputs)
            state["calibrated_confidence"]["final_score"] = result.score  # type: ignore[index]
            state["calibrated_confidence"]["routing_decision"] = result.routing_decision  # type: ignore[index]

        state["next_node"] = "resolver"
        logger.info(
            "kb_search_complete",
            extra={
                "intent": intent,
                "chunks_found": len(chunks),
                "kb_call_count": state["budget"]["kb_search_count"],
            },
        )
    except Exception as e:
        logger.error(f"kb_search_failed: {e}")
        state["next_node"] = "resolver"

    return state
