#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Facade database — chọn backend theo `Config.STORAGE_BACKEND` và delegate.

Backend hiện hỗ trợ:
- `postgres`: `PostgresBackend` (asyncpg) — production, multi-instance.
- `sqlite`:   `SqliteBackend` (aiosqlite) — single instance, dev / nhẹ.

Handler chỉ cần gọi method của `DatabaseManager` — không cần biết backend nào
đang chạy. Mọi method đều delegate sang `self.backend` và trả về cùng kiểu dữ liệu
(dict, list, bool) để tương thích với code cũ.
"""

import logging
from typing import Any, Dict, List, Optional

from config.config import Config
from database.base import BaseDatabase
from database.postgres_backend import PostgresBackend
from database.sqlite_backend import SqliteBackend

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Facade chọn backend theo config, delegate mọi method sang backend tương ứng."""

    def __init__(self):
        self.config = Config()
        self.backend: BaseDatabase = self._build_backend()
        # Expose các thuộc tính nội bộ của backend để tương thích code cũ
        self.pool = getattr(self.backend, "pool", None)
        self._bot_lock_conn = getattr(self.backend, "_bot_lock_conn", None)
        self._bot_lock_key = getattr(self.backend, "_bot_lock_key", None)

    def _build_backend(self) -> BaseDatabase:
        """Khởi tạo backend theo `Config.STORAGE_BACKEND`."""
        if self.config.STORAGE_BACKEND == "postgres":
            return PostgresBackend()
        if self.config.STORAGE_BACKEND == "sqlite":
            return SqliteBackend()
        raise ValueError(f"STORAGE_BACKEND không hợp lệ: {self.config.STORAGE_BACKEND}")

    # ==================== Lifecycle ====================

    async def connect(self):
        await self.backend.connect()

    async def close(self):
        await self.backend.close()

    # ==================== Instance lock ====================

    async def acquire_bot_instance_lock(self, lock_key: int) -> bool:
        return await self.backend.acquire_bot_instance_lock(lock_key)

    async def release_bot_instance_lock(self) -> None:
        await self.backend.release_bot_instance_lock()

    # ==================== Users ====================

    async def save_user(
        self, telegram_user_id: int, username: str, password: str, device_uuid: str
    ) -> bool:
        return await self.backend.save_user(telegram_user_id, username, password, device_uuid)

    async def get_user(self, telegram_user_id: int) -> Optional[Dict[str, Any]]:
        return await self.backend.get_user(telegram_user_id)

    async def get_active_account(self, telegram_user_id: int) -> Optional[Dict[str, Any]]:
        return await self.backend.get_active_account(telegram_user_id)

    async def get_active_user_token(self, telegram_user_id: int) -> Optional[str]:
        return await self.backend.get_active_user_token(telegram_user_id)

    async def get_user_accounts(
        self, telegram_user_id: int, order_by_login_time: bool = False
    ) -> List[Dict[str, Any]]:
        return await self.backend.get_user_accounts(telegram_user_id, order_by_login_time)

    async def add_account(
        self,
        telegram_user_id: int,
        username: str,
        password: str,
        device_uuid: str,
        response_data: Dict[str, Any],
        ho_ten: Optional[str] = None,
    ) -> bool:
        return await self.backend.add_account(
            telegram_user_id, username, password, device_uuid, response_data, ho_ten
        )

    async def set_active_account(self, telegram_user_id: int, username: str) -> bool:
        return await self.backend.set_active_account(telegram_user_id, username)

    async def remove_account(self, telegram_user_id: int, username: str) -> bool:
        return await self.backend.remove_account(telegram_user_id, username)

    async def delete_all_accounts(self, telegram_user_id: int) -> bool:
        return await self.backend.delete_all_accounts(telegram_user_id)

    async def delete_user(self, telegram_user_id: int) -> bool:
        return await self.backend.delete_user(telegram_user_id)

    async def is_user_logged_in(self, telegram_user_id: int) -> bool:
        return await self.backend.is_user_logged_in(telegram_user_id)

    async def get_user_device_uuid_by_username(
        self, telegram_user_id: int, username: str
    ) -> Optional[str]:
        return await self.backend.get_user_device_uuid_by_username(telegram_user_id, username)

    async def set_user_login_status(self, telegram_user_id: int, is_logged_in: bool) -> bool:
        return await self.backend.set_user_login_status(telegram_user_id, is_logged_in)

    # ==================== Login responses ====================

    async def save_login_response(
        self,
        telegram_user_id: int,
        username: str,
        response_data: Dict[str, Any],
        ho_ten: Optional[str] = None,
    ) -> bool:
        return await self.backend.save_login_response(
            telegram_user_id, username, response_data, ho_ten
        )

    async def get_user_login_response(self, telegram_user_id: int) -> Optional[Dict[str, Any]]:
        return await self.backend.get_user_login_response(telegram_user_id)

    async def get_user_login_response_by_username(
        self, telegram_user_id: int, username: str
    ) -> Optional[Dict[str, Any]]:
        return await self.backend.get_user_login_response_by_username(telegram_user_id, username)

    # ==================== Logged-in list ====================

    async def get_all_logged_in_users(self) -> List[int]:
        return await self.backend.get_all_logged_in_users()

    # ==================== Policy / consent ====================

    async def has_accepted_policy(self, telegram_user_id: int) -> bool:
        return await self.backend.has_accepted_policy(telegram_user_id)

    async def set_policy_consent(self, telegram_user_id: int, accepted: bool) -> bool:
        return await self.backend.set_policy_consent(telegram_user_id, accepted)

    # ==================== Preferred campus ====================

    async def get_user_preferred_campus(self, telegram_user_id: int) -> Optional[str]:
        return await self.backend.get_user_preferred_campus(telegram_user_id)

    async def set_user_preferred_campus(
        self, telegram_user_id: int, campus_name: str
    ) -> bool:
        return await self.backend.set_user_preferred_campus(telegram_user_id, campus_name)

    async def delete_user_preferred_campus(self, telegram_user_id: int) -> bool:
        return await self.backend.delete_user_preferred_campus(telegram_user_id)
