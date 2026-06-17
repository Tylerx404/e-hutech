#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Cache backend dùng Redis.

Lưu value theo format `{timestamp, data}` để thống nhất với `MemoryCache`.
Hỗ trợ share cache giữa nhiều instance, phù hợp production.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

import redis.asyncio as redis

from cache.base import BaseCache
from config.config import Config

logger = logging.getLogger(__name__)


class RedisCache(BaseCache):
    def __init__(self):
        self.config = Config()
        self.redis_pool: Optional[redis.ConnectionPool] = None

    async def connect(self):
        """Tạo Redis connection pool từ REDIS_URL."""
        if not self.redis_pool:
            try:
                self.redis_pool = redis.ConnectionPool.from_url(
                    self.config.REDIS_URL,
                    decode_responses=True,
                )
                logger.info("Đã tạo Redis connection pool thành công.")
            except Exception as e:
                logger.error("Không thể tạo Redis connection pool: %s", e)
                raise

    async def close(self):
        """Đóng connection pool khi bot dừng."""
        if self.redis_pool:
            await self.redis_pool.disconnect()
            logger.info("Đã đóng Redis connection pool.")

    def get_redis_client(self) -> redis.Redis:
        """Lấy client mới từ pool. Dùng nội bộ và cho `StateStore` nếu cần
        truy cập trực tiếp Redis. Các handler nên dùng wrapper `get/set/delete`."""
        if not self.redis_pool:
            raise ConnectionError("Redis connection pool chưa được khởi tạo. Hãy gọi connect() trước.")
        return redis.Redis(connection_pool=self.redis_pool)

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Lấy value theo key. Trả về dict `{timestamp, data}` hoặc None nếu miss."""
        try:
            r = self.get_redis_client()
            cached_data = await r.get(key)
            if cached_data:
                logger.debug("Cache HIT for key: %s", key)
                return json.loads(cached_data)
            logger.debug("Cache MISS for key: %s", key)
            return None
        except Exception as e:
            logger.error("Lỗi lấy cache cho key '%s': %s", key, e)
            return None

    async def set(self, key: str, value: Any, ttl: int = 3600):
        """Lưu value kèm timestamp, có TTL (giây)."""
        try:
            r = self.get_redis_client()
            data_to_cache = {
                "timestamp": datetime.utcnow().isoformat(),
                "data": value,
            }
            await r.set(key, json.dumps(data_to_cache, ensure_ascii=False), ex=ttl)
            logger.debug("Đã lưu cache cho key: %s với TTL: %s giây.", key, ttl)
        except Exception as e:
            logger.error("Lỗi lưu cache cho key '%s': %s", key, e)

    async def delete(self, key: str):
        """Xóa một key khỏi cache."""
        try:
            r = self.get_redis_client()
            await r.delete(key)
            logger.debug("Đã xóa cache cho key: %s", key)
        except Exception as e:
            logger.error("Lỗi xóa cache cho key '%s': %s", key, e)

    async def clear_user_cache(self, telegram_user_id: int, log_info: bool = True):
        """Xóa tất cả cache keys có chứa `:{user_id}` trong tên.
        Pattern này khớp với format key mà các handler dùng (vd `tkb:{user_id}:2024-1`)."""
        try:
            r = self.get_redis_client()
            keys_to_delete = []
            async for key in r.scan_iter(f"*:{telegram_user_id}*"):
                keys_to_delete.append(key)
            if keys_to_delete:
                await r.delete(*keys_to_delete)
                if log_info:
                    logger.info(
                        "Đã xóa %s cache keys cho người dùng %s.",
                        len(keys_to_delete), telegram_user_id,
                    )
        except Exception as e:
            logger.error("Lỗi xóa cache cho người dùng %s: %s", telegram_user_id, e)