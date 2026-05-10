"""
Cache abstraction for Jouzu.

Defines the CacheProvider protocol so the rest of the app depends on an
interface, not a concrete storage implementation. The active implementation
is InMemoryCache -- a plain dict that works for single-user local deployment.

To swap storage backends (e.g. Redis for multi-user production), write a new
class that satisfies CacheProvider and point the consuming module at it.
Nothing in the calling code changes -- only the implementation behind the interface.
"""

from typing import Generic, Protocol, TypeVar, runtime_checkable

T = TypeVar("T")


@runtime_checkable
class CacheProvider(Protocol, Generic[T]):
    """Generic cache interface. Keyed by string, stores any value type."""

    def get(self, key: str) -> T | None:
        """Return the cached value for the key, or None if not present."""
        ...

    def set(self, key: str, value: T) -> None:
        """Store a value under the key."""
        ...

    def contains(self, key: str) -> bool:
        """Return True if the key has a cached entry."""
        ...


class InMemoryCache(Generic[T]):
    """
    Dict-backed implementation of CacheProvider.

    Persists for the lifetime of the server process and is cleared on restart.
    Suitable for single-user or low-traffic deployments.

    For multi-user production, replace with a distributed cache (e.g. Redis)
    by implementing CacheProvider and swapping the instance in the consuming module.
    """

    def __init__(self) -> None:
        self._store: dict[str, T] = {}

    def get(self, key: str) -> T | None:
        return self._store.get(key)

    def set(self, key: str, value: T) -> None:
        self._store[key] = value

    def contains(self, key: str) -> bool:
        return key in self._store
