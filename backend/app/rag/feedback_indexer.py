"""
Feedback indexer — learning loop (Defect 4 fix).
When admin corrects AI decision → indexes correction into KB with boost_score=1.5.
Invariant 16: correction → KB chunk created
Invariant 17: boost_score=1.5 applied in ranking
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

CORRECTION_BOOST_SCORE = 1.5


class FeedbackIndexer:
    async def index_correction(
        self,
        ticket_id: str,
        original_intent: str,
        original_response: str,
        corrected_response: str,
        correction_type: str,
        category: str | None,
        admin_id: str,
        db: object,
    ) -> str:
        """
        Convert admin correction → KB chunk with 1.5× boost.
        Returns created chunk_id.
        Invariants 16 + 17.
        """
        chunk_text = (
            f"[HUMAN-VERIFIED CORRECTION]\n"
            f"Intent: {original_intent}\n"
            f"Original response: {original_response[:300]}\n"
            f"Correct resolution: {corrected_response}\n"
            f"Verified by: Admin | Date: {datetime.now(UTC).date()}"
        )
        chunk_hash = hashlib.sha256(chunk_text.encode()).hexdigest()

        from app.models.knowledge_base import KnowledgeBaseChunk
        from app.rag.embedder import embedder

        embedding = await embedder.embed(chunk_text)

        chunk = KnowledgeBaseChunk(
            id=uuid.uuid4(),
            source_file="admin_feedback",
            doc_type="human_correction",
            category=category,
            language="en",
            chunk_index=0,
            chunk_hash=chunk_hash,
            text=chunk_text,
            embedding=embedding,
            boost_score=CORRECTION_BOOST_SCORE,  # Invariant 17
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        # Upsert (conflict on chunk_hash)
        from sqlalchemy import text as sa_text

        db.add(chunk)  # type: ignore[union-attr]
        try:
            await db.flush()  # type: ignore[union-attr]
        except Exception:
            await db.rollback()  # type: ignore[union-attr]
            # Chunk already exists — update boost score
            await db.execute(  # type: ignore[union-attr]
                sa_text(
                    "UPDATE knowledge_base_chunks SET boost_score=:boost WHERE chunk_hash=:hash"
                ),
                {"boost": CORRECTION_BOOST_SCORE, "hash": chunk_hash},
            )

        # Rebuild BM25 index to include new correction
        try:
            from app.rag.bm25_index import bm25_index
            await bm25_index.rebuild_from_db()
        except Exception as e:
            logger.warning(f"bm25_rebuild_after_correction_failed: {e}")

        logger.info(
            "correction_indexed",
            extra={
                "ticket_id": ticket_id,
                "intent": original_intent,
                "chunk_hash": chunk_hash,
                "boost_score": CORRECTION_BOOST_SCORE,
            },
        )

        return str(chunk.id)


feedback_indexer = FeedbackIndexer()
