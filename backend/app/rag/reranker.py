"""Cross-encoder re-ranker — RAG Layer 4."""
from __future__ import annotations

import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    def __init__(self) -> None:
        self._model: Any = None

    def _load(self) -> None:
        if self._model is None:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(settings.reranker_model)
            logger.info(f"reranker_loaded: {settings.reranker_model}")

    async def rerank(self, query: str, chunks: list[Any]) -> list[Any]:
        if not chunks:
            return []
        try:
            self._load()
            pairs = [(query, c.text) for c in chunks]
            scores = self._model.predict(pairs)
            for chunk, score in zip(chunks, scores, strict=False):
                chunk.score = float(score)
            return sorted(chunks, key=lambda c: c.score, reverse=True)
        except Exception as e:
            logger.warning(f"reranker_failed, returning original order: {e}")
            return chunks


reranker = CrossEncoderReranker()
