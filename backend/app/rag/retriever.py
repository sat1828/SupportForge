"""
Hybrid RAG Retriever — 4-layer pipeline.
Invariant 7: fast-path (semantic-only) returns in <= 60ms.
Full pipeline: semantic + BM25 + RRF + cross-encoder reranker.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

FAST_PATH_INTENTS = {
    "order_status",
    "refund_timeline",
    "track_shipment",
    "invoice_download",
    "cod_query",
}


@dataclass
class RetrievedChunk:
    chunk_id: str
    source: str
    text: str
    score: float
    doc_type: str
    category: str | None
    boost_score: float = 1.0

    @property
    def boosted_score(self) -> float:
        return self.score * self.boost_score


class HybridRetriever:
    """
    Layer 1: Semantic search (pgvector cosine similarity)
    Layer 2: BM25 keyword search
    Layer 3: Reciprocal Rank Fusion merge
    Layer 4: Cross-encoder re-ranking
    + Conversation-aware deduplication
    """

    def __init__(self) -> None:
        self._embedder: Any = None
        self._bm25: Any = None
        self._reranker: Any = None

    def _lazy_init(self) -> None:
        if self._embedder is None:
            from app.rag.embedder import embedder
            self._embedder = embedder
        if self._bm25 is None:
            from app.rag.bm25_index import bm25_index
            self._bm25 = bm25_index
        if self._reranker is None:
            from app.rag.reranker import reranker
            self._reranker = reranker

    def _use_fast_path(self, intent: str | None, confidence: float) -> bool:
        """Invariant 7: fast path for high-confidence simple intents."""
        return bool(intent) and intent in FAST_PATH_INTENTS and confidence >= 0.90

    async def retrieve(
        self,
        query: str,
        intent: str | None = None,
        confidence: float = 0.0,
        metadata_filter: dict[str, Any] | None = None,
        conversation_history: list[str] | None = None,
        top_k: int = 3,
    ) -> list[RetrievedChunk]:
        self._lazy_init()
        t0 = time.monotonic()

        if self._use_fast_path(intent, confidence):
            results = await self._semantic_search(query, top_k=1, filter_=metadata_filter)
            latency_ms = int((time.monotonic() - t0) * 1000)
            logger.debug(f"rag_fast_path latency={latency_ms}ms")
            from app.observability.prometheus import rag_retrieval_latency
            rag_retrieval_latency.labels(path="fast").observe(latency_ms)
            if latency_ms > 60:
                logger.warning(f"fast_path_latency_exceeded: {latency_ms}ms")
            return results[:top_k]

        # Full pipeline
        semantic = await self._semantic_search(query, top_k=20, filter_=metadata_filter)
        keyword = self._bm25.search(query, top_k=20, filter_=metadata_filter)
        fused = self._reciprocal_rank_fusion(semantic, keyword)
        reranked = await self._reranker.rerank(query, fused[:10])
        boosted = self._apply_boost(reranked)
        filtered = self._exclude_cited(boosted, conversation_history or [])

        latency_ms = int((time.monotonic() - t0) * 1000)
        from app.observability.prometheus import rag_retrieval_latency
        rag_retrieval_latency.labels(path="full").observe(latency_ms)
        logger.debug(f"rag_full_pipeline latency={latency_ms}ms results={len(filtered)}")
        return filtered[:top_k]

    async def _semantic_search(
        self, query: str, top_k: int, filter_: dict | None
    ) -> list[RetrievedChunk]:
        try:
            from sqlalchemy import select, text
            from app.database import AsyncSessionLocal
            from app.models.knowledge_base import KnowledgeBaseChunk

            query_embedding = await self._embedder.embed(query)
            embedding_str = f"[{','.join(str(x) for x in query_embedding)}]"

            async with AsyncSessionLocal() as db:
                stmt = text("""
                    SELECT id, source_file, text, doc_type, category, boost_score,
                           1 - (embedding <=> :embedding::vector) AS score
                    FROM knowledge_base_chunks
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding <=> :embedding::vector
                    LIMIT :limit
                """)
                result = await db.execute(
                    stmt, {"embedding": embedding_str, "limit": top_k}
                )
                rows = result.fetchall()
                chunks = [
                    RetrievedChunk(
                        chunk_id=str(r.id),
                        source=r.source_file,
                        text=r.text,
                        score=float(r.score),
                        doc_type=r.doc_type,
                        category=r.category,
                        boost_score=float(r.boost_score),
                    )
                    for r in rows
                ]
                # Apply doc_type filter if provided
                if filter_ and filter_.get("doc_type"):
                    chunks = [c for c in chunks if c.doc_type == filter_["doc_type"]]
                return chunks
        except Exception as e:
            logger.error(f"semantic_search_failed: {e}")
            return []

    def _reciprocal_rank_fusion(
        self,
        semantic: list[RetrievedChunk],
        keyword: list[RetrievedChunk],
        k: int = 60,
    ) -> list[RetrievedChunk]:
        scores: dict[str, float] = {}
        index: dict[str, RetrievedChunk] = {}

        for rank, chunk in enumerate(semantic):
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0) + 1 / (k + rank + 1)
            index[chunk.chunk_id] = chunk

        for rank, chunk in enumerate(keyword):
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0) + 1 / (k + rank + 1)
            if chunk.chunk_id not in index:
                index[chunk.chunk_id] = chunk

        sorted_ids = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)
        result = []
        for cid in sorted_ids:
            chunk = index[cid]
            chunk.score = scores[cid]
            result.append(chunk)
        return result

    def _apply_boost(self, results: list[RetrievedChunk]) -> list[RetrievedChunk]:
        for r in results:
            if r.boost_score != 1.0:
                r.score = r.boosted_score
        return sorted(results, key=lambda r: r.score, reverse=True)

    def _exclude_cited(
        self, results: list[RetrievedChunk], cited_sources: list[str]
    ) -> list[RetrievedChunk]:
        cited_set = set(cited_sources)
        return [r for r in results if r.source not in cited_set]


hybrid_retriever = HybridRetriever()
