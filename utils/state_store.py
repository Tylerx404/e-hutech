#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Lưu state tạm per user trong Redis.

Thay thế `context.user_data` của python-telegram-bot. State được lưu dưới
dạng JSON với key `bot:state:<user_id>`, TTL mặc định 1800s (30 phút).
Khi Redis restart, state sẽ mất và user phải nhập lại.
"""

import json
import logging
from typing import Any, Dict, Optional

from cache.cache_manager import CacheManager

logger = logging.getLogger(__name__)

# TTL mặc định cho state (giây)
DEFAULT_STATE_TTL = 1800

# Tiền tố cho tất cả state keys
STATE_KEY_PREFIX = "bot:state:"


class StateStore:
    """
    Wrapper quanh Redis để lưu state per user.

    Dùng chung connection pool với CacheManager để tránh tạo thêm connection
    pool Redis thứ hai.
    """

    def __init__(self, cache_manager: Optional[CacheManager] = None, ttl: int = DEFAULT_STATE_TTL):
        self.cache_manager = cache_manager or CacheManager()
        self.ttl = ttl

    def _key(self, user_id: int) -> str:
        return f"{STATE_KEY_PREFIX}{user_id}"

    async def get_state(self, user_id: int) -> Dict[str, Any]:
        """
        Lấy state hiện tại của user. Trả về dict rỗng nếu chưa có.
        """
        try:
            r = self.cache_manager.get_redis_client()
            raw = await r.get(self._key(user_id))
            if not raw:
                return {}
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.error("Lỗi đọc state cho user %s: %s", user_id, e)
            return {}

    async def set_state(self, user_id: int, data: Dict[str, Any]) -> None:
        """
        Ghi đè state của user bằng dict mới.
        """
        try:
            r = self.cache_manager.get_redis_client()
            payload = json.dumps(data, ensure_ascii=False)
            await r.set(self._key(user_id), payload, ex=self.ttl)
        except Exception as e:
            logger.error("Lỗi ghi state cho user %s: %s", user_id, e)

    async def update_state(self, user_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge `updates` vào state hiện tại và ghi lại. Trả về state sau khi merge.
        """
        current = await self.get_state(user_id)
        current.update(updates)
        await self.set_state(user_id, current)
        return current

    async def clear_state(self, user_id: int) -> None:
        """
        Xóa toàn bộ state của user.
        """
        try:
            r = self.cache_manager.get_redis_client()
            await r.delete(self._key(user_id))
        except Exception as e:
            logger.error("Lỗi xóa state cho user %s: %s", user_id, e)
