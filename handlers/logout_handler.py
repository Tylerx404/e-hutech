#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Handler xử lý đăng xuất khỏi hệ thống HUTECH.

Giao tiếp qua utils/telegram_api (HTTP thuần).
"""

import json
import logging
from typing import Any, Dict, Optional

import aiohttp

from config.config import Config
from utils.telegram_api import TelegramAPI

logger = logging.getLogger(__name__)


class LogoutHandler:
    def __init__(self, db_manager, cache_manager, telegram_api: Optional[TelegramAPI] = None):
        self.db_manager = db_manager
        self.cache_manager = cache_manager
        self.config = Config()
        self.telegram = telegram_api or TelegramAPI(self.config)

    async def handle(self, chat_id: int, user_id: int, reply_to_message_id: Optional[int] = None) -> None:
        """
        Xử lý /dangxuat: xóa account active, gọi API logout HUTECH nếu có token.
        """
        if not await self.db_manager.is_user_logged_in(user_id):
            await self.telegram.send_message(
                chat_id=chat_id,
                text="Bạn chưa đăng nhập.",
                reply_to_message_id=reply_to_message_id,
            )
            return

        result = await self._do_logout(user_id)
        await self.telegram.send_message(
            chat_id=chat_id,
            text=result["message"],
            reply_to_message_id=reply_to_message_id,
        )

    # ==================== Internal ====================

    async def _do_logout(self, telegram_user_id: int) -> Dict[str, Any]:
        try:
            active_account = await self.db_manager.get_active_account(telegram_user_id)
            if not active_account:
                return {"success": False, "message": "Bạn chưa đăng nhập tài khoản nào."}

            username = active_account.get("username")
            token = await self._get_user_token_by_username(telegram_user_id, username)
            device_uuid = await self.db_manager.get_user_device_uuid_by_username(
                telegram_user_id, username
            )
            if token and device_uuid:
                await self._call_logout_api(token, {"diuu": device_uuid})

            await self.db_manager.remove_account(telegram_user_id, username)
            await self.cache_manager.clear_user_cache(telegram_user_id)

            # Nếu còn account khác, chuyển sang account đó
            remaining_accounts = await self.db_manager.get_user_accounts(telegram_user_id)
            if remaining_accounts:
                next_account = remaining_accounts[0]
                await self.db_manager.set_active_account(telegram_user_id, next_account.get("username"))
                ho_ten = next_account.get("ho_ten") or next_account.get("username")
                return {"success": True, "message": f"Đã chuyển sang tài khoản: {ho_ten}"}
            return {"success": True, "message": "Đăng xuất thành công."}
        except Exception as e:
            logger.error("Logout error for user %s: %s", telegram_user_id, e)
            return {"success": False, "message": f"Lỗi đăng xuất: {str(e)}"}

    async def _get_user_token_by_username(self, telegram_user_id: int, username: str) -> Optional[str]:
        try:
            response_data = await self.db_manager.get_user_login_response_by_username(
                telegram_user_id, username
            )
            if not response_data:
                return None
            return response_data.get("token")
        except Exception as e:
            logger.error("Error getting token for user %s/%s: %s", telegram_user_id, username, e)
            return None

    async def _call_logout_api(self, token: str, request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            url = f"{self.config.HUTECH_API_BASE_URL}{self.config.HUTECH_LOGOUT_ENDPOINT}"
            headers = self.config.HUTECH_STUDENT_HEADERS.copy()
            headers["authorization"] = f"JWT {token}"
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=request_data) as response:
                    if response.status == 200:
                        return {"success": True, "status_code": 200, "message": "Đăng xuất thành công"}
                    error_text = await response.text()
                    logger.error("Logout API error: %s - %s", response.status, error_text)
                    return {"error": True, "status_code": response.status, "message": error_text}
        except aiohttp.ClientError as e:
            logger.error("HTTP client error: %s", e)
            return {"error": True, "message": f"Lỗi kết nối: {str(e)}"}
        except json.JSONDecodeError as e:
            logger.error("JSON decode error: %s", e)
            return {"error": True, "message": f"Lỗi phân tích dữ liệu: {str(e)}"}
        except Exception as e:
            logger.error("Unexpected error: %s", e)
            return {"error": True, "message": f"Lỗi không xác định: {str(e)}"}

    async def force_logout(self, telegram_user_id: int) -> Dict[str, Any]:
        """Xóa tất cả account không cần gọi API."""
        try:
            success = await self.db_manager.delete_all_accounts(telegram_user_id)
            return (
                {"success": True, "message": "Đăng xuất thành công"}
                if success
                else {"success": False, "message": "Đăng xuất thất bại"}
            )
        except Exception as e:
            logger.error("Force logout error for user %s: %s", telegram_user_id, e)
            return {"success": False, "message": f"Lỗi đăng xuất: {str(e)}"}
