"""线程安全的 TTL 缓存，适用于单进程 uvicorn。"""

import threading
import time
from typing import Any


_MISSING = object()


class TTLCache:
    """进程内 TTL 缓存，用于减少高频数据库查询。"""

    def __init__(self, default_ttl: float = 10.0):
        self._store: dict[str, tuple[float, Any]] = {}
        self._default_ttl = default_ttl
        self._lock = threading.Lock()

    def get(self, key: str) -> Any:
        """取缓存，过期或不存在返回 None。"""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """存缓存。"""
        actual_ttl = ttl if ttl is not None else self._default_ttl
        with self._lock:
            self._store[key] = (time.monotonic() + actual_ttl, value)

    def invalidate(self, key: str) -> None:
        """主动失效指定 key。"""
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        """清空全部缓存。"""
        with self._lock:
            self._store.clear()
