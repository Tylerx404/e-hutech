#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Lưu state tạm per user qua cache (Redis hoặc in-memory).

Thay thế `context.user_data` của python-telegram-bot. State được lưu dưới
dạng JSON với key `bot:state:<user_id>`, TTL mặc định 1800s (30 phút).

State dùng cho các flow nhiều bước (vd `/dangnhap` hỏi username → password),
do đó TTL ngắn. Khi dùng in-memory cache, state sẽ mất khi bot restart —
user phải bắt đầu lại flow.

StateStore gọi qua wrapper `cache.get/set/delete` nên tương thích với mọi
backend (Redis / memory).
"""

import logging
from typing import Any, Dict, Optional

from cache.base import BaseCache
from cache.cache_manager import CacheManager

logger = logging.getLogger(__name__)

# TTL mặc định cho state (giây) — 30 phút
DEFAULT_STATE_TTL = 1800

# Tiền tố cho tất cả state keys trong cache
STATE_KEY_PREFIX = "bot:state:"


class StateStore:
    """Wrapper quanh cache backend để lưu/đọc state per user."""

    def __init__(self, cache_manager: Optional[CacheManager] = None, ttl: int = DEFAULT_STATE_TTL):
        self.cache_manager = cache_manager or CacheManager()
        # Gọi thẳng backend để tránh qua facade (một tầng indirection thừa).
        self.cache: BaseCache = self.cache_manager.backend
        self.ttl = ttl

    def _key(self, user_id: int) -> str:
        """Sinh cache key cho state của user."""
        return f"{STATE_KEY_PREFIX}{user_id}"

    async def get_state(self, user_id: int) -> Dict[str, Any]:
        """Lấy state hiện tại của user. Trả về dict rỗng nếu chưa có hoặc lỗi."""
        try:
            raw = await self.cache.get(self._key(user_id))
            if not raw:
                return {}
            data = raw.get("data") if isinstance(raw, dict) else None
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.error("Lỗi đọc state cho user %s: %s", user_id, e)
            return {}

    async def set_state(self, user_id: int, data: Dict[str, Any]) -> None:
        """Ghi đè state của user bằng dict mới."""
        try:
            await self.cache.set(self._key(user_id), data, ttl=self.ttl)
        except Exception as e:
            logger.error("Lỗi ghi state cho user %s: %s", user_id, e)

    async def update_state(self, user_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Merge `updates` vào state hiện tại và ghi lại. Trả về state sau khi merge."""
        current = await self.get_state(user_id)
        current.update(updates)
        await self.set_state(user_id, current)
        return current

    async def clear_state(self, user_id: int) -> None:
        """Xóa toàn bộ state của user."""
        try:
            await self.cache.delete(self._key(user_id))
        except Exception as e:
            logger.error("Lỗi xóa state cho user %s: %s", user_id, e)