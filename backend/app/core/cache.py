"""
Redis cache manager — L1 (in-process dict) + L2 (Redis).
Used by: ConfidenceScorer, Embedder, AgentPerformanceCache.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# L1: simple in-process dict (bounded to 512 entries)
_l1_cache: dict[str, Any] = {}
_L1_MAX = 512


class CacheManager:
    """Two-tier cache: in-process dict + Redis."""

    def __init__(self) -> None:
        self._redis: Any = None
        self._lock = asyncio.Lock()

    async def _get_redis(self) -> Any:
        if self._redis is None:
            async with self._lock:
                if self._redis is None:
                    import redis.asyncio as aioredis

                    from app.config import settings
                    self._redis = await aioredis.from_url(
                        settings.redis_url, decode_responses=True
                    )
        return self._redis

    async def get(self, key: str) -> Any | None:
        # L1 hit
        if key in _l1_cache:
            return _l1_cache[key]
        # L2 hit
        try:
            r = await self._get_redis()
            val = await r.get(key)
            if val is not None:
                parsed = json.loads(val)
                self._l1_set(key, parsed)
                return parsed
        except Exception as e:
            logger.warning(f"cache_get_failed key={key}: {e}")
        return None

    async def set(self, key: str, value: Any, ttl: int = 300) -> None:
        self._l1_set(key, value)
        try:
            r = await self._get_redis()
            await r.setex(key, ttl, json.dumps(value))
        except Exception as e:
            logger.warning(f"cache_set_failed key={key}: {e}")

    async def delete(self, key: str) -> None:
        _l1_cache.pop(key, None)
        try:
            r = await self._get_redis()
            await r.delete(key)
        except Exception as e:
            logger.warning(f"cache_delete_failed key={key}: {e}")

    async def invalidate_prefix(self, prefix: str) -> None:
        """Invalidate all keys starting with prefix."""
        to_remove = [k for k in _l1_cache if k.startswith(prefix)]
        for k in to_remove:
            _l1_cache.pop(k, None)
        try:
            r = await self._get_redis()
            keys = await r.keys(f"{prefix}*")
            if keys:
                await r.delete(*keys)
        except Exception as e:
            logger.warning(f"cache_invalidate_failed prefix={prefix}: {e}")

    @staticmethod
    def _l1_set(key: str, value: Any) -> None:
        if len(_l1_cache) >= _L1_MAX:
            # Evict oldest entry (FIFO)
            try:
                oldest = next(iter(_l1_cache))
                _l1_cache.pop(oldest, None)
            except StopIteration:
                pass
        _l1_cache[key] = value


# Global singleton
cache_manager = CacheManager()
