"""TTL 缓存单元测试."""

import time

from vocab_qc.core.cache import TTLCache


class TestTTLCache:
    def test_set_and_get(self):
        cache = TTLCache()
        cache.set("key1", {"data": 42})
        assert cache.get("key1") == {"data": 42}

    def test_get_missing_key_returns_none(self):
        cache = TTLCache()
        assert cache.get("nonexistent") is None

    def test_expired_entry_returns_none(self):
        cache = TTLCache(default_ttl=0.1)
        cache.set("key1", "value")
        time.sleep(0.15)
        assert cache.get("key1") is None

    def test_custom_ttl_per_key(self):
        cache = TTLCache(default_ttl=10.0)
        cache.set("short", "val", ttl=0.1)
        cache.set("long", "val", ttl=10.0)
        time.sleep(0.15)
        assert cache.get("short") is None
        assert cache.get("long") == "val"

    def test_invalidate(self):
        cache = TTLCache()
        cache.set("key1", "value")
        cache.invalidate("key1")
        assert cache.get("key1") is None

    def test_invalidate_missing_key_no_error(self):
        cache = TTLCache()
        cache.invalidate("nonexistent")  # 不应抛异常

    def test_clear(self):
        cache = TTLCache()
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.get("a") is None
        assert cache.get("b") is None

    def test_overwrite_existing_key(self):
        cache = TTLCache()
        cache.set("key1", "old")
        cache.set("key1", "new")
        assert cache.get("key1") == "new"
