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
    
    async def handle_logout(self, telegram_user_id: int) -> Dict[str, Any]:
        """
        Xử lý đăng xuất khỏi hệ thống HUTECH
        
        Args:
            telegram_user_id: ID của người dùng trên Telegram
            
        Returns:
            Dict chứa kết quả đăng xuất
        """
        try:
            # Lấy token và device UUID của người dùng
            token = await self._get_user_token(telegram_user_id)
            device_uuid = await self._get_user_device_uuid(telegram_user_id)
            
            if not token:
                # Tự động sửa lỗi: Nếu DB nói đã login nhưng không có token,
                # thì tiến hành đăng xuất luôn để đồng bộ trạng thái.
                logger.warning(f"Không tìm thấy token cho người dùng {telegram_user_id} dù đã đăng nhập. Tự động đăng xuất.")
                await self.force_logout(telegram_user_id)
                return {
                    "success": True,
                    "message": "Phiên đăng nhập cũ đã hết hạn. Bạn đã được đăng xuất."
                }
            
            if not device_uuid:
                return {
                    "success": False,
                    "message": "Không tìm thấy device UUID. Vui lòng đăng nhập lại."
                }
            
            # Tạo request data
            request_data = {
                "diuu": device_uuid
            }
            
            # Gọi API đăng xuất
            response_data = await self._call_logout_api(token, request_data)
            
            # Lưu response vào database
            # Lưu response vào database (Tạm thời bỏ qua vì không quan trọng)
            # await self._save_logout_response(telegram_user_id, response_data)
            
            # Cập nhật trạng thái đăng nhập của người dùng
            await self.db_manager.set_user_login_status(telegram_user_id, False)
            
            # Xóa cache của người dùng
            await self.cache_manager.clear_user_cache(telegram_user_id)
            
            # Kiểm tra kết quả đăng xuất
            if response_data and not response_data.get("error", False):
                return {
                    "success": True,
                    "message": "Đăng xuất thành công",
                    "data": response_data
                }
            else:
                error_message = response_data.get("message", "Đăng xuất thất bại") if response_data else "Đăng xuất thất bại"
                return {
                    "success": False,
                    "message": error_message,
                    "data": response_data
                }
        
        except Exception as e:
            logger.error(f"Logout error for user {telegram_user_id}: {e}")
            return {
                "success": False,
                "message": f"Lỗi đăng xuất: {str(e)}",
                "data": None
            }
    
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
        Lấy token của người dùng từ database. API Logout cần token chính.
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
        Lấy device UUID của người dùng từ database
        
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
        
        Args:
            telegram_user_id: ID của người dùng trên Telegram
            
        Returns:
            Dict chứa kết quả đăng xuất
        """
        try:
            # Cập nhật trạng thái đăng nhập của người dùng
            success = await self.db_manager.set_user_login_status(telegram_user_id, False)
            
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