"""Thread-safe caching system for data sources in Slideflow.

This module provides a singleton cache implementation for storing DataFrames
from various data sources to avoid redundant fetching during presentation
generation. The cache uses MD5 hashing of source parameters to create unique
keys and provides thread-safe operations for concurrent access.

Key Features:
    - Singleton pattern ensuring single cache instance per application
    - Thread-safe operations with reentrant locking
    - MD5-based key generation from source parameters
    - Enable/disable functionality for cache control
    - Copy-on-read/write storage to isolate callers from mutations
    - Cache introspection and debugging capabilities

The cache is designed to be transparent to data connectors and automatically
manages the lifecycle of cached data within build operations.

Example:
    Using the cache in data connectors::

        from slideflow.data.cache import get_data_cache

        def fetch_data(self) -> pd.DataFrame:
            cache = get_data_cache()

            # Try to get cached data
            cached_data = cache.get("csv", file_path=self.file_path)
            if cached_data is not None:
                return cached_data

            # Fetch and cache new data
            data = pd.read_csv(self.file_path)
            cache.set(data, "csv", file_path=self.file_path)
            return data

Classes:
    DataSourceCache: Thread-safe singleton cache for DataFrame storage

Functions:
    get_data_cache: Factory function to get the global cache instance
"""

import hashlib
import json
import os
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

import pandas as pd

from slideflow.constants import Defaults, Environment
from slideflow.utilities.dataframes import copy_dataframe
from slideflow.utilities.error_messages import redacted_error_line
from slideflow.utilities.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class _InflightLoad:
    """Tracks one cache load that other callers may wait on."""

    event: threading.Event
    generation: int


def _resolve_data_cache_max_entries() -> int:
    """Resolve cache entry cap from environment with safe fallback."""
    raw_value = os.getenv(Environment.SLIDEFLOW_DATA_CACHE_MAX_ENTRIES)
    if raw_value is None:
        return Defaults.DATA_SOURCE_CACHE_MAX_ENTRIES
    try:
        parsed = int(raw_value)
    except ValueError:
        return Defaults.DATA_SOURCE_CACHE_MAX_ENTRIES
    return parsed if parsed > 0 else Defaults.DATA_SOURCE_CACHE_MAX_ENTRIES


class DataSourceCache:
    """Thread-safe singleton cache for DataFrame storage in Slideflow.

    This class implements a singleton pattern to ensure only one cache instance
    exists per application. It provides thread-safe operations for storing and
    retrieving DataFrames using MD5-based keys generated from source parameters.

    The cache is designed to be transparent to data connectors and automatically
    stores DataFrame copies and returns fresh copies to callers so replacement
    formatting, chart transforms, and other consumers cannot mutate cached data
    shared by the rest of the build.

    Thread Safety:
        All operations are protected by a reentrant lock (RLock) to ensure
        thread-safe access in concurrent environments.

    Key Generation:
        Cache keys are generated using MD5 hashing of source type and parameters,
        ensuring consistent and unique identification of data sources.

    Example:
        The cache is typically accessed through the factory function:

        >>> cache = get_data_cache()
        >>> data = cache.get("csv", file_path="/path/to/file.csv")
        >>> if data is None:
        ...     data = pd.read_csv("/path/to/file.csv")
        ...     cache.set(data, "csv", file_path="/path/to/file.csv")

    Attributes:
        _instance: Class-level singleton instance storage
        _cache: Thread-safe dictionary storing isolated DataFrame copies
        _enabled: Boolean flag controlling cache operations
        _lock: Reentrant lock for thread-safe operations
    """

    _instance: Optional["DataSourceCache"] = None
    _instance_lock: threading.Lock = threading.Lock()
    _cache: "OrderedDict[str, pd.DataFrame]"
    _inflight: Dict[str, _InflightLoad]
    _enabled: bool
    _generation: int
    _max_entries: int
    _lock: threading.RLock

    def __new__(cls) -> "DataSourceCache":
        """Create or return the singleton cache instance.

        Implements the singleton pattern by creating a new instance only if
        one doesn't already exist. Initializes the cache dictionary, enabled
        flag, and thread lock on first creation.

        Returns:
            The singleton DataSourceCache instance.
        """
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._cache = OrderedDict()
                    cls._instance._inflight = {}
                    cls._instance._enabled = True
                    cls._instance._generation = 0
                    cls._instance._max_entries = _resolve_data_cache_max_entries()
                    cls._instance._lock = threading.RLock()
        return cls._instance

    @staticmethod
    def _copy_frame(data: pd.DataFrame) -> pd.DataFrame:
        """Return an isolated DataFrame copy for cache storage or consumers."""
        return copy_dataframe(data)

    @staticmethod
    def _new_inflight_event() -> threading.Event:
        """Create an event for coordinating one in-flight cache load."""
        return threading.Event()

    @staticmethod
    def _stable_json(value: Any) -> str:
        """Render a deterministic JSON string for normalized key fragments."""
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        )

    @staticmethod
    def _normalize_for_key(value: Any) -> Any:
        """Normalize nested structures into a deterministic JSON-serializable form."""
        if value is None or isinstance(value, (str, int, float, bool)):
            return value

        if isinstance(value, dict):
            normalized_items = [
                [
                    DataSourceCache._normalize_for_key(key),
                    DataSourceCache._normalize_for_key(inner),
                ]
                for key, inner in value.items()
            ]
            normalized_items.sort(
                key=lambda item: DataSourceCache._stable_json(item[0])
            )
            return {"__dict__": normalized_items}

        if isinstance(value, list):
            return {
                "__list__": [
                    DataSourceCache._normalize_for_key(inner) for inner in value
                ]
            }

        if isinstance(value, tuple):
            return {
                "__tuple__": [
                    DataSourceCache._normalize_for_key(inner) for inner in value
                ]
            }

        if isinstance(value, (set, frozenset)):
            normalized_items = [
                DataSourceCache._normalize_for_key(inner) for inner in value
            ]
            normalized_items = sorted(
                normalized_items, key=DataSourceCache._stable_json
            )
            set_tag = "__frozenset__" if isinstance(value, frozenset) else "__set__"
            return {set_tag: normalized_items}

        if isinstance(value, bytes):
            return {"__bytes__": value.hex()}

        # pathlib.Path and similar os.PathLike values.
        if hasattr(value, "__fspath__"):
            return os.fspath(value)

        if hasattr(value, "model_dump") and callable(value.model_dump):
            try:
                return DataSourceCache._normalize_for_key(value.model_dump())
            except Exception as error:
                logger.debug(
                    "Data cache key normalization: model_dump failed (%s); "
                    "falling back to repr().",
                    redacted_error_line(error),
                    exc_info=True,
                )

        return repr(value)

    def _enforce_size_limit_locked(self) -> None:
        """Enforce max cache entries using LRU eviction. Caller must hold lock."""
        while len(self._cache) > self._max_entries:
            self._cache.popitem(last=False)

    def _generate_key(self, source_type: str, **kwargs) -> str:
        """Generate MD5 hash key from source type and parameters.

        Creates a unique cache key by combining the source type with all
        provided parameters. Parameters are sorted to ensure consistent
        key generation regardless of parameter order.

        Args:
            source_type: Type of data source (e.g., "csv", "databricks", "api").
            **kwargs: Additional parameters that uniquely identify the data source.
                Common parameters include file_path, query, table_name, etc.

        Returns:
            MD5 hash string representing the unique cache key.

        Example:
            >>> cache._generate_key("csv", file_path="/data/sales.csv")
            'a1b2c3d4e5f6...'

            >>> cache._generate_key("databricks", query="SELECT * FROM users")
            'f6e5d4c3b2a1...'
        """
        payload = {
            "source_type": source_type,
            "kwargs": DataSourceCache._normalize_for_key(kwargs),
        }
        canonical_payload = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        return hashlib.md5(canonical_payload.encode("utf-8")).hexdigest()

    def get(self, source_type: str, **kwargs) -> Optional[pd.DataFrame]:
        """Retrieve a DataFrame from the cache if it exists.

        Attempts to find a cached DataFrame matching the provided source type
        and parameters. Returns None if the cache is disabled or if no matching
        entry is found.

        Args:
            source_type: Type of data source to look for in cache.
            **kwargs: Parameters that uniquely identify the data source.
                Must match the parameters used when the data was cached.

        Returns:
            The cached DataFrame if found and cache is enabled, None otherwise.

        Example:
            >>> data = cache.get("csv", file_path="/data/sales.csv")
            >>> if data is not None:
            ...     print(f"Found cached data with {len(data)} rows")
            ... else:
            ...     print("Data not in cache, need to fetch")
        """
        key = self._generate_key(source_type, **kwargs)
        with self._lock:
            if not self._enabled:
                return None
            # guard the lookup
            df = self._cache.get(key)
            if df is not None:
                # LRU: move most recently used key to the end.
                self._cache.move_to_end(key)
            else:
                return None
        return self._copy_frame(df)

    def set(self, data: pd.DataFrame, source_type: str, **kwargs) -> None:
        """Store a DataFrame in the cache.

        Caches a copy of the provided DataFrame using a key generated from the
        source type and parameters. Later reads return fresh copies so callers
        can safely mutate their returned frames without corrupting the cache.

        Args:
            data: The DataFrame to cache.
            source_type: Type of data source being cached.
            **kwargs: Parameters that uniquely identify the data source.
                These should be the same parameters used for retrieval.

        Example:
            >>> data = pd.read_csv("/data/sales.csv")
            >>> cache.set(data, "csv", file_path="/data/sales.csv")
            >>>
            >>> # Later retrieval will use the same parameters
            >>> cached_data = cache.get("csv", file_path="/data/sales.csv")
        """
        key = self._generate_key(source_type, **kwargs)
        cache_entry = self._copy_frame(data)
        with self._lock:
            if not self._enabled:
                return
            self._cache[key] = cache_entry
            self._cache.move_to_end(key)
            self._enforce_size_limit_locked()

    def get_or_load(
        self, source_type: str, loader: Callable[[], pd.DataFrame], **kwargs
    ) -> pd.DataFrame:
        """Get cached data or load it exactly once per key under concurrency.

        Prevents cache stampedes by ensuring only one concurrent caller executes
        `loader` for a given cache key while others wait for that result.

        Args:
            source_type: Type of data source (e.g., "csv", "databricks").
            loader: Zero-arg callable that fetches the DataFrame on cache miss.
            **kwargs: Parameters that uniquely identify the data source.

        Returns:
            Cached or freshly loaded DataFrame for the requested key.
        """
        key = self._generate_key(source_type, **kwargs)

        while True:
            cached = None
            pending = None
            is_owner = False
            load_uncached = False
            with self._lock:
                if not self._enabled:
                    load_uncached = True
                else:
                    cached = self._cache.get(key)
                    if cached is not None:
                        self._cache.move_to_end(key)
                    else:
                        pending = self._inflight.get(key)
                        if pending is None:
                            pending = _InflightLoad(
                                event=self._new_inflight_event(),
                                generation=self._generation,
                            )
                            self._inflight[key] = pending
                            is_owner = True

            if load_uncached:
                return loader()

            if cached is not None:
                return self._copy_frame(cached)

            if is_owner:
                assert pending is not None
                try:
                    data = loader()
                except BaseException:
                    with self._lock:
                        current = self._inflight.get(key)
                        if current is pending:
                            self._inflight.pop(key, None)
                        pending.event.set()
                    raise

                cache_entry = self._copy_frame(data)
                with self._lock:
                    current = self._inflight.get(key)
                    if (
                        self._enabled
                        and self._generation == pending.generation
                        and current is pending
                    ):
                        self._cache[key] = cache_entry
                        self._cache.move_to_end(key)
                        self._enforce_size_limit_locked()
                        self._inflight.pop(key, None)
                    elif current is pending:
                        self._inflight.pop(key, None)
                    pending.event.set()
                return data

            if pending is None:
                continue
            pending.event.wait()

    def clear(self) -> None:
        """Remove all cached DataFrames.

        Clears all entries from the cache while maintaining the enabled state.
        This is useful for freeing memory between build operations or when
        you want to force fresh data retrieval.

        Example:
            >>> cache.clear()
            >>> print(f"Cache size after clear: {cache.size}")  # 0
        """
        with self._lock:
            self._generation += 1
            self._cache.clear()
            self._release_inflight_locked()

    def disable(self) -> None:
        """Disable the cache and clear all cached data.

        Disables cache operations and removes all cached DataFrames. Once disabled,
        get() operations will return None and set() operations will be ignored
        until the cache is re-enabled.

        Example:
            >>> cache.disable()
            >>> data = cache.get("csv", file_path="/data/sales.csv")  # Returns None
            >>> cache.set(df, "csv", file_path="/data/sales.csv")  # Ignored
        """
        with self._lock:
            self._enabled = False
            self._generation += 1
            self._cache.clear()
            self._release_inflight_locked()

    def enable(self) -> None:
        """Re-enable cache operations.

        Enables cache operations after being disabled. The cache starts empty
        after being re-enabled since disable() clears all cached data.

        Example:
            >>> cache.enable()
            >>> cache.set(df, "csv", file_path="/data/sales.csv")  # Now works
            >>> data = cache.get("csv", file_path="/data/sales.csv")  # Returns df
        """
        with self._lock:
            self._enabled = True
            self._max_entries = _resolve_data_cache_max_entries()

    def _release_inflight_locked(self) -> None:
        """Wake all waiters after cache state invalidation. Caller holds lock."""
        inflight = list(self._inflight.values())
        self._inflight.clear()
        for pending in inflight:
            pending.event.set()

    @property
    def is_enabled(self) -> bool:
        """Check if the cache is currently enabled.

        Returns:
            True if cache operations are enabled, False otherwise.

        Example:
            >>> if cache.is_enabled:
            ...     print("Cache is active")
            ... else:
            ...     print("Cache is disabled")
        """
        with self._lock:
            return self._enabled

    @property
    def size(self) -> int:
        """Get the number of cached DataFrames.

        Returns:
            Number of DataFrames currently stored in the cache.

        Example:
            >>> print(f"Cache contains {cache.size} DataFrames")
        """
        with self._lock:
            return len(self._cache)

    @property
    def max_entries(self) -> int:
        """Configured maximum number of cache entries."""
        with self._lock:
            return self._max_entries

    def get_cache_info(self) -> Dict[str, Any]:
        """Get comprehensive information about the cache state.

        Returns a dictionary containing cache status, size, and a list of
        all cached source keys for debugging and monitoring purposes.

        Returns:
            Dictionary containing:
                - enabled: Boolean indicating if cache is enabled
                - size: Number of cached DataFrames
                - cached_sources: List of cache keys for all stored DataFrames

        Example:
            >>> info = cache.get_cache_info()
            >>> print(f"Cache enabled: {info['enabled']}")
            >>> print(f"Cached sources: {info['cached_sources']}")
        """
        with self._lock:
            return {
                "enabled": self._enabled,
                "size": len(self._cache),
                "max_entries": self._max_entries,
                "cached_sources": list(self._cache.keys()),
            }


def get_data_cache() -> DataSourceCache:
    """Get the global data source cache instance.

    Factory function that returns the singleton DataSourceCache instance.
    This is the recommended way to access the cache from data connectors
    and other parts of the application.

    Returns:
        The singleton DataSourceCache instance.

    Example:
        >>> from slideflow.data.cache import get_data_cache
        >>>
        >>> def load_csv_data(file_path: str) -> pd.DataFrame:
        ...     cache = get_data_cache()
        ...
        ...     # Try to get cached data
        ...     data = cache.get("csv", file_path=file_path)
        ...     if data is not None:
        ...         return data
        ...
        ...     # Load and cache new data
        ...     data = pd.read_csv(file_path)
        ...     cache.set(data, "csv", file_path=file_path)
        ...     return data
    """
    return DataSourceCache()
