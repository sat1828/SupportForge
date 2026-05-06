"""BM25 keyword index for hybrid retrieval Layer 2."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BM25Index:
    _corpus: list[dict[str, Any]] = field(default_factory=list, repr=False)
    _bm25: Any = field(default=None, repr=False)

    def build(self, chunks: list[dict[str, Any]]) -> None:
        from rank_bm25 import BM25Okapi
        self._corpus = chunks
        tokenized = [self._tokenize(c["text"]) for c in chunks]
        self._bm25 = BM25Okapi(tokenized)
        logger.info(f"bm25_index_built: {len(chunks)} chunks")

    def search(
        self, query: str, top_k: int = 20, filter_: dict | None = None
    ) -> list[Any]:
        if self._bm25 is None or not self._corpus:
            return []

        from app.rag.retriever import RetrievedChunk
        tokens = self._tokenize(query)
        scores = self._bm25.get_scores(tokens)

        ranked = sorted(
            [(score, i) for i, score in enumerate(scores)],
            reverse=True,
        )

        results = []
        for score, idx in ranked[:top_k * 2]:
            if score <= 0:
                continue
            chunk = self._corpus[idx]
            if filter_ and filter_.get("doc_type") and chunk.get("doc_type") != filter_["doc_type"]:
                continue
            results.append(
                RetrievedChunk(
                    chunk_id=chunk.get("id", str(idx)),
                    source=chunk.get("source_file", ""),
                    text=chunk.get("text", ""),
                    score=float(score),
                    doc_type=chunk.get("doc_type", ""),
                    category=chunk.get("category"),
                    boost_score=float(chunk.get("boost_score", 1.0)),
                )
            )
            if len(results) >= top_k:
                break

        return results

    async def rebuild_from_db(self) -> None:
        """Load all chunks from DB and rebuild index. Called at startup + after indexing."""
        try:
            from sqlalchemy import select

            from app.database import AsyncSessionLocal
            from app.models.knowledge_base import KnowledgeBaseChunk

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(KnowledgeBaseChunk.id, KnowledgeBaseChunk.text,
                           KnowledgeBaseChunk.source_file, KnowledgeBaseChunk.doc_type,
                           KnowledgeBaseChunk.category, KnowledgeBaseChunk.boost_score)
                )
                rows = result.fetchall()

            chunks = [
                {"id": str(r.id), "text": r.text, "source_file": r.source_file,
                 "doc_type": r.doc_type, "category": r.category, "boost_score": float(r.boost_score)}
                for r in rows
            ]
            self.build(chunks)
        except Exception as e:
            logger.error(f"bm25_rebuild_failed: {e}")

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        text = text.lower()
        tokens = re.findall(r"\b\w+\b", text)
        stopwords = {"the", "a", "an", "is", "in", "on", "at", "to", "for",
                     "of", "and", "or", "with", "by", "from", "my", "your"}
        return [t for t in tokens if t not in stopwords and len(t) > 2]


bm25_index = BM25Index()
