"""
Sentence-Transformer embedder with Redis L2 cache.
Embedding cache TTL: 24h (EMBEDDING_CACHE_TTL_SECONDS).
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


class Embedder:
    def __init__(self) -> None:
        self._model: Any = None
        self._redis: Any = None

    def _load_model(self) -> None:
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(settings.embedding_model)
            logger.info(f"embedding_model_loaded: {settings.embedding_model}")

    async def _get_redis(self) -> Any:
        if self._redis is None:
            import redis.asyncio as aioredis
            self._redis = await aioredis.from_url(settings.redis_url, decode_responses=True)
        return self._redis

    async def embed(self, text: str) -> list[float]:
        """Embed single text with Redis cache."""
        cache_key = f"emb:{hashlib.sha256(text.encode()).hexdigest()}"
        try:
            r = await self._get_redis()
            cached = await r.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

        self._load_model()
        vector: list[float] = self._model.encode(text, normalize_embeddings=True).tolist()

        try:
            r = await self._get_redis()
            await r.setex(cache_key, settings.embedding_cache_ttl_seconds, json.dumps(vector))
        except Exception as e:
            logger.warning(f"embedding_cache_set_failed: {e}")

        return vector

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Batch embed — always bypasses cache for seeding."""
        self._load_model()
        return self._model.encode(texts, batch_size=32, normalize_embeddings=True).tolist()


embedder = Embedder()
