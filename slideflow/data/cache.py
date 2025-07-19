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
    - Memory-efficient reference storage (no copying)
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
import threading
import pandas as pd
from typing import Dict, Any, Optional

class DataSourceCache:
    """Thread-safe singleton cache for DataFrame storage in Slideflow.
    
    This class implements a singleton pattern to ensure only one cache instance
    exists per application. It provides thread-safe operations for storing and
    retrieving DataFrames using MD5-based keys generated from source parameters.
    
    The cache is designed to be transparent to data connectors and automatically
    manages memory-efficient storage by storing DataFrame references rather than
    copies. This is safe because the cache lifecycle is contained within single
    build operations.
    
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
        _cache: Thread-safe dictionary storing DataFrame references
        _enabled: Boolean flag controlling cache operations
        _lock: Reentrant lock for thread-safe operations
    """
    _instance: Optional['DataSourceCache'] = None

    def __new__(cls) -> 'DataSourceCache':
        """Create or return the singleton cache instance.
        
        Implements the singleton pattern by creating a new instance only if
        one doesn't already exist. Initializes the cache dictionary, enabled
        flag, and thread lock on first creation.
        
        Returns:
            The singleton DataSourceCache instance.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cache: Dict[str, pd.DataFrame] = {}
            cls._instance._enabled = True
            cls._instance._lock = threading.RLock()       # ← add a reentrant lock
        return cls._instance

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
        parts = [source_type] + [f"{k}:{v}" for k,v in sorted(kwargs.items())]
        return hashlib.md5("|".join(parts).encode()).hexdigest()

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
        if not self._enabled:
            return None
        key = self._generate_key(source_type, **kwargs)
        with self._lock:
            # guard the lookup
            df = self._cache.get(key)
        return df

    def set(self, data: pd.DataFrame, source_type: str, **kwargs) -> None:
        """Store a DataFrame in the cache.
        
        Caches the provided DataFrame using a key generated from the source type
        and parameters. The cache stores a reference to the DataFrame rather than
        a copy for memory efficiency. This is safe because the cache lifecycle
        is contained within single build operations.
        
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
        if not self._enabled:
            return
        key = self._generate_key(source_type, **kwargs)
        with self._lock:
            # Store reference instead of copy - safe since cache lifecycle 
            # is contained within a single build operation
            self._cache[key] = data

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
            self._cache.clear()

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
            self._cache.clear()

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
