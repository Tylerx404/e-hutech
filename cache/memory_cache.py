#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Cache backend dùng dict trong bộ nhớ.

Phù hợp single-instance / dev khi không có Redis. Trade-off:
- Mất khi restart bot.
- Không share giữa nhiều instance.

Cơ chế TTL:
- Lazy expiration: `get` thấy expired thì xóa.
- Background sweeper mỗi 60s dọn key expired không ai truy cập.
- `asyncio.Lock` bảo vệ trong cùng process.

Cấu trúc dữ liệu:
- `_store[key]`: payload đã wrap theo format `{timestamp, data}`.
- `_expires[key]`: epoch giây hết hạn.
- `_user_index[user_id]`: set các key chứa user_id — giúp `clear_user_cache`
  không phải scan toàn bộ store.
"""

import asyncio
import logging
import re
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Optional, Set

from cache.base import BaseCache

logger = logging.getLogger(__name__)

# Tách user_id từ key. Khớp với convention của các handler
# (vd `tkb:123456:2024-1`, `cache:user:123456:diem`).
_USER_ID_RE = re.compile(r":(\d+)(?::|$)")


class MemoryCache(BaseCache):
    """Cache backend lưu trong RAM, có TTL, có user-index, có background sweeper."""

    def __init__(self):
        # key -> payload (đã wrap theo format {timestamp, data})
        self._store: Dict[str, Any] = {}
        # key -> epoch giây hết hạn
        self._expires: Dict[str, float] = {}
        # user_id -> set[key]: index phục vụ clear_user_cache
        self._user_index: Dict[int, Set[str]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._sweeper_task: Optional[asyncio.Task] = None
        self._closed = False

    async def connect(self):
        """Khởi động background sweeper dọn key expired định kỳ (60s)."""
        if self._sweeper_task is None:
            self._sweeper_task = asyncio.create_task(self._sweep_loop())
            logger.info("In-memory cache đã khởi tạo (sweeper 60s).")

    async def close(self):
        """Dừng sweeper, xóa toàn bộ dữ liệu trong RAM."""
        self._closed = True
        if self._sweeper_task and not self._sweeper_task.done():
            self._sweeper_task.cancel()
            try:
                await self._sweeper_task
            except asyncio.CancelledError:
                pass
        self._sweeper_task = None
        async with self._lock:
            self._store.clear()
            self._expires.clear()
            self._user_index.clear()
        logger.info("In-memory cache đã đóng.")

    def _extract_user_id(self, key: str) -> Optional[int]:
        """Tách user_id từ key theo pattern `:(\\d+)(?::|$)`. Trả về None nếu không khớp."""
        m = _USER_ID_RE.search(key)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                return None
        return None

    def _is_expired(self, key: str, now: float) -> bool:
        """Kiểm tra key đã hết hạn chưa."""
        exp = self._expires.get(key)
        return exp is not None and exp <= now

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Lấy value theo key. Nếu expired, xóa luôn (lazy expiration) và trả về None."""
        now = time.time()
        async with self._lock:
            if key not in self._store:
                logger.debug("Cache MISS for key: %s", key)
                return None
            if self._is_expired(key, now):
                self._store.pop(key, None)
                self._expires.pop(key, None)
                for uid_set in self._user_index.values():
                    uid_set.discard(key)
                logger.debug("Cache MISS (expired) for key: %s", key)
                return None
            logger.debug("Cache HIT for key: %s", key)
            return self._store[key]

    async def set(self, key: str, value: Any, ttl: int = 3600):
        """Lưu value kèm timestamp, có TTL (giây). Tự động index user_id nếu có trong key."""
        payload = {
            "timestamp": datetime.utcnow().isoformat(),
            "data": value,
        }
        now = time.time()
        user_id = self._extract_user_id(key)
        async with self._lock:
            self._store[key] = payload
            self._expires[key] = now + ttl
            if user_id is not None:
                self._user_index[user_id].add(key)
        logger.debug("Đã lưu cache cho key: %s với TTL: %s giây.", key, ttl)

    async def delete(self, key: str):
        """Xóa một key khỏi cache và khỏi user index."""
        user_id = self._extract_user_id(key)
        async with self._lock:
            self._store.pop(key, None)
            self._expires.pop(key, None)
            if user_id is not None:
                self._user_index[user_id].discard(key)
        logger.debug("Đã xóa cache cho key: %s", key)

    async def clear_user_cache(self, telegram_user_id: int, log_info: bool = True):
        """Xóa tất cả cache của một user. Dùng user index để tránh scan toàn bộ store."""
        async with self._lock:
            keys = list(self._user_index.get(telegram_user_id, set()))
            for k in keys:
                self._store.pop(k, None)
                self._expires.pop(k, None)
            self._user_index.pop(telegram_user_id, None)
        if log_info and keys:
            logger.info(
                "Đã xóa %s cache keys cho người dùng %s.",
                len(keys), telegram_user_id,
            )

    async def _sweep_loop(self):
        """Background task dọn key expired định kỳ (60s/lần)."""
        try:
            while not self._closed:
                await asyncio.sleep(60)
                now = time.time()
                async with self._lock:
                    expired = [k for k, exp in self._expires.items() if exp <= now]
                    for k in expired:
                        self._store.pop(k, None)
                        self._expires.pop(k, None)
                        for uid_set in self._user_index.values():
                            uid_set.discard(k)
                if expired:
                    logger.debug("Sweeper: đã xóa %s key expired.", len(expired))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("Lỗi trong sweeper: %s", e)
