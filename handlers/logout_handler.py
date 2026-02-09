#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Handler xử lý đăng xuất khỏi hệ thống HUTECH
"""

import json
import logging
import aiohttp
from typing import Dict, Any, Optional

from config.config import Config

logger = logging.getLogger(__name__)

class LogoutHandler:
    def __init__(self, db_manager, cache_manager):
        self.db_manager = db_manager
        self.cache_manager = cache_manager
        self.config = Config()
    
    async def handle_logout(self, telegram_user_id: int, logout_all: bool = False) -> Dict[str, Any]:
        """
        Xử lý đăng xuất khỏi hệ thống HUTECH

        Args:
            telegram_user_id: ID của người dùng trên Telegram
            logout_all: Nếu True, xóa tất cả tài khoản. Nếu False, chỉ xóa account active.

        Returns:
            Dict chứa kết quả đăng xuất
        """
        try:
            # Lấy account active hiện tại
            active_account = await self.db_manager.get_active_account(telegram_user_id)

            if not active_account:
                return {
                    "success": False,
                    "message": "Bạn chưa đăng nhập tài khoản nào."
                }

            username = active_account.get("username")

            if logout_all:
                # Xóa tất cả tài khoản
                # Gọi API logout cho tất cả accounts
                accounts = await self.db_manager.get_user_accounts(telegram_user_id)
                for acc in accounts:
                    token = await self._get_user_token_by_username(telegram_user_id, acc.get("username"))
                    if token:
                        device_uuid = await self.db_manager.get_user_device_uuid_by_username(telegram_user_id, acc.get("username"))
                        if device_uuid:
                            request_data = {"diuu": device_uuid}
                            await self._call_logout_api(token, request_data)

                # Xóa tất cả tài khoản trong DB
                await self.db_manager.delete_all_accounts(telegram_user_id)

                # Xóa cache
                await self.cache_manager.clear_user_cache(telegram_user_id)

                return {
                    "success": True,
                    "message": "Đã đăng xuất khỏi tất cả tài khoản."
                }
            else:
                # Chỉ xóa account active
                token = await self._get_user_token_by_username(telegram_user_id, username)
                device_uuid = await self.db_manager.get_user_device_uuid_by_username(telegram_user_id, username)

                # Gọi API logout nếu có token
                if token and device_uuid:
                    request_data = {"diuu": device_uuid}
                    await self._call_logout_api(token, request_data)

                # Xóa account active
                await self.db_manager.remove_account(telegram_user_id, username)

                # Kiểm tra còn account nào không
                remaining_accounts = await self.db_manager.get_user_accounts(telegram_user_id)

                # Xóa cache
                await self.cache_manager.clear_user_cache(telegram_user_id)

                if remaining_accounts:
                    # Chuyển sang account khác
                    next_account = remaining_accounts[0]
                    await self.db_manager.set_active_account(telegram_user_id, next_account.get("username"))
                    ho_ten = next_account.get("ho_ten") or next_account.get("username")
                    return {
                        "success": True,
                        "message": f"Đã chuyển sang tài khoản: {ho_ten}"
                    }
                else:
                    return {
                        "success": True,
                        "message": "Đăng xuất thành công."
                    }

        except Exception as e:
            logger.error(f"Logout error for user {telegram_user_id}: {e}")
            return {
                "success": False,
                "message": f"Lỗi đăng xuất: {str(e)}",
                "data": None
            }

    async def _get_user_token_by_username(self, telegram_user_id: int, username: str) -> Optional[str]:
        """
        Lấy token của người dùng theo username cụ thể.
        """
        try:
            response_data = await self.db_manager.get_user_login_response_by_username(telegram_user_id, username)
            if not response_data:
                return None

            return response_data.get("token")

        except Exception as e:
            logger.error(f"Error getting token for user {telegram_user_id}/{username}: {e}")
            return None
    
    async def _call_logout_api(self, token: str, request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Gọi API đăng xuất của HUTECH
        
        Args:
            token: Token xác thực
            request_data: Dữ liệu request
            
        Returns:
            Response data từ API hoặc None nếu có lỗi
        """
        try:
            url = f"{self.config.HUTECH_API_BASE_URL}{self.config.HUTECH_LOGOUT_ENDPOINT}"
            headers = self.config.HUTECH_STUDENT_HEADERS.copy()
            headers["authorization"] = f"JWT {token}"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=headers,
                    json=request_data
                ) as response:
                    if response.status == 200:
                        # API đăng xuất trả về status 200 nhưng không có body
                        return {
                            "success": True,
                            "status_code": response.status,
                            "message": "Đăng xuất thành công"
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"Logout API error: {response.status} - {error_text}")
                        return {
                            "error": True,
                            "status_code": response.status,
                            "message": error_text
                        }
        
        except aiohttp.ClientError as e:
            logger.error(f"HTTP client error: {e}")
            return {
                "error": True,
                "message": f"Lỗi kết nối: {str(e)}"
            }
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return {
                "error": True,
                "message": f"Lỗi phân tích dữ liệu: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return {
                "error": True,
                "message": f"Lỗi không xác định: {str(e)}"
            }

    async def _get_user_token(self, telegram_user_id: int) -> Optional[str]:
        """
        Lấy token của người dùng từ database (lấy từ account active). API Logout cần token chính.
        """
        try:
            response_data = await self.db_manager.get_user_login_response(telegram_user_id)
            if not response_data:
                return None

            # API đăng xuất cần token chính
            return response_data.get("token")

        except Exception as e:
            logger.error(f"Error getting token for user {telegram_user_id}: {e}")
            return None

    async def _get_user_device_uuid(self, telegram_user_id: int) -> Optional[str]:
        """
        Lấy device UUID của người dùng từ database (lấy từ account active)

        Args:
            telegram_user_id: ID của người dùng trên Telegram

        Returns:
            Device UUID của người dùng hoặc None nếu không tìm thấy
        """
        try:
            user = await self.db_manager.get_user(telegram_user_id)
            if user:
                return user.get("device_uuid")
            return None

        except Exception as e:
            logger.error(f"Error getting device UUID for user {telegram_user_id}: {e}")
            return None

    async def force_logout(self, telegram_user_id: int) -> Dict[str, Any]:
        """
        Đăng xuất người dùng mà không cần gọi API (dùng khi token không hợp lệ)
        Xóa tất cả tài khoản.

        Args:
            telegram_user_id: ID của người dùng trên Telegram

        Returns:
            Dict chứa kết quả đăng xuất
        """
        try:
            # Xóa tất cả tài khoản
            success = await self.db_manager.delete_all_accounts(telegram_user_id)

            if success:
                return {
                    "success": True,
                    "message": "Đăng xuất thành công"
                }
            else:
                return {
                    "success": False,
                    "message": "Đăng xuất thất bại"
                }

        except Exception as e:
            logger.error(f"Force logout error for user {telegram_user_id}: {e}")
            return {
                "success": False,
                "message": f"Lỗi đăng xuất: {str(e)}"
            }