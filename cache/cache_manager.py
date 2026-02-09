#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Quản lý cache sử dụng Redis
"""

import json
import logging
from typing import Optional, Any, Dict
from datetime import datetime

import redis.asyncio as redis

from config.config import Config

logger = logging.getLogger(__name__)

class CacheManager:
    def __init__(self):
        self.config = Config()
        self.redis_pool = None

    async def connect(self):
        """Khởi tạo Redis connection pool."""
        if not self.redis_pool:
            try:
                self.redis_pool = redis.ConnectionPool.from_url(
                    self.config.REDIS_URL,
                    decode_responses=True  # Tự động decode responses thành string
                )
                logger.info("Đã tạo Redis connection pool thành công.")
            except Exception as e:
                logger.error(f"Không thể tạo Redis connection pool: {e}")
                raise

    async def close(self):
        """Đóng Redis connection pool."""
        if self.redis_pool:
            await self.redis_pool.disconnect()
            logger.info("Đã đóng Redis connection pool.")

    def get_redis_client(self) -> redis.Redis:
        """Lấy một client từ connection pool."""
        if not self.redis_pool:
            raise ConnectionError("Redis connection pool chưa được khởi tạo. Hãy gọi connect() trước.")
        return redis.Redis(connection_pool=self.redis_pool)

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Lấy dữ liệu từ cache.

        Args:
            key: Khóa của cache.

        Returns:
            Một dictionary chứa 'data' và 'timestamp', hoặc None nếu không tìm thấy.
        """
        try:
            r = self.get_redis_client()
            cached_data = await r.get(key)
            if cached_data:
                logger.info(f"Cache HIT for key: {key}")
                # Dữ liệu trả về là một dict chứa data và timestamp
                return json.loads(cached_data)
            logger.info(f"Cache MISS for key: {key}")
            return None
        except Exception as e:
            logger.error(f"Lỗi lấy cache cho key '{key}': {e}")
            return None

    async def set(self, key: str, value: Any, ttl: int = 3600):
        """
        Lưu dữ liệu vào cache cùng với timestamp.

        Args:
            key: Khóa của cache.
            value: Dữ liệu cần lưu.
            ttl: Thời gian sống của cache (time-to-live) tính bằng giây. Mặc định là 1 giờ.
        """
        try:
            r = self.get_redis_client()
            # Tạo một đối tượng để lưu trữ cả dữ liệu và timestamp
            data_to_cache = {
                "timestamp": datetime.utcnow().isoformat(),
                "data": value
            }
            serialized_value = json.dumps(data_to_cache, ensure_ascii=False)
            await r.set(key, serialized_value, ex=ttl)
            logger.info(f"Đã lưu cache cho key: {key} với TTL: {ttl} giây.")
        except Exception as e:
            logger.error(f"Lỗi lưu cache cho key '{key}': {e}")

    async def delete(self, key: str):
        """
        Xóa dữ liệu khỏi cache.

        Args:
            key: Khóa của cache cần xóa.
        """
        try:
            r = self.get_redis_client()
            await r.delete(key)
            logger.info(f"Đã xóa cache cho key: {key}")
        except Exception as e:
            logger.error(f"Lỗi xóa cache cho key '{key}': {e}")

    async def clear_user_cache(self, telegram_user_id: int):
        """
        Xóa tất cả cache liên quan đến một người dùng.
        Hữu ích khi người dùng đăng xuất.
        """
        try:
            r = self.get_redis_client()
            # Xóa các cache theo pattern
            keys_to_delete = []
            async for key in r.scan_iter(f"*:{telegram_user_id}*"):
                keys_to_delete.append(key)
            
            if keys_to_delete:
                await r.delete(*keys_to_delete)
                logger.info(f"Đã xóa {len(keys_to_delete)} cache keys cho người dùng {telegram_user_id}.")
        except Exception as e:
            logger.error(f"Lỗi xóa cache cho người dùng {telegram_user_id}: {e}")