import hashlib
import threading
import pandas as pd
from typing import Dict, Any, Optional

class DataSourceCache:
    _instance: Optional['DataSourceCache'] = None

    def __new__(cls) -> 'DataSourceCache':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cache: Dict[str, pd.DataFrame] = {}
            cls._instance._enabled = True
            cls._instance._lock = threading.RLock()       # ← add a reentrant lock
        return cls._instance

    def _generate_key(self, source_type: str, **kwargs) -> str:
        parts = [source_type] + [f"{k}:{v}" for k,v in sorted(kwargs.items())]
        return hashlib.md5("|".join(parts).encode()).hexdigest()

    def get(self, source_type: str, **kwargs) -> Optional[pd.DataFrame]:
        if not self._enabled:
            return None
        key = self._generate_key(source_type, **kwargs)
        with self._lock:
            # guard the lookup
            df = self._cache.get(key)
        return df

    def set(self, data: pd.DataFrame, source_type: str, **kwargs) -> None:
        if not self._enabled:
            return
        key = self._generate_key(source_type, **kwargs)
        with self._lock:
            # Store reference instead of copy - safe since cache lifecycle 
            # is contained within a single build operation
            self._cache[key] = data

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def disable(self) -> None:
        with self._lock:
            self._enabled = False
            self._cache.clear()

    def enable(self) -> None:
        with self._lock:
            self._enabled = True

    @property
    def is_enabled(self) -> bool:
        with self._lock:
            return self._enabled

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._cache)

    def get_cache_info(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "enabled": self._enabled,
                "size": len(self._cache),
                "cached_sources": list(self._cache.keys()),
            }

def get_data_cache() -> DataSourceCache:
    return DataSourceCache()
