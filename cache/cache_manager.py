#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Facade cache — chọn backend theo `Config.CACHE_BACKEND` và delegate.

Backend hiện hỗ trợ:
- `redis`:  `RedisCache` — production, share cache giữa các instance.
- `memory`: `MemoryCache` — single instance, dev / nhẹ.

Handler và `StateStore` chỉ cần gọi `get/set/delete/clear_user_cache`
qua facade — không cần biết backend nào đang chạy.
"""

import logging
from typing import Any, Dict, Optional

from cache.base import BaseCache
from cache.memory_cache import MemoryCache
from cache.redis_cache import RedisCache
from config.config import Config

logger = logging.getLogger(__name__)


class CacheManager:
    """Facade chọn backend theo config, delegate mọi method sang backend tương ứng."""

    def __init__(self):
        self.config = Config()
        self.backend: BaseCache = self._build_backend()

    def _build_backend(self) -> BaseCache:
        """Khởi tạo backend theo `Config.CACHE_BACKEND`."""
        if self.config.CACHE_BACKEND == "redis":
            return RedisCache()
        if self.config.CACHE_BACKEND == "memory":
            return MemoryCache()
        raise ValueError(f"CACHE_BACKEND không hợp lệ: {self.config.CACHE_BACKEND}")

    async def connect(self):
        await self.backend.connect()

    async def close(self):
        await self.backend.close()

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        return await self.backend.get(key)

    async def set(self, key: str, value: Any, ttl: int = 3600):
        await self.backend.set(key, value, ttl)

    async def delete(self, key: str):
        await self.backend.delete(key)

    async def clear_user_cache(self, telegram_user_id: int, log_info: bool = True):
        await self.backend.clear_user_cache(telegram_user_id, log_info)
