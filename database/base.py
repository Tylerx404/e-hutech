#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Interface chung cho các database backend.

Mỗi backend tự xử lý cú pháp SQL riệng (placeholder, JSON, upsert, lock).
Handler chỉ gọi qua facade `DatabaseManager` — không cần biết backend nào.
"""

import abc
import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class BaseDatabase(abc.ABC):
    """Interface chung cho mọi database backend."""

    # ==================== Lifecycle ====================

    @abc.abstractmethod
    async def connect(self) -> None: ...

    @abc.abstractmethod
    async def close(self) -> None: ...

    # ==================== Instance lock ====================

    @abc.abstractmethod
    async def acquire_bot_instance_lock(self, lock_key: int) -> bool: ...

    @abc.abstractmethod
    async def release_bot_instance_lock(self) -> None: ...

    # ==================== Users ====================

    @abc.abstractmethod
    async def save_user(
        self, telegram_user_id: int, username: str, password: str, device_uuid: str
    ) -> bool: ...

    @abc.abstractmethod
    async def get_user(self, telegram_user_id: int) -> Optional[Dict[str, Any]]: ...

    @abc.abstractmethod
    async def get_active_account(self, telegram_user_id: int) -> Optional[Dict[str, Any]]: ...

    @abc.abstractmethod
    async def get_active_user_token(self, telegram_user_id: int) -> Optional[str]: ...

    @abc.abstractmethod
    async def get_user_accounts(
        self, telegram_user_id: int, order_by_login_time: bool = False
    ) -> List[Dict[str, Any]]: ...

    @abc.abstractmethod
    async def add_account(
        self,
        telegram_user_id: int,
        username: str,
        password: str,
        device_uuid: str,
        response_data: Dict[str, Any],
        ho_ten: Optional[str] = None,
    ) -> bool: ...

    @abc.abstractmethod
    async def set_active_account(self, telegram_user_id: int, username: str) -> bool: ...

    @abc.abstractmethod
    async def remove_account(self, telegram_user_id: int, username: str) -> bool: ...

    @abc.abstractmethod
    async def delete_all_accounts(self, telegram_user_id: int) -> bool: ...

    @abc.abstractmethod
    async def delete_user(self, telegram_user_id: int) -> bool: ...

    @abc.abstractmethod
    async def is_user_logged_in(self, telegram_user_id: int) -> bool: ...

    @abc.abstractmethod
    async def get_user_device_uuid_by_username(
        self, telegram_user_id: int, username: str
    ) -> Optional[str]: ...

    @abc.abstractmethod
    async def set_user_login_status(self, telegram_user_id: int, is_logged_in: bool) -> bool: ...

    # ==================== Login responses ====================

    @abc.abstractmethod
    async def save_login_response(
        self,
        telegram_user_id: int,
        username: str,
        response_data: Dict[str, Any],
        ho_ten: Optional[str] = None,
    ) -> bool: ...

    @abc.abstractmethod
    async def get_user_login_response(
        self, telegram_user_id: int
    ) -> Optional[Dict[str, Any]]: ...

    @abc.abstractmethod
    async def get_user_login_response_by_username(
        self, telegram_user_id: int, username: str
    ) -> Optional[Dict[str, Any]]: ...

    # ==================== Logged-in list ====================

    @abc.abstractmethod
    async def get_all_logged_in_users(self) -> List[int]: ...

    # ==================== Policy / consent ====================

    @abc.abstractmethod
    async def has_accepted_policy(self, telegram_user_id: int) -> bool: ...

    @abc.abstractmethod
    async def set_policy_consent(self, telegram_user_id: int, accepted: bool) -> bool: ...

    # ==================== Preferred campus ====================

    @abc.abstractmethod
    async def get_user_preferred_campus(self, telegram_user_id: int) -> Optional[str]: ...

    @abc.abstractmethod
    async def set_user_preferred_campus(
        self, telegram_user_id: int, campus_name: str
    ) -> bool: ...

    @abc.abstractmethod
    async def delete_user_preferred_campus(self, telegram_user_id: int) -> bool: ...

    # ==================== JSON helpers ====================

    @staticmethod
    def dump_json(value: Any) -> str:
        """Serialize dict/list thành JSON string để lưu vào DB."""
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def parse_json(raw: Any) -> Optional[Dict[str, Any]]:
        """Parse JSON từ DB an toàn. Trả về None nếu input rỗng hoặc parse lỗi."""
        if raw is None or raw == "":
            return None
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, (list, str, bytes)):
            try:
                data = json.loads(raw)
                return data if isinstance(data, dict) else None
            except (TypeError, ValueError):
                return None
        return None