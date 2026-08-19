"""A small in-memory cache for completed verifications.

This exists for one reason: the free API tiers are tight (Gemini gave out at ~20
requests/day, Firecrawl at ~10/minute), and a verification costs 2–3 Gemini calls
plus up to 9 Firecrawl calls. Re-running the same claim — which is exactly what
happens when a demo is rehearsed, repeated for a second judge, or retried after a
stumble — would spend that budget again for an answer already known.

Deliberately not a database: entries live in the process, expire on a TTL, and are
gone on restart. That is the correct trade for a hackathon, and it keeps the promise
that no user data is persisted anywhere.
"""

import logging
import time
from collections import OrderedDict
from typing import Generic, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class TTLCache(Generic[T]):
    """Bounded, time-limited cache with least-recently-used eviction."""

    def __init__(self, ttl_seconds: float, max_entries: int) -> None:
        self._ttl = ttl_seconds
        self._max = max(1, max_entries)
        self._entries: OrderedDict[str, tuple[float, T]] = OrderedDict()

    def get(self, key: str) -> T | None:
        entry = self._entries.get(key)
        if entry is None:
            return None

        stored_at, value = entry
        # Monotonic clock: a wall-clock adjustment must not resurrect or expire entries.
        if time.monotonic() - stored_at > self._ttl:
            del self._entries[key]
            logger.debug("cache entry expired: %s", key)
            return None

        self._entries.move_to_end(key)
        return value

    def set(self, key: str, value: T) -> None:
        self._entries[key] = (time.monotonic(), value)
        self._entries.move_to_end(key)
        while len(self._entries) > self._max:
            evicted, _ = self._entries.popitem(last=False)
            logger.debug("cache evicted: %s", evicted)

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)
