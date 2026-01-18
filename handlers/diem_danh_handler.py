#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Handler xử lý điểm danh từ hệ thống HUTECH
"""

import json
import logging
import aiohttp
from typing import Dict, Any, Optional, List

from config.config import Config

logger = logging.getLogger(__name__)

# Danh sách các campus với tọa độ
CAMPUS_LOCATIONS = {
    "Thu Duc Campus": {"lat": 10.8550845, "long": 106.7853143},
    "Sai Gon Campus": {"lat": 10.8021417, "long": 106.7149192},
    "Ung Van Khiem Campus": {"lat": 10.8098001, "long": 106.714906},
    "Hitech Park Campus": {"lat": 10.8408075, "long": 106.8088987}
}

class DiemDanhHandler:
    def __init__(self, db_manager, cache_manager):
        self.db_manager = db_manager
        self.cache_manager = cache_manager
        self.config = Config()
    
    async def handle_diem_danh_menu(self, telegram_user_id: int) -> Dict[str, Any]:
        """
        Xử lý hiển thị menu chọn vị trí điểm danh
        
        Args:
            telegram_user_id: ID của người dùng trên Telegram
            
        Returns:
            Dict chứa kết quả và dữ liệu menu
        """
        try:
            # Lấy token của người dùng
            token = await self._get_user_token(telegram_user_id)
            
            if not token:
                return {
                    "success": False,
                    "message": "Bạn chưa đăng nhập. Vui lòng sử dụng /dangnhap để đăng nhập.",
                    "data": None
                }
            
            # Trả về danh sách campus để hiển thị menu
            return {
                "success": True,
                "message": "Lấy danh sách campus thành công",
                "data": {
                    "campus_list": list(CAMPUS_LOCATIONS.keys())
                }
            }
        
        except Exception as e:
            logger.error(f"Điểm danh menu error for user {telegram_user_id}: {e}")
            return {
                "success": False,
                "message": f"🚫 *Lỗi*\n\nĐã xảy ra lỗi khi lấy danh sách campus: {str(e)}",
                "data": None
            }
    
    async def handle_submit_diem_danh(self, telegram_user_id: int, code: str, campus_name: str) -> Dict[str, Any]:
        """
        Xử lý gửi request điểm danh
        
        Args:
            telegram_user_id: ID của người dùng trên Telegram
            code: Mã QR cần quét để điểm danh
            campus_name: Tên campus đã chọn
            
        Returns:
            Dict chứa kết quả và dữ liệu response
        """
        try:
            # Lấy token của người dùng
            token = await self._get_user_token(telegram_user_id)
            
            if not token:
                return {
                    "success": False,
                    "message": "Bạn chưa đăng nhập. Vui lòng sử dụng /dangnhap để đăng nhập.",
                    "data": None
                }
            
            # Lấy vị trí campus
            if campus_name not in CAMPUS_LOCATIONS:
                return {
                    "success": False,
                    "message": "🚫 *Lỗi*\n\nCampus bạn chọn không hợp lệ. Vui lòng thử lại.",
                    "data": None
                }
            
            location = CAMPUS_LOCATIONS[campus_name]
            
            # Lấy device UUID
            device_uuid = await self._get_user_device_uuid(telegram_user_id)
            if not device_uuid:
                return {
                    "success": False,
                    "message": "🚫 *Lỗi*\n\nKhông tìm thấy thông tin thiết bị (device UUID). Vui lòng đăng nhập lại.",
                    "data": None
                }
            
            # Gọi API điểm danh
            response_data = await self._call_diem_danh_api(token, code, device_uuid, location)
            
            # Lưu response vào database
            save_data = {
                "code": code,
                "campus": campus_name,
                "response_data": response_data
            }
            await self._save_diem_danh_response(telegram_user_id, save_data)
            
            # Kiểm tra kết quả
            if response_data:
                # Kiểm tra nếu có statusCode (thất bại)
                if "statusCode" in response_data:
                    statusCode = response_data.get("statusCode")
                    message = response_data.get("reasons", {}).get("message", "Điểm danh thất bại")
                    
                    return {
                        "success": False,
                        "message": f"❌ *Điểm danh thất bại*\n\n{message}",
                        "data": response_data,
                        "has_status_code": True,
                        "show_back_button": True
                    }
                # Kiểm tra nếu có error từ API call
                elif response_data.get("error") and "status_code" in response_data:
                    statusCode = response_data.get("status_code")
                    message = response_data.get("message", "Điểm danh thất bại")
                    
                    return {
                        "success": False,
                        "message": f"❌ *Điểm danh thất bại*\n\n{message}",
                        "data": response_data,
                        "has_status_code": True,
                        "show_back_button": True
                    }
                else:
                    # Thành công
                    return {
                        "success": True,
                        "message": response_data.get("message", "Điểm danh thành công"),
                        "data": response_data,
                        "has_status_code": False
                    }
            else:
                return {
                    "success": False,
                    "message": "🚫 *Lỗi*\n\nKhông thể gửi yêu cầu điểm danh. Vui lòng thử lại sau.",
                    "data": None
                }
        
        except Exception as e:
            logger.error(f"Submit điểm danh error for user {telegram_user_id}: {e}")
            return {
                "success": False,
                "message": f"🚫 *Lỗi*\n\nĐã xảy ra lỗi trong quá trình điểm danh: {str(e)}",
                "data": None
            }
    
    async def _call_diem_danh_api(self, token: str, code: str, device_uuid: str, location: Dict[str, float]) -> Optional[Dict[str, Any]]:
        """
        Gọi API điểm danh của HUTECH
        
        Args:
            token: Token xác thực
            code: Mã QR cần quét
            device_uuid: UUID của thiết bị
            location: Vị trí GPS
            
        Returns:
            Response data từ API hoặc None nếu có lỗi
        """
        try:
            url = f"{self.config.HUTECH_API_BASE_URL}{self.config.HUTECH_DIEM_DANH_SUBMIT_ENDPOINT}"
            
            # Tạo headers
            headers = {
                "user-agent": "Dart/3.5 (dart:io)",
                "authorization": f"JWT {token}",
                "app-key": "MOBILE_HUTECH",
                "content-type": "application/json"
            }
            
            # Tạo request body
            request_data = {
                "code": code,
                "qr_key": "DIEM_DANH",
                "device_id": device_uuid,
                "diuu": device_uuid,
                "location": {
                    "lat": location["lat"],
                    "long": location["long"]
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=headers,
                    json=request_data
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        logger.error(f"Điểm danh API error: {response.status} - {error_text}")
                        try:
                            # Thử parse JSON từ response
                            error_json = await response.json()
                            return {
                                "error": True,
                                "status_code": response.status,
                                "message": error_json.get("reasons", {}).get("message", error_text),
                                "full_response": error_json
                            }
                        except:
                            # Nếu không phải JSON, trả về text
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
    
    async def _save_diem_danh_response(self, telegram_user_id: int, save_data: Dict[str, Any]) -> bool:
        """
        Lưu response từ API điểm danh vào database
        
        Args:
            telegram_user_id: ID của người dùng trên Telegram
            save_data: Dữ liệu để lưu (chứa code, campus, response_data)
            
        Returns:
            True nếu lưu thành công, False nếu có lỗi
        """
        try:
            return self.db_manager.save_diem_danh_response(telegram_user_id, save_data)
        except Exception as e:
            logger.error(f"Error saving điểm danh submit response for user {telegram_user_id}: {e}")
            return False
    
    async def _get_user_token(self, telegram_user_id: int) -> Optional[str]:
        """
        Lấy token của người dùng từ database (ưu tiên token từ old_login_info cho các API cũ).
        """
        try:
            response_data = await self.db_manager.get_user_login_response(telegram_user_id)
            if not response_data:
                return None

            # Ưu tiên sử dụng token từ old_login_info cho các API elearning cũ
            old_login_info = response_data.get("old_login_info")
            if isinstance(old_login_info, dict) and old_login_info.get("token"):
                return old_login_info["token"]
            
            # Nếu không, sử dụng token chính
            return response_data.get("token")

        except Exception as e:
            logger.error(f"Error getting token for user {telegram_user_id}: {e}")
            return None
    
    async def _get_user_device_uuid(self, telegram_user_id: int) -> Optional[str]:
        """
        Lấy device UUID của người dùng từ database
        """
        try:
            user = await self.db_manager.get_user(telegram_user_id)
            if user:
                return user.get("device_uuid")
            return None
        
        except Exception as e:
            logger.error(f"Error getting device UUID for user {telegram_user_id}: {e}")
            return None
    
    def format_campus_menu_message(self) -> str:
        """
        Định dạng danh sách campus thành tin nhắn menu
        
        Returns:
            Chuỗi tin nhắn đã định dạng
        """
        try:
            # Tạo tiêu đề
            message = "📍 *Chọn Vị Trí Điểm Danh*\n\n"
            
            # Hiển thị danh sách campus
            for i, campus_name in enumerate(CAMPUS_LOCATIONS.keys(), 1):
                message += f"{i}. *{campus_name}*\n"
            
            message += "\nVui lòng chọn một campus để tiếp tục điểm danh."
            
            return message
        
        except Exception as e:
            logger.error(f"Error formatting campus menu message: {e}")
            return f"Lỗi định dạng menu campus: {str(e)}"
    
    def format_campus_keyboard(self) -> List[List[Dict[str, str]]]:
        """
        Tạo keyboard cho các nút chọn campus
        
        Returns:
            Danh sách các hàng nút bấm
        """
        try:
            keyboard = []
            
            # Thêm các nút chọn campus (tối đa 2 nút mỗi hàng)
            row = []
            for i, campus_name in enumerate(CAMPUS_LOCATIONS.keys()):
                row.append({
                    "text": campus_name,
                    "callback_data": f"diemdanh_campus_{campus_name}"
                })
                if len(row) == 2 or i == len(CAMPUS_LOCATIONS) - 1:
                    keyboard.append(row)
                    row = []
            
            return keyboard
        
        except Exception as e:
            logger.error(f"Error creating campus keyboard: {e}")
            return []
    
    # def format_diem_danh_input_message(self, campus_name: str) -> str:
    #     """
    #     Định dạng tin nhắn yêu cầu nhập mã QR
        
    #     Args:
    #         campus_name: Tên campus đã chọn
            
    #     Returns:
    #         Chuỗi tin nhắn đã định dạng
    #     """
    #     try:
    #         message = f"📍 *Điểm Danh Tại {campus_name}*\n\n"
    #         message += "Vui lòng nhập mã QR để tiếp tục điểm danh:"
            
    #         return message
        
    #     except Exception as e:
    #         logger.error(f"Error formatting điểm danh input message: {e}")
    #         return f"Lỗi định dạng tin nhắn: {str(e)}"
    
    def format_diem_danh_numeric_message(self, campus_name: str) -> str:
        """
        Định dạng tin nhắn hiển thị menu với bàn phím và hiệu ứng nhập 4 số
        
        Args:
            campus_name: Tên campus đã chọn
            
        Returns:
            Chuỗi tin nhắn đã định dạng
        """
        try:
            message = f"📍 *Điểm Danh Tại {campus_name}*\n\n"
            message += "Nhập mã điểm danh:"
            
            return message
        
        except Exception as e:
            logger.error(f"Error formatting điểm danh numeric message: {e}")
            return f"Lỗi định dạng tin nhắn: {str(e)}"
    
    def format_diem_danh_numeric_keyboard(self) -> List[List[Dict[str, str]]]:
        """
        Tạo bàn phím số cho nhập 4 số
        
        Returns:
            Danh sách các hàng nút bấm
        """
        try:
            keyboard = []
            
            # Hàng 1: 1 2 3
            keyboard.append([
                {"text": "1", "callback_data": "num_1"},
                {"text": "2", "callback_data": "num_2"},
                {"text": "3", "callback_data": "num_3"}
            ])
            
            # Hàng 2: 4 5 6
            keyboard.append([
                {"text": "4", "callback_data": "num_4"},
                {"text": "5", "callback_data": "num_5"},
                {"text": "6", "callback_data": "num_6"}
            ])
            
            # Hàng 3: 7 8 9
            keyboard.append([
                {"text": "7", "callback_data": "num_7"},
                {"text": "8", "callback_data": "num_8"},
                {"text": "9", "callback_data": "num_9"}
            ])
            
            # Hàng 4: Thoát 0 Xoá
            keyboard.append([
                {"text": "Thoát", "callback_data": "num_exit"},
                {"text": "0", "callback_data": "num_0"},
                {"text": "Xoá", "callback_data": "num_delete"}
            ])
            
            return keyboard
        
        except Exception as e:
            logger.error(f"Error creating numeric keyboard: {e}")
            return []
    
    def format_diem_danh_numeric_display(self, current_input: str) -> str:
        """
        Định dạng hiển thị trạng thái nhập số hiện tại
        
        Args:
            current_input: Chuỗi số đã nhập
            
        Returns:
            Chuỗi hiển thị trạng thái
        """
        try:
            # Hiển thị dưới dạng ô vuông cho từng số
            display = ""
            for i in range(4):
                if i < len(current_input):
                    display += f"{current_input[i]} "
                else:
                    display += "⬜ "
            
            return display
        
        except Exception as e:
            logger.error(f"Error formatting numeric display: {e}")
            return "⬜ ⬜ ⬜ ⬜"
    
    def get_campus_location(self, campus_name: str) -> Optional[Dict[str, float]]:
        """
        Lấy vị trí của campus
        
        Args:
            campus_name: Tên campus
            
        Returns:
            Vị trí campus hoặc None nếu không tìm thấy
        """
        try:
            return CAMPUS_LOCATIONS.get(campus_name)
        except Exception as e:
            logger.error(f"Error getting campus location for {campus_name}: {e}")
            return None