from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Generic, Hashable, TypeVar

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


@dataclass
class CacheEntry(Generic[V]):
    value: V
    expires_at: float | None = None


class LRUCache(Generic[K, V]):
    """Tiny LRU cache with optional TTL.

    Designed for in-process caching of deterministic LLM calls.
    """

    def __init__(self, *, max_size: int = 128, ttl_seconds: float | None = None) -> None:
        self.max_size = max(1, int(max_size))
        self.ttl_seconds = ttl_seconds
        self._store: OrderedDict[K, CacheEntry[V]] = OrderedDict()

    def get(self, key: K) -> V | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry.expires_at is not None and time.time() >= entry.expires_at:
            self._store.pop(key, None)
            return None
        self._store.move_to_end(key)
        return entry.value

    def set(self, key: K, value: V) -> None:
        expires_at = (time.time() + self.ttl_seconds) if self.ttl_seconds is not None else None
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = CacheEntry(value=value, expires_at=expires_at)
        while len(self._store) > self.max_size:
            self._store.popitem(last=False)
