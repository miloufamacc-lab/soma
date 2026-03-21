"""
In-memory TTL cache service for the Musk Ecosystem Intelligence app.
Provides thread-safe caching with automatic expiration.
"""

import logging
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class CacheService:
    """
    Thread-safe in-memory cache with TTL (Time-To-Live) support.

    Key pattern: "category:entity:field" (e.g., "stock:TSLA:price")
    """

    def __init__(self):
        """Initialize the cache service."""
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "total_items": 0,
        }

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a value from the cache.

        Checks expiration time and removes expired entries.

        Args:
            key: Cache key in format "category:entity:field"

        Returns:
            Cached value if found and not expired, None otherwise
        """
        with self._lock:
            if key not in self._cache:
                self._stats["misses"] += 1
                return None

            entry = self._cache[key]

            # Check if expired
            if entry["expires_at"] is not None and time.time() > entry["expires_at"]:
                del self._cache[key]
                self._stats["misses"] += 1
                logger.debug(f"Cache key expired: {key}")
                return None

            self._stats["hits"] += 1
            return entry["value"]

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """
        Store a value in the cache with optional TTL.

        Args:
            key: Cache key in format "category:entity:field"
            value: Value to cache (can be any Python object)
            ttl_seconds: Time-to-live in seconds. If None, cache indefinitely.
        """
        with self._lock:
            expires_at = None
            if ttl_seconds is not None:
                expires_at = time.time() + ttl_seconds

            self._cache[key] = {
                "value": value,
                "expires_at": expires_at,
                "set_at": time.time(),
            }

            self._stats["sets"] += 1
            self._stats["total_items"] = len(self._cache)
            logger.debug(f"Cache set: {key} with TTL {ttl_seconds}s")

    def delete(self, key: str) -> bool:
        """
        Delete a key from the cache.

        Args:
            key: Cache key to delete

        Returns:
            True if key existed and was deleted, False otherwise
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._stats["deletes"] += 1
                self._stats["total_items"] = len(self._cache)
                logger.debug(f"Cache deleted: {key}")
                return True
            return False

    def clear_expired(self) -> int:
        """
        Remove all expired entries from the cache.

        Returns:
            Number of entries removed
        """
        with self._lock:
            current_time = time.time()
            expired_keys = [
                key for key, entry in self._cache.items()
                if entry["expires_at"] is not None and current_time > entry["expires_at"]
            ]

            for key in expired_keys:
                del self._cache[key]

            self._stats["total_items"] = len(self._cache)

            if expired_keys:
                logger.info(f"Cleared {len(expired_keys)} expired cache entries")

            return len(expired_keys)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with hits, misses, sets, deletes, and total items
        """
        with self._lock:
            total_requests = self._stats["hits"] + self._stats["misses"]
            hit_rate = (
                self._stats["hits"] / total_requests
                if total_requests > 0
                else 0
            )

            return {
                **self._stats,
                "hit_rate": round(hit_rate, 3),
                "total_requests": total_requests,
            }

    def clear_all(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._stats["total_items"] = 0
            logger.info(f"Cleared all {count} cache entries")

    def get_all_keys(self) -> list:
        """Get all current cache keys."""
        with self._lock:
            return list(self._cache.keys())
