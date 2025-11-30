"""
In-memory TTL cache for database queries and API results.

Provides simple caching without Redis dependency for MVP.
Can be replaced with Redis for production scaling.
"""

import asyncio
import time
from collections import OrderedDict
from functools import wraps
from typing import Any, Callable, Optional


class TTLCache:
    """
    Time-To-Live cache with LRU eviction.

    Features:
    - TTL-based expiration (items expire after N seconds)
    - LRU eviction when max_size exceeded
    - Thread-safe for async operations
    - Automatic cleanup of expired items
    """

    def __init__(self, max_size: int = 1000, default_ttl: int = 3600):
        """
        Initialize TTL cache.

        Args:
            max_size: Maximum number of cached items
            default_ttl: Default time-to-live in seconds
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache if not expired.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        async with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            value, expires_at = self._cache[key]

            # Check if expired
            if time.time() > expires_at:
                del self._cache[key]
                self._misses += 1
                return None

            # Move to end (LRU)
            self._cache.move_to_end(key)
            self._hits += 1
            return value

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Set value in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (uses default if None)
        """
        async with self._lock:
            expires_at = time.time() + (ttl or self.default_ttl)
            self._cache[key] = (value, expires_at)
            self._cache.move_to_end(key)

            # Evict oldest if over max_size
            while len(self._cache) > self.max_size:
                self._cache.popitem(last=False)

    async def delete(self, key: str) -> bool:
        """
        Delete key from cache.

        Args:
            key: Cache key

        Returns:
            True if key existed, False otherwise
        """
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    async def clear(self) -> None:
        """Clear all cached items."""
        async with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    async def cleanup_expired(self) -> int:
        """
        Remove all expired items.

        Returns:
            Number of items removed
        """
        async with self._lock:
            now = time.time()
            expired_keys = [
                key for key, (_, expires_at) in self._cache.items() if now > expires_at
            ]

            for key in expired_keys:
                del self._cache[key]

            return len(expired_keys)

    @property
    def stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total_requests = self._hits + self._misses
        hit_rate = self._hits / total_requests if total_requests > 0 else 0

        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
        }


# Global cache instances
material_search_cache = TTLCache(max_size=500, default_ttl=3600)  # 1 hour
price_scrape_cache = TTLCache(max_size=1000, default_ttl=86400)  # 24 hours


def cached(
    cache: TTLCache, key_prefix: str = "", ttl: Optional[int] = None
) -> Callable:
    """
    Decorator to cache async function results.

    Usage:
        @cached(material_search_cache, key_prefix="search", ttl=3600)
        async def search_materials(query: str):
            ...

    Args:
        cache: TTLCache instance to use
        key_prefix: Prefix for cache keys
        ttl: Time-to-live in seconds (None = use cache default)

    Returns:
        Decorated function
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Build cache key from function args
            cache_key = f"{key_prefix}:{func.__name__}:{args}:{kwargs}"

            # Try to get from cache
            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                return cached_value

            # Execute function
            result = await func(*args, **kwargs)

            # Store in cache
            await cache.set(cache_key, result, ttl=ttl)

            return result

        return wrapper

    return decorator


async def start_cache_cleanup_task():
    """
    Background task to cleanup expired cache entries.

    Runs every 5 minutes to prevent memory buildup.
    Should be added to FastAPI lifespan events.
    """
    while True:
        await asyncio.sleep(300)  # 5 minutes
        await material_search_cache.cleanup_expired()
        await price_scrape_cache.cleanup_expired()
