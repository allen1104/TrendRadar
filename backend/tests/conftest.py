"""pytest 全局 fixture。

注意：这里在 import 任何 app 模块之前先注入必需的环境变量，
否则 Settings 会因缺少 SECRET_KEY 而报错。
"""

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-0123456789abcdef0123456789abcdef")
os.environ.setdefault("JWT_REFRESH_SECRET_KEY", "test-refresh-key-fedcba9876543210fedcba98")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("POSTGRES_DB", "trendradar_test")

import fnmatch
import time
from collections.abc import AsyncIterator
from typing import Any

import pytest


class FakeRedis:
    """够用的内存版 Redis，覆盖 auth 用到的命令。

    支持：get / set / setex / incr / expire / ttl / delete / exists / getdel / scan_iter
    """

    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self._expire_at: dict[str, float] = {}

    # ---- 内部

    def _expired(self, key: str) -> bool:
        deadline = self._expire_at.get(key)
        if deadline is not None and deadline <= time.monotonic():
            self._data.pop(key, None)
            self._expire_at.pop(key, None)
            return True
        return False

    def _live_keys(self) -> list[str]:
        return [k for k in list(self._data) if not self._expired(k)]

    # ---- 命令

    async def get(self, key: str) -> str | None:
        if self._expired(key):
            return None
        return self._data.get(key)

    async def set(self, key: str, value: Any) -> bool:
        self._data[key] = str(value)
        return True

    async def setex(self, key: str, ttl: int, value: Any) -> bool:
        self._data[key] = str(value)
        self._expire_at[key] = time.monotonic() + ttl
        return True

    async def incr(self, key: str) -> int:
        current = 0 if self._expired(key) else int(self._data.get(key, 0))
        current += 1
        self._data[key] = str(current)
        return current

    async def expire(self, key: str, ttl: int) -> bool:
        if key not in self._data:
            return False
        self._expire_at[key] = time.monotonic() + ttl
        return True

    async def ttl(self, key: str) -> int:
        if self._expired(key) or key not in self._data:
            return -2
        deadline = self._expire_at.get(key)
        if deadline is None:
            return -1
        return max(0, int(deadline - time.monotonic()))

    async def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if self._data.pop(key, None) is not None:
                removed += 1
            self._expire_at.pop(key, None)
        return removed

    async def exists(self, key: str) -> int:
        return 0 if self._expired(key) or key not in self._data else 1

    async def getdel(self, key: str) -> str | None:
        value = await self.get(key)
        if value is not None:
            await self.delete(key)
        return value

    async def scan_iter(self, match: str = "*", count: int = 100) -> AsyncIterator[str]:
        for key in self._live_keys():
            if fnmatch.fnmatch(key, match):
                yield key

    async def ping(self) -> bool:
        return True


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()
