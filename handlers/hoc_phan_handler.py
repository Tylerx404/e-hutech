#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Handler xử lý học phần từ hệ thống HUTECH
"""

import json
import logging
import aiohttp
import io
import asyncio
import unicodedata
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill

from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes, Application, CommandHandler, CallbackQueryHandler

from config.config import Config
from utils.button_style import make_inline_button

logger = logging.getLogger(__name__)

class HocPhanHandler:
    def __init__(self, db_manager, cache_manager):
        self.db_manager = db_manager
        self.cache_manager = cache_manager
        self.config = Config()
    
    async def handle_hoc_phan(self, telegram_user_id: int) -> Dict[str, Any]:
        """
        Xử lý lấy danh sách năm học - học kỳ của người dùng
        
        Args:
            telegram_user_id: ID của người dùng trên Telegram
            
        Returns:
            Dict chứa kết quả và dữ liệu năm học - học kỳ
        """
        try:
            cache_key = f"nam_hoc_hoc_ky:{telegram_user_id}"

            # 1. Kiểm tra cache
            cached_result = await self.cache_manager.get(cache_key)
            if cached_result:
                nam_hoc_data = cached_result.get("data")
                timestamp = cached_result.get("timestamp")

                processed_data = self._process_nam_hoc_hoc_ky_data(nam_hoc_data)
                processed_data["timestamp"] = timestamp

                return {
                    "success": True,
                    "message": "Lấy danh sách năm học - học kỳ thành công",
                    "data": processed_data
                }

            # 2. Nếu cache miss, gọi API
            token = await self._get_user_token(telegram_user_id)
            
            if not token:
                return {
                    "success": False,
                    "message": "Bạn chưa đăng nhập. Vui lòng sử dụng /dangnhap để đăng nhập.",
                    "data": None
                }
            
            response_data = await self._call_nam_hoc_hoc_ky_api(token)
            
            # 3. Lưu vào cache
            if response_data and isinstance(response_data, list):
                await self.cache_manager.set(cache_key, response_data, ttl=86400) # Cache trong 24 giờ
            
            # Kiểm tra kết quả
            if response_data and isinstance(response_data, list):
                # Xử lý dữ liệu năm học - học kỳ
                processed_data = self._process_nam_hoc_hoc_ky_data(response_data)
                processed_data["timestamp"] = datetime.utcnow().isoformat() # Thêm timestamp mới
                
                return {
                    "success": True,
                    "message": "Lấy danh sách năm học - học kỳ thành công (dữ liệu mới)",
                    "data": processed_data
                }
            else:
                return {
                    "success": False,
                    "message": "🚫 *Lỗi*\n\nKhông thể lấy danh sách năm học - học kỳ. Vui lòng thử lại sau.",
                    "data": response_data
                }
        
        except Exception as e:
            logger.error(f"Học phần error for user {telegram_user_id}: {e}")
            return {
                "success": False,
                "message": f"🚫 *Lỗi*\n\nĐã xảy ra lỗi khi lấy danh sách năm học - học kỳ: {str(e)}",
                "data": None
            }
    
    async def handle_search_hoc_phan(self, telegram_user_id: int, nam_hoc_hoc_ky_list: List[str]) -> Dict[str, Any]:
        """
        Xử lý tìm kiếm học phần theo danh sách năm học - học kỳ
        
        Args:
            telegram_user_id: ID của người dùng trên Telegram
            nam_hoc_hoc_ky_list: Danh sách mã năm học - học kỳ
            
        Returns:
            Dict chứa kết quả và dữ liệu học phần
        """
        try:
            # Tạo cache key dựa trên user_id và danh sách năm học
            cache_key = f"search_hoc_phan:{telegram_user_id}:{':'.join(sorted(nam_hoc_hoc_ky_list))}"

            # 1. Kiểm tra cache
            cached_result = await self.cache_manager.get(cache_key)
            if cached_result:
                processed_data = self._process_search_hoc_phan_data(cached_result.get("data", []))
                return {
                    "success": True,
                    "message": "Tìm kiếm học phần thành công (từ cache)",
                    "data": processed_data
                }

            # 2. Nếu cache miss, gọi API
            token = await self._get_user_token(telegram_user_id)
            
            if not token:
                return {
                    "success": False,
                    "message": "Bạn chưa đăng nhập. Vui lòng sử dụng /dangnhap để đăng nhập.",
                    "data": None
                }
            
            response_data = await self._call_search_hoc_phan_api(token, nam_hoc_hoc_ky_list)

            # Nếu lần 1 thất bại theo đúng điều kiện trả message lỗi bên dưới, retry 1 lần với renew=true
            if not (response_data and isinstance(response_data, list)):
                logger.warning(
                    "Search học phần thất bại lần 1 | user_id=%s nam_hoc_hoc_ky=%s | retry lần 2 với renew=true",
                    telegram_user_id,
                    nam_hoc_hoc_ky_list,
                )
                response_data = await self._call_search_hoc_phan_api(
                    token,
                    nam_hoc_hoc_ky_list,
                    use_renew=True,
                )
            
            # 3. Lưu vào cache nếu thành công
            if response_data and isinstance(response_data, list):
                await self.cache_manager.set(cache_key, response_data, ttl=3600) # Cache trong 1 giờ
            
            # Kiểm tra kết quả
            if response_data and isinstance(response_data, list):
                # Xử lý dữ liệu học phần
                # Xử lý dữ liệu học phần
                processed_data = self._process_search_hoc_phan_data(response_data)
                processed_data["timestamp"] = datetime.utcnow().isoformat()
                
                return {
                    "success": True,
                    "message": "Tìm kiếm học phần thành công",
                    "data": processed_data
                }
            else:
                return {
                    "success": False,
                    "message": "🚫 *Lỗi*: Không thể tìm kiếm học phần. Vui lòng thử lại sau.",
                    "data": response_data
                }
        
        except Exception as e:
            logger.error(f"Search học phần error for user {telegram_user_id}: {e}")
            return {
                "success": False,
                "message": f"🚫 *Lỗi*\n\nĐã xảy ra lỗi khi tìm kiếm học phần: {str(e)}",
                "data": None
            }
    
    async def handle_diem_danh(self, telegram_user_id: int, key_lop_hoc_phan: str) -> Dict[str, Any]:
        """
        Xử lý lấy lịch sử điểm danh của một học phần
        
        Args:
            telegram_user_id: ID của người dùng trên Telegram
            key_lop_hoc_phan: Khóa lớp học phần
            
        Returns:
            Dict chứa kết quả và dữ liệu điểm danh
        """
        try:
            cache_key = f"diem_danh:{telegram_user_id}:{key_lop_hoc_phan}"

            # 1. Kiểm tra cache
            cached_result = await self.cache_manager.get(cache_key)
            if cached_result:
                processed_data = self._process_diem_danh_data(cached_result.get("data", []))
                return {
                    "success": True,
                    "message": "Lấy lịch sử điểm danh thành công (từ cache)",
                    "data": processed_data
                }

            # 2. Nếu cache miss, gọi API
            token = await self._get_user_token(telegram_user_id)
            
            if not token:
                return {
                    "success": False,
                    "message": "Bạn chưa đăng nhập. Vui lòng sử dụng /dangnhap để đăng nhập.",
                    "data": None
                }
            
            response_data = await self._call_diem_danh_api(token, key_lop_hoc_phan)
            
            # 3. Lưu vào cache nếu thành công
            if response_data and isinstance(response_data, dict) and "result" in response_data:
                await self.cache_manager.set(cache_key, response_data["result"], ttl=3600) # Cache trong 1 giờ

            # Kiểm tra kết quả
            if response_data and isinstance(response_data, dict) and "result" in response_data:
                # Xử lý dữ liệu điểm danh
                diem_danh_list = response_data["result"]
                processed_data = self._process_diem_danh_data(diem_danh_list)
                processed_data["timestamp"] = datetime.utcnow().isoformat()
                
                return {
                    "success": True,
                    "message": "Lấy lịch sử điểm danh thành công",
                    "data": processed_data
                }
            else:
                # Xử lý lỗi từ API
                error_message = "Danh sách điểm danh chưa được cập nhật"
                if response_data and response_data.get("error"):
                    try:
                        # Thử parse message nếu nó là JSON string
                        api_error_details = json.loads(response_data.get("message", "{}"))
                        # Ưu tiên lấy message từ reasons, sau đó là errorMessage
                        extracted_message = api_error_details.get("reasons", {}).get("message") or api_error_details.get("errorMessage")
                        if extracted_message:
                             error_message = extracted_message.split(" - ", 1)[-1] # Lấy phần thông báo lỗi chính
                    except (json.JSONDecodeError, AttributeError):
                        # Nếu message không phải JSON hoặc không có cấu trúc mong đợi, sử dụng message gốc
                        if isinstance(response_data.get("message"), str):
                            error_message = response_data["message"]

                error_flag = response_data.get("error") if isinstance(response_data, dict) else None
                api_message = response_data.get("message") if isinstance(response_data, dict) else None
                if isinstance(api_message, str):
                    api_message = api_message[:200]
                logger.warning(
                    "Invalid response data or API error | user_id=%s key_lop_hoc_phan=%s error=%s message=%s",
                    telegram_user_id,
                    key_lop_hoc_phan,
                    error_flag,
                    api_message,
                )
                return {
                    "success": False,
                    "message": f"🚫 *Lỗi*\n\n{error_message}",
                    "data": response_data
                }
        
        except Exception as e:
            logger.error(f"Điểm danh error for user {telegram_user_id}: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"🚫 *Lỗi*\n\nĐã xảy ra lỗi khi lấy lịch sử điểm danh: {str(e)}",
                "data": None
            }
    
    async def handle_danh_sach_sinh_vien(self, telegram_user_id: int, key_lop_hoc_phan: str) -> Dict[str, Any]:
        """
        Xử lý lấy danh sách sinh viên của một học phần
        
        Args:
            telegram_user_id: ID của người dùng trên Telegram
            key_lop_hoc_phan: Khóa lớp học phần
            
        Returns:
            Dict chứa kết quả và dữ liệu danh sách sinh viên
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
            
            # Gọi API danh sách sinh viên
            response_data = await self._call_danh_sach_sinh_vien_api(token, key_lop_hoc_phan)
            
            # Kiểm tra kết quả
            if response_data and isinstance(response_data, dict):
                # Xử lý dữ liệu danh sách sinh viên
                processed_data = self._process_danh_sach_sinh_vien_data(response_data)
                
                return {
                    "success": True,
                    "message": "Lấy danh sách sinh viên thành công",
                    "data": processed_data
                }
            else:
                return {
                    "success": False,
                    "message": "🚫 *Lỗi*\n\nKhông thể lấy danh sách sinh viên. Vui lòng thử lại sau.",
                    "data": response_data
                }
        
        except Exception as e:
            logger.error(f"Danh sách sinh viên error for user {telegram_user_id}: {e}")
            return {
                "success": False,
                "message": f"🚫 *Lỗi*\n\nĐã xảy ra lỗi khi lấy danh sách sinh viên: {str(e)}",
                "data": None
            }
    
    async def _call_nam_hoc_hoc_ky_api(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Gọi API lấy danh sách năm học - học kỳ của HUTECH
        
        Args:
            token: Token xác thực
            
        Returns:
            Response data từ API hoặc None nếu có lỗi
        """
        try:
            url = f"{self.config.HUTECH_API_BASE_URL}{self.config.HUTECH_HOC_PHAN_NAM_HOC_HOC_KY_ENDPOINT}"
            
            # Tạo headers riêng cho API học phần
            headers = self.config.HUTECH_MOBILE_HEADERS.copy()
            headers["authorization"] = f"JWT {token}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=headers
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        logger.error(f"Năm học - học kỳ API error: {response.status} - {error_text}")
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
    
    async def _call_search_hoc_phan_api(
        self,
        token: str,
        nam_hoc_hoc_ky_list: List[str],
        use_renew: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Gọi API tìm kiếm học phần của HUTECH
        
        Args:
            token: Token xác thực
            nam_hoc_hoc_ky_list: Danh sách mã năm học - học kỳ
            
        Returns:
            Response data từ API hoặc None nếu có lỗi
        """
        try:
            url = f"{self.config.HUTECH_API_BASE_URL}{self.config.HUTECH_HOC_PHAN_SEARCH_ENDPOINT}"
            
            # Tạo headers riêng cho API học phần
            headers = self.config.HUTECH_MOBILE_HEADERS.copy()
            headers["authorization"] = f"JWT {token}"
            
            # Request body theo mode
            request_body = {
                "nam_hoc_hoc_ky": nam_hoc_hoc_ky_list
            }
            if use_renew:
                request_body = {
                    "renew": True,
                    "nam_hoc_hoc_ky": nam_hoc_hoc_ky_list
                }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=headers,
                    json=request_body
                ) as response:
                    if response.status == 200:
                        return await response.json()

                    error_text = await response.text()
                    logger.error(
                        "Search học phần API error%s: %s - %s",
                        " (renew=true)" if use_renew else "",
                        response.status,
                        error_text
                    )
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
    
    async def _call_diem_danh_api(self, token: str, key_lop_hoc_phan: str) -> Optional[Dict[str, Any]]:
        """
        Gọi API điểm danh của HUTECH
        
        Args:
            token: Token xác thực
            key_lop_hoc_phan: Khóa lớp học phần
            
        Returns:
            Response data từ API hoặc None nếu có lỗi
        """
        try:
            url = f"{self.config.HUTECH_API_BASE_URL}{self.config.HUTECH_HOC_PHAN_DIEM_DANH_ENDPOINT}"
            
            # Tạo headers riêng cho API học phần
            headers = self.config.HUTECH_MOBILE_HEADERS.copy()
            headers["authorization"] = f"JWT {token}"
            
            # Tạo query parameters
            params = {
                "key_lop_hoc_phan": key_lop_hoc_phan
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=headers,
                    params=params
                ) as response:
                    
                    if response.status == 200:
                        response_data = await response.json()
                        return response_data
                    else:
                        error_text = await response.text()
                        logger.error(f"Điểm danh API error: {response.status} - {error_text}")
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
            logger.error(f"Unexpected error: {e}", exc_info=True)
            return {
                "error": True,
                "message": f"Lỗi không xác định: {str(e)}"
            }
    
    async def _call_danh_sach_sinh_vien_api(self, token: str, key_lop_hoc_phan: str) -> Optional[Dict[str, Any]]:
        """
        Gọi API danh sách sinh viên của HUTECH
        
        Args:
            token: Token xác thực
            key_lop_hoc_phan: Khóa lớp học phần
            
        Returns:
            Response data từ API hoặc None nếu có lỗi
        """
        try:
            url = f"{self.config.HUTECH_API_BASE_URL}{self.config.HUTECH_HOC_PHAN_DANH_SACH_SINH_VIEN_ENDPOINT}"
            
            # Tạo headers riêng cho API học phần
            headers = self.config.HUTECH_MOBILE_HEADERS.copy()
            headers["authorization"] = f"JWT {token}"
            
            # Tạo query parameters
            params = {
                "key_lop_hoc_phan": key_lop_hoc_phan
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=headers,
                    params=params
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        logger.error(f"Danh sách sinh viên API error: {response.status} - {error_text}")
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

    def _format_hoc_ky_label(self, hoc_ky: Any) -> str:
        """
        Chuẩn hóa nhãn hiển thị học kỳ cho tin nhắn theo quy ước backend.

        Args:
            hoc_ky: Mã học kỳ backend trả về

        Returns:
            Nhãn học kỳ rút gọn để hiển thị trong tin nhắn
        """
        hoc_ky_str = str(hoc_ky).strip()

        if not hoc_ky_str or hoc_ky_str == "N/A":
            return "N/A"

        normalized_hoc_ky = hoc_ky_str.lstrip("0") or hoc_ky_str
        hoc_ky_mapping = {
            "1": "HK1",
            "2": "HK phụ HK1",
            "3": "HK2",
            "4": "HK phụ HK2",
            "5": "HK3",
        }

        return hoc_ky_mapping.get(normalized_hoc_ky, hoc_ky_str)

    def _format_hoc_ky_excel_label(self, hoc_ky: Any) -> str:
        """
        Chuẩn hóa nhãn học kỳ cho file Excel danh sách sinh viên.

        Args:
            hoc_ky: Mã học kỳ backend trả về

        Returns:
            Nhãn học kỳ gọn cho file Excel
        """
        hoc_ky_str = str(hoc_ky).strip()

        if not hoc_ky_str or hoc_ky_str == "N/A":
            return "N/A"

        normalized_hoc_ky = hoc_ky_str.lstrip("0") or hoc_ky_str
        hoc_ky_mapping = {
            "1": "1",
            "2": "phụ HK1",
            "3": "2",
            "4": "phụ HK2",
            "5": "3",
        }

        return hoc_ky_mapping.get(normalized_hoc_ky, hoc_ky_str)
    
    def _process_nam_hoc_hoc_ky_data(self, nam_hoc_hoc_ky_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Xử lý dữ liệu năm học - học kỳ

        Args:
            nam_hoc_hoc_ky_data: Dữ liệu năm học - học kỳ thô từ API

        Returns:
            Dữ liệu đã được xử lý
        """
        try:
            # Lọc chỉ giữ lại mã lẻ
            filtered_data = [item for item in nam_hoc_hoc_ky_data
                           if int(item.get("ma_hoc_ky", "0")[-1]) % 2 != 0]

            # Sắp xếp theo mã năm học - học kỳ (mới nhất lên đầu)
            sorted_data = sorted(filtered_data, key=lambda x: x.get("ma_hoc_ky", ""), reverse=True)

            return {
                "nam_hoc_hoc_ky_list": sorted_data
            }

        except Exception as e:
            logger.error(f"Error processing năm học - học kỳ data: {e}")
            return {
                "nam_hoc_hoc_ky_list": []
            }
    
    def _process_search_hoc_phan_data(self, search_hoc_phan_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Xử lý dữ liệu tìm kiếm học phần

        Args:
            search_hoc_phan_data: Dữ liệu tìm kiếm học phần thô từ API

        Returns:
            Dữ liệu đã được xử lý
        """
        try:
            # Sắp xếp theo năm học, học kỳ, tên môn học
            sorted_data = sorted(search_hoc_phan_data, key=lambda x: (
                x.get("json_thong_tin", {}).get("nam_hoc", ""),
                x.get("json_thong_tin", {}).get("hoc_ky", ""),
                x.get("json_thong_tin", {}).get("ten_mon_hoc", "")
            ), reverse=True)

            return {
                "hoc_phan_list": sorted_data
            }

        except Exception as e:
            logger.error(f"Error processing search học phần data: {e}")
            return {
                "hoc_phan_list": []
            }
    
    def _process_diem_danh_data(self, diem_danh_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Xử lý dữ liệu điểm danh
        
        Args:
            diem_danh_data: Dữ liệu điểm danh thô từ API
            
        Returns:
            Dữ liệu đã được xử lý
        """
        try:
            
            # Hàm chuyển đổi ngày từ chuỗi sang datetime để sắp xếp đúng
            def parse_date(date_str):
                try:
                    # Định dạng ngày là dd/mm/yyyy
                    return datetime.strptime(date_str, "%d/%m/%Y")
                except (ValueError, TypeError):
                    # Nếu không thể chuyển đổi, trả về một ngày rất xa trong tương lai
                    return datetime.max
            
            # Sắp xếp theo ngày học tăng dần (từ cũ đến mới)
            sorted_data = sorted(diem_danh_data, key=lambda x: parse_date(x.get("lich_trinh", {}).get("ngay_hoc", "")))
            
            return {
                "diem_danh_list": sorted_data
            }
        
        except Exception as e:
            logger.error(f"Error processing điểm danh data: {e}", exc_info=True)
            return {
                "diem_danh_list": []
            }
    
    def _get_vietnamese_char_sort_key(self, char: str) -> tuple:
        """
        Tạo khóa sắp xếp cho một ký tự theo bảng chữ cái tiếng Việt.
        """
        vietnamese_alphabet_order = {
            "a": 0,
            "ă": 1,
            "â": 2,
            "b": 3,
            "c": 4,
            "d": 5,
            "đ": 6,
            "e": 7,
            "ê": 8,
            "g": 9,
            "h": 10,
            "i": 11,
            "k": 12,
            "l": 13,
            "m": 14,
            "n": 15,
            "o": 16,
            "ô": 17,
            "ơ": 18,
            "p": 19,
            "q": 20,
            "r": 21,
            "s": 22,
            "t": 23,
            "u": 24,
            "ư": 25,
            "v": 26,
            "x": 27,
            "y": 28,
        }
        tone_order = {
            "": 0,
            "̀": 1,
            "̉": 2,
            "̃": 3,
            "́": 4,
            "̣": 5,
        }

        normalized_char = unicodedata.normalize("NFD", char.casefold())
        if not normalized_char:
            return (len(vietnamese_alphabet_order), 0, 0)

        if char.casefold() == "đ":
            return (vietnamese_alphabet_order["đ"], 0, ord("đ"))

        base_char = normalized_char[0]
        combining_marks = set(normalized_char[1:])

        if base_char == "a":
            if "̆" in combining_marks:
                letter = "ă"
            elif "̂" in combining_marks:
                letter = "â"
            else:
                letter = "a"
        elif base_char == "e":
            letter = "ê" if "̂" in combining_marks else "e"
        elif base_char == "o":
            if "̛" in combining_marks:
                letter = "ơ"
            elif "̂" in combining_marks:
                letter = "ô"
            else:
                letter = "o"
        elif base_char == "u":
            letter = "ư" if "̛" in combining_marks else "u"
        else:
            letter = base_char

        tone_rank = 0
        for mark, rank in tone_order.items():
            if mark and mark in combining_marks:
                tone_rank = rank
                break

        letter_rank = vietnamese_alphabet_order.get(letter, len(vietnamese_alphabet_order) + ord(base_char))
        return (letter_rank, tone_rank, ord(base_char))

    def _build_vietnamese_sort_key(self, value: str) -> tuple:
        """
        Tạo khóa sắp xếp cho chuỗi theo bảng chữ cái tiếng Việt.
        """
        normalized_value = "".join((value or "").split()).casefold()
        return tuple(self._get_vietnamese_char_sort_key(char) for char in normalized_value)

    def _process_danh_sach_sinh_vien_data(self, danh_sach_sinh_vien_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Xử lý dữ liệu danh sách sinh viên
        
        Args:
            danh_sach_sinh_vien_data: Dữ liệu danh sách sinh viên thô từ API
            
        Returns:
            Dữ liệu đã được xử lý
        """
        try:
            # Lấy thông tin lớp học phần
            lop_info = danh_sach_sinh_vien_data.get("lop", {})
            json_member = lop_info.get("json_member", {})
            
            # Chuyển đổi json_member thành danh sách sinh viên
            sinh_vien_list = []
            for mssv, info in json_member.items():
                # Tách họ và tên
                ho_ten = info.get("ho_ten", "")
                parts = ho_ten.split()
                if len(parts) > 1:
                    ho = " ".join(parts[:-1])
                    ten = parts[-1]
                else:
                    ho = ""
                    ten = ho_ten
                
                sinh_vien_list.append({
                    "mssv": mssv,
                    "ho": ho,
                    "ten": ten,
                    "lop": info.get("lop", ""),
                    "ho_ten_day_du": ho_ten  # Giữ họ tên đầy đủ để sử dụng nếu cần
                })
            
            sinh_vien_list.sort(
                key=lambda student: (
                    self._build_vietnamese_sort_key(student["ten"]),
                    self._build_vietnamese_sort_key(student["ho"]),
                    student["mssv"],
                )
            )
            
            return {
                "lop_info": lop_info,
                "sinh_vien_list": sinh_vien_list
            }
        
        except Exception as e:
            logger.error(f"Error processing danh sách sinh viên data: {e}")
            return {
                "lop_info": {},
                "sinh_vien_list": []
            }
    
    def format_nam_hoc_hoc_ky_message(self, nam_hoc_hoc_ky_data: Dict[str, Any]) -> str:
        """
        Định dạng dữ liệu năm học - học kỳ thành tin nhắn
        
        Args:
            nam_hoc_hoc_ky_data: Dữ liệu năm học - học kỳ đã được xử lý
            
        Returns:
            Chuỗi tin nhắn đã định dạng
        """
        try:
            nam_hoc_hoc_ky_list = nam_hoc_hoc_ky_data.get("nam_hoc_hoc_ky_list", [])
            timestamp_str = nam_hoc_hoc_ky_data.get("timestamp")

            if not nam_hoc_hoc_ky_list:
                return "📚 *Học Phần*\n\nKhông có dữ liệu năm học - học kỳ."

            message = "📚 *Danh Sách Năm Học - Học Kỳ*\n\n"
            message += "Chọn một hoặc nhiều học kỳ để tìm kiếm học phần.\n\n"
            
            for i, item in enumerate(nam_hoc_hoc_ky_list):
                ma_hoc_ky = item.get("ma_hoc_ky", "N/A")
                ten_hoc_ky = item.get("ten_hoc_ky", "N/A")
                
                message += f"*{i+1}. {ten_hoc_ky}*\n"
                message += f"   - *Mã:* `{ma_hoc_ky}`\n\n"

            if timestamp_str:
                try:
                    ts_utc = datetime.fromisoformat(timestamp_str)
                    ts_local = ts_utc + timedelta(hours=7)
                    message += f"\n_Dữ liệu cập nhật lúc: {ts_local.strftime('%H:%M %d/%m/%Y')}_"
                except (ValueError, TypeError):
                    pass
            
            return message
        
        except Exception as e:
            logger.error(f"Error formatting năm học - học kỳ message: {e}")
            return f"Lỗi định dạng danh sách năm học - học kỳ: {str(e)}"
    
    def format_search_hoc_phan_message(self, search_hoc_phan_data: Dict[str, Any]) -> str:
        """
        Định dạng dữ liệu tìm kiếm học phần thành tin nhắn
        
        Args:
            search_hoc_phan_data: Dữ liệu tìm kiếm học phần đã được xử lý
            
        Returns:
            Chuỗi tin nhắn đã định dạng
        """
        try:
            hoc_phan_list = search_hoc_phan_data.get("hoc_phan_list", [])
            timestamp_str = search_hoc_phan_data.get("timestamp")

            if not hoc_phan_list:
                return "📚 *Kết Quả Tìm Kiếm*\n\nKhông có học phần nào được tìm thấy."
            
            message = "📚 *Kết Quả Tìm Kiếm Học Phần*\n\n"
            
            for i, item in enumerate(hoc_phan_list):
                thong_tin = item.get("json_thong_tin", {})
                ten_mon_hoc = thong_tin.get("ten_mon_hoc", "N/A")
                ma_mon_hoc = thong_tin.get("ma_mon_hoc", "N/A")
                nam_hoc = thong_tin.get("nam_hoc", "N/A")
                hoc_ky = thong_tin.get("hoc_ky", "N/A")
                nhom_hoc = thong_tin.get("nhom_hoc", "N/A")
                so_tc = thong_tin.get("so_tc", "N/A")
                hoc_ky_label = self._format_hoc_ky_label(hoc_ky)
                
                message += f"*{i+1}. {ten_mon_hoc}*\n"
                message += f"   - *Mã HP:* `{ma_mon_hoc}`\n"
                message += f"   - *Học kỳ:* `{nam_hoc} - {hoc_ky_label}`\n"
                message += f"   - *Nhóm:* `{nhom_hoc}` | *Số TC:* `{so_tc}`\n\n"
            
            if timestamp_str:
                try:
                    ts_utc = datetime.fromisoformat(timestamp_str)
                    ts_local = ts_utc + timedelta(hours=7)
                    message += f"\n_Dữ liệu cập nhật lúc: {ts_local.strftime('%H:%M %d/%m/%Y')}_"
                except (ValueError, TypeError):
                    pass

            return message
        
        except Exception as e:
            logger.error(f"Error formatting search học phần message: {e}")
            return f"Lỗi định dạng danh sách học phần: {str(e)}"
    
    def format_hoc_phan_detail_message(self, hoc_phan_data: Dict[str, Any]) -> str:
        """
        Định dạng dữ liệu chi tiết học phần thành tin nhắn
        
        Args:
            hoc_phan_data: Dữ liệu học phần đã được xử lý
            
        Returns:
            Chuỗi tin nhắn đã định dạng
        """
        try:
            thong_tin = hoc_phan_data.get("json_thong_tin", {})
            timestamp_str = hoc_phan_data.get("timestamp")
            ten_mon_hoc = thong_tin.get("ten_mon_hoc", "N/A")
            ma_mon_hoc = thong_tin.get("ma_mon_hoc", "N/A")
            nam_hoc = thong_tin.get("nam_hoc", "N/A")
            hoc_ky = thong_tin.get("hoc_ky", "N/A")
            nhom_hoc = thong_tin.get("nhom_hoc", "N/A")
            so_tc = thong_tin.get("so_tc", "N/A")
            nhom_thuc_hanh = thong_tin.get("nhom_thuc_hanh", "")
            hoc_ky_label = self._format_hoc_ky_label(hoc_ky)
            
            message = f"📚 *Chi Tiết Học Phần*\n\n"
            message += f"*{ten_mon_hoc}*\n"
            message += f"  - *Mã HP:* `{ma_mon_hoc}`\n"
            message += f"  - *Học kỳ:* `{nam_hoc} - {hoc_ky_label}`\n"
            message += f"  - *Nhóm:* `{nhom_hoc}`\n"
            message += f"  - *Số TC:* `{so_tc}`\n"
            if nhom_thuc_hanh:
                message += f"  - *Nhóm TH:* `{nhom_thuc_hanh}`\n"
            
            if timestamp_str:
                try:
                    ts_utc = datetime.fromisoformat(timestamp_str)
                    ts_local = ts_utc + timedelta(hours=7)
                    message += f"\n_Dữ liệu cập nhật lúc: {ts_local.strftime('%H:%M %d/%m/%Y')}_"
                except (ValueError, TypeError):
                    pass

            return message
        
        except Exception as e:
            logger.error(f"Error formatting học phần detail message: {e}")
            return f"Lỗi định dạng chi tiết học phần: {str(e)}"
    
    def format_diem_danh_message(self, diem_danh_data: Dict[str, Any]) -> str:
        """
        Định dạng dữ liệu điểm danh thành tin nhắn
        
        Args:
            diem_danh_data: Dữ liệu điểm danh đã được xử lý
            
        Returns:
            Chuỗi tin nhắn đã định dạng
        """
        try:
            diem_danh_list = diem_danh_data.get("diem_danh_list", [])
            timestamp_str = diem_danh_data.get("timestamp")

            if not diem_danh_list:
                return "📝 *Lịch Sử Điểm Danh*\n\nKhông có dữ liệu điểm danh."
            
            message = "📝 *Lịch Sử Điểm Danh*\n"
            
            total_sessions = len(diem_danh_list)
            present_sessions = sum(1 for item in diem_danh_list if item and item.get("diem_danh") and item.get("diem_danh", {}).get("ket_qua") == "co_mat")
            absent_sessions = sum(1 for item in diem_danh_list if item and item.get("diem_danh") and item.get("diem_danh", {}).get("ket_qua") == "vang_mat")
            
            message += f"\n*Tổng quan:*\n"
            message += f"  - ✅ *Có mặt:* `{present_sessions}/{total_sessions}`\n"
            message += f"  - ❌ *Vắng mặt:* `{absent_sessions}/{total_sessions}`\n"

            message += "\n- - - - - *Chi Tiết* - - - - -\n"

            for item in diem_danh_list:
                if not item:
                    continue
                lich_trinh = item.get("lich_trinh", {})
                diem_danh = item.get("diem_danh") or {}
                
                ngay_hoc = lich_trinh.get("ngay_hoc", "N/A")
                gio_bat_dau = lich_trinh.get("gio_bat_dau", "N/A")
                gio_ket_thuc = lich_trinh.get("gio_ket_thuc", "N/A")
                ma_phong = lich_trinh.get("ma_phong", "N/A")
                
                ket_qua = diem_danh.get("ket_qua", "chua_diem_danh")
                
                if ket_qua == "co_mat":
                    status_icon = "✅"
                    status_text = "Có mặt"
                elif ket_qua == "vang_mat":
                    status_icon = "❌"
                    status_text = "Vắng mặt"
                else:
                    status_icon = "❔"
                    status_text = "Chưa điểm danh"

                message += f"\n*{ngay_hoc}* ({gio_bat_dau} - {gio_ket_thuc})\n"
                message += f"   - *Trạng thái:* {status_icon} {status_text}\n"
                message += f"   - *Phòng:* `{ma_phong}`\n"

                # Lấy thông tin chi tiết từ QR code điểm danh
                chi_tiet_dd = lich_trinh.get("diem_danh") or {}
                chi_tiet_list = chi_tiet_dd.get("chi_tiet", [])
                if chi_tiet_list:
                    qr_data = (chi_tiet_list[0].get("diem_danh_qr_code") or {}).get("data", {})
                    thoi_gian_dd = qr_data.get("time")
                    location = qr_data.get("location", {})
                    dia_diem = location.get("display_name")
                    if thoi_gian_dd:
                        message += f"   - *Thời gian ĐD:* `{thoi_gian_dd}`\n"
                    if dia_diem:
                        message += f"   - *Vị trí:* `{dia_diem}`\n"
            
            if timestamp_str:
                try:
                    ts_utc = datetime.fromisoformat(timestamp_str)
                    ts_local = ts_utc + timedelta(hours=7)
                    message += f"\n\n_Dữ liệu cập nhật lúc: {ts_local.strftime('%H:%M %d/%m/%Y')}_"
                except (ValueError, TypeError):
                    pass

            return message
        
        except Exception as e:
            logger.error(f"Error formatting điểm danh message: {e}", exc_info=True)
            return f"Lỗi định dạng lịch sử điểm danh: {str(e)}"
    
    def generate_danh_sach_sinh_vien_xlsx(self, danh_sach_sinh_vien_data: Dict[str, Any]) -> io.BytesIO:
        """
        Tạo file Excel danh sách sinh viên
        
        Args:
            danh_sach_sinh_vien_data: Dữ liệu danh sách sinh viên đã được xử lý
            
        Returns:
            File Excel dưới dạng BytesIO
        """
        try:
            lop_info = danh_sach_sinh_vien_data.get("lop_info", {})
            sinh_vien_list = danh_sach_sinh_vien_data.get("sinh_vien_list", [])
            
            # Tạo workbook mới
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Danh sách sinh viên"
            
            # Định dạng tiêu đề
            title_font = Font(name='Arial', size=14, bold=True)
            header_font = Font(name='Arial', size=12, bold=True)
            cell_font = Font(name='Arial', size=11)
            header_fill = PatternFill(start_color='CCE5FF', end_color='CCE5FF', fill_type='solid')
            header_alignment = Alignment(horizontal='center', vertical='center')
            cell_alignment = Alignment(horizontal='left', vertical='center')
            stt_alignment = Alignment(horizontal='center', vertical='center')
            
            # Thêm thông tin lớp học phần
            thong_tin = lop_info.get("json_thong_tin", {})
            ten_mon_hoc = thong_tin.get("ten_mon_hoc", "")
            ma_mon_hoc = thong_tin.get("ma_mon_hoc", "")
            nam_hoc = thong_tin.get("nam_hoc", "")
            hoc_ky = thong_tin.get("hoc_ky", "")
            nhom_hoc = thong_tin.get("nhom_hoc", "")
            hoc_ky_label = self._format_hoc_ky_excel_label(hoc_ky)
            
            # Cập nhật merge cells để chứa thêm cột STT
            ws.merge_cells('A1:E1')
            ws['A1'] = f"DANH SÁCH SINH VIÊN LỚP HỌC PHẦN"
            ws['A1'].font = title_font
            ws['A1'].alignment = Alignment(horizontal='center', vertical='center')
            
            ws.merge_cells('A2:E2')
            ws['A2'] = f"{ten_mon_hoc} ({ma_mon_hoc})"
            ws['A2'].font = header_font
            ws['A2'].alignment = Alignment(horizontal='center', vertical='center')
            
            ws.merge_cells('A3:E3')
            ws['A3'] = f"Năm học: {nam_hoc} - Học kỳ: {hoc_ky_label} - Nhóm học: {nhom_hoc}"
            ws['A3'].font = cell_font
            ws['A3'].alignment = Alignment(horizontal='center', vertical='center')
            
            # Thêm tiêu đề bảng (bao gồm cột STT)
            headers = ['STT', 'MSSV', 'Họ', 'Tên', 'Lớp']
            for col_num, header in enumerate(headers, 1):
                cell = ws.cell(row=5, column=col_num, value=header)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = header_alignment
            
            # Thêm dữ liệu sinh viên (bao gồm cột STT)
            for row_num, sinh_vien in enumerate(sinh_vien_list, 6):
                # Thêm số thứ tự
                ws.cell(row=row_num, column=1, value=row_num - 5).font = cell_font
                ws.cell(row=row_num, column=1).alignment = stt_alignment
                
                # Thêm MSSV
                ws.cell(row=row_num, column=2, value=sinh_vien["mssv"]).font = cell_font
                ws.cell(row=row_num, column=2).alignment = cell_alignment
                
                # Thêm Họ
                ws.cell(row=row_num, column=3, value=sinh_vien["ho"]).font = cell_font
                ws.cell(row=row_num, column=3).alignment = cell_alignment
                
                # Thêm Tên
                ws.cell(row=row_num, column=4, value=sinh_vien["ten"]).font = cell_font
                ws.cell(row=row_num, column=4).alignment = cell_alignment
                
                # Thêm Lớp
                ws.cell(row=row_num, column=5, value=sinh_vien["lop"]).font = cell_font
                ws.cell(row=row_num, column=5).alignment = cell_alignment
            
            # Điều chỉnh độ rộng cột (bao gồm cột STT)
            ws.column_dimensions['A'].width = 5   # STT
            ws.column_dimensions['B'].width = 15  # MSSV
            ws.column_dimensions['C'].width = 25  # Họ
            ws.column_dimensions['D'].width = 15  # Tên
            ws.column_dimensions['E'].width = 15  # Lớp
            
            # Lưu file vào BytesIO
            file_stream = io.BytesIO()
            wb.save(file_stream)
            file_stream.seek(0)
            
            return file_stream
        
        except Exception as e:
            logger.error(f"Error generating danh sách sinh viên XLSX: {e}")
            raise e
    
    def get_nam_hoc_hoc_ky_list(self, nam_hoc_hoc_ky_data: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Lấy danh sách năm học - học kỳ để hiển thị trong menu
        
        Args:
            nam_hoc_hoc_ky_data: Dữ liệu năm học - học kỳ đã được xử lý
            
        Returns:
            Danh sách năm học - học kỳ với thông tin hiển thị
        """
        try:
            nam_hoc_hoc_ky_list = nam_hoc_hoc_ky_data.get("nam_hoc_hoc_ky_list", [])
            
            if not nam_hoc_hoc_ky_list:
                return []
            
            result = []
            
            for i, item in enumerate(nam_hoc_hoc_ky_list):
                ma_hoc_ky = item.get("ma_hoc_ky", "")
                ten_hoc_ky = item.get("ten_hoc_ky", "")
                
                result.append({
                    "key": ma_hoc_ky,
                    "name": f"{ten_hoc_ky}",
                    "display": str(i+1)
                })
            
            return result
        
        except Exception as e:
            logger.error(f"Error getting năm học - học kỳ list: {e}")
            return []
    
    def get_hoc_phan_list(self, search_hoc_phan_data: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Lấy danh sách học phần để hiển thị trong menu
        
        Args:
            search_hoc_phan_data: Dữ liệu tìm kiếm học phần đã được xử lý
            
        Returns:
            Danh sách học phần với thông tin hiển thị
        """
        try:
            hoc_phan_list = search_hoc_phan_data.get("hoc_phan_list", [])
            
            if not hoc_phan_list:
                return []
            
            result = []
            
            for i, item in enumerate(hoc_phan_list):
                thong_tin = item.get("json_thong_tin", {})
                ten_mon_hoc = thong_tin.get("ten_mon_hoc", "")
                ma_mon_hoc = thong_tin.get("ma_mon_hoc", "")
                nam_hoc = thong_tin.get("nam_hoc", "")
                hoc_ky = thong_tin.get("hoc_ky", "")
                nhom_hoc = thong_tin.get("nhom_hoc", "")
                key_check = item.get("key_check", "")
                hoc_ky_label = self._format_hoc_ky_label(hoc_ky)
                
                display_name = f"{ten_mon_hoc} ({ma_mon_hoc})"
                if len(display_name) > 40:  # Giới hạn độ dài hiển thị
                    display_name = display_name[:37] + "..."
                
                result.append({
                    "key": key_check,
                    "name": display_name,
                    "full_name": f"{ten_mon_hoc} ({ma_mon_hoc}) - {nam_hoc} - {hoc_ky_label} - NH{nhom_hoc}",
                    "display": str(i+1)
                })
            
            return result
        
        except Exception as e:
            logger.error(f"Error getting học phần list: {e}")
            return []

    # ==================== Command Methods ====================

    async def hoc_phan_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý lệnh /hocphan"""
        user_id = update.effective_user.id

        # Kiểm tra xem người dùng đã đăng nhập chưa
        if not await self.db_manager.is_user_logged_in(user_id):
            await update.message.reply_text("Bạn chưa đăng nhập. Vui lòng /dangnhap để đăng nhập.", reply_to_message_id=update.message.message_id)
            return

        # Lấy danh sách năm học - học kỳ
        result = await self.handle_hoc_phan(user_id)

        if result["success"]:
            # Định dạng dữ liệu năm học - học kỳ thành menu
            message = self.format_nam_hoc_hoc_ky_message(result["data"])

            # Tạo keyboard cho các nút chọn năm học - học kỳ
            nam_hoc_hoc_ky_list = self.get_nam_hoc_hoc_ky_list(result["data"])
            keyboard = []

            # Thêm các nút chọn năm học - học kỳ (tối đa 3 nút mỗi hàng)
            row = []
            for i, nam_hoc_hoc_ky in enumerate(nam_hoc_hoc_ky_list):
                row.append(make_inline_button(nam_hoc_hoc_ky["name"], f"namhoc_{nam_hoc_hoc_ky['key']}", tone=None))
                if len(row) == 3 or i == len(nam_hoc_hoc_ky_list) - 1:
                    keyboard.append(row)
                    row = []

            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                message,
                reply_markup=reply_markup,
                parse_mode="Markdown",
                reply_to_message_id=update.message.message_id
            )
        else:
            await update.message.reply_text(result['message'], reply_to_message_id=update.message.message_id, parse_mode="Markdown")

    # ==================== Callback Methods ====================

    async def hoc_phan_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý callback từ các nút chọn năm học - học kỳ"""
        query = update.callback_query
        user_id = query.from_user.id

        # Lấy callback_data
        callback_data = query.data

        if callback_data.startswith("namhoc_"):
            nam_hoc_key = callback_data[7:]  # Bỏ "namhoc_" prefix

            # Hiển thị thông báo đang xử lý
            await query.answer("Đang tìm kiếm học phần...")

            # Lưu năm học - học kỳ đã chọn vào context
            context.user_data["selected_nam_hoc"] = nam_hoc_key

            # Lấy danh sách năm học - học kỳ
            result = await self.handle_hoc_phan(user_id)

            if result["success"]:
                # Lấy danh sách năm học - học kỳ
                nam_hoc_hoc_ky_list = self.get_nam_hoc_hoc_ky_list(result["data"])

                # Tìm các năm học - học kỳ phù hợp
                selected_nam_hoc_list = []
                for item in nam_hoc_hoc_ky_list:
                    if item["key"] == nam_hoc_key:
                        selected_nam_hoc_list.append(item["key"])
                        break


                if selected_nam_hoc_list:
                    # Tìm kiếm học phần
                    search_result = await self.handle_search_hoc_phan(user_id, selected_nam_hoc_list)

                    if search_result["success"]:
                        # Định dạng dữ liệu học phần thành menu
                        message = self.format_search_hoc_phan_message(search_result["data"])

                        # Tạo keyboard cho các nút chọn học phần
                        hoc_phan_list = self.get_hoc_phan_list(search_result["data"])

                        keyboard = []

                        # Thêm các nút chọn học phần (tối đa 2 nút mỗi hàng)
                        row = []
                        for i, hoc_phan in enumerate(hoc_phan_list):
                            row.append(make_inline_button(hoc_phan["name"], f"hocphan_{hoc_phan['key']}", tone=None))
                            if len(row) == 2 or i == len(hoc_phan_list) - 1:
                                keyboard.append(row)
                                row = []

                        # Thêm nút quay lại
                        keyboard.append([make_inline_button("Quay lại", "hocphan_back", tone="neutral", emoji=None)])

                        reply_markup = InlineKeyboardMarkup(keyboard)

                        await query.edit_message_text(
                            text=message,
                            reply_markup=reply_markup,
                            parse_mode="Markdown"
                        )
                    else:
                        # Thêm menu quay lại khi không tìm thấy học phần
                        keyboard = [
                            [make_inline_button("Quay lại", "hocphan_back", tone="neutral", emoji=None)]
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        await query.edit_message_text(
                            text=f"{search_result['message']}",
                            reply_markup=reply_markup,
                            parse_mode="Markdown"
                        )
                else:
                    await query.edit_message_text("Không tìm thấy năm học - học kỳ được chọn.")
            else:
                await query.edit_message_text(result['message'], parse_mode="Markdown")
        elif callback_data.startswith("hocphan_"):
            # Xử lý khi chọn học phần
            if callback_data == "hocphan_back":
                # Quay lại menu chọn năm học - học kỳ
                result = await self.handle_hoc_phan(user_id)

                if result["success"]:
                    # Định dạng dữ liệu năm học - học kỳ thành menu
                    message = self.format_nam_hoc_hoc_ky_message(result["data"])

                    # Tạo keyboard cho các nút chọn năm học - học kỳ
                    nam_hoc_hoc_ky_list = self.get_nam_hoc_hoc_ky_list(result["data"])
                    keyboard = []

                    # Thêm các nút chọn năm học - học kỳ (tối đa 3 nút mỗi hàng)
                    row = []
                    for i, nam_hoc_hoc_ky in enumerate(nam_hoc_hoc_ky_list):
                        row.append(make_inline_button(nam_hoc_hoc_ky["name"], f"namhoc_{nam_hoc_hoc_ky['key']}", tone=None))
                        if len(row) == 3 or i == len(nam_hoc_hoc_ky_list) - 1:
                            keyboard.append(row)
                            row = []

                    reply_markup = InlineKeyboardMarkup(keyboard)

                    await query.edit_message_text(
                        text=message,
                        reply_markup=reply_markup,
                        parse_mode="Markdown"
                    )
                else:
                    await query.edit_message_text(result['message'], parse_mode="Markdown")
            else:
                # Xem chi tiết học phần
                key_lop_hoc_phan = callback_data.split("hocphan_")[1]

                # Lấy thông tin chi tiết học phần
                # Lấy năm học - học kỳ đã chọn từ context
                selected_nam_hoc = context.user_data.get("selected_nam_hoc")

                if not selected_nam_hoc:
                    # Nếu không có trong context, lấy năm học - học kỳ đầu tiên
                    result = await self.handle_hoc_phan(user_id)
                    if result["success"]:
                        nam_hoc_hoc_ky_list = self.get_nam_hoc_hoc_ky_list(result["data"])
                        if nam_hoc_hoc_ky_list:
                            selected_nam_hoc = nam_hoc_hoc_ky_list[0]["key"]
                        else:
                            logger.error("No nam_hoc_hoc_ky available")
                            await query.edit_message_text("Không có năm học - học kỳ nào để tìm kiếm.")
                            return
                    else:
                        await query.edit_message_text(result['message'], parse_mode="Markdown")
                        return

                # Tìm kiếm học phần với năm học - học kỳ đã chọn
                search_result = await self.handle_search_hoc_phan(user_id, [selected_nam_hoc])

                if search_result["success"]:
                    # Tìm học phần phù hợp
                    hoc_phan_list = search_result["data"].get("hoc_phan_list", [])
                    logger.info(f"Searching in {len(hoc_phan_list)} hoc_phan items")

                    selected_hoc_phan = None

                    for hoc_phan in hoc_phan_list:
                        hocphan_key_check = hoc_phan.get("key_check")
                        if hocphan_key_check == key_lop_hoc_phan:
                            selected_hoc_phan = hoc_phan
                            break

                    if selected_hoc_phan:
                        # Định dạng thông tin chi tiết học phần
                        message = self.format_hoc_phan_detail_message(selected_hoc_phan)

                        # Tạo keyboard cho các chức năng
                        keyboard = [
                            [
                                make_inline_button("Danh sách sinh viên", f"danhsach_{key_lop_hoc_phan}", tone="primary", emoji="📋"),
                                make_inline_button("Điểm danh", f"diemdanh_lop_hoc_phan_{key_lop_hoc_phan}", tone="success", emoji="📝")
                            ],
                            [
                                make_inline_button("Quay lại", "hocphan_back", tone="neutral", emoji=None)
                            ]
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)

                        await query.edit_message_text(
                            text=message,
                            reply_markup=reply_markup,
                            parse_mode="Markdown"
                        )
                    else:
                        await query.edit_message_text("Không tìm thấy học phần được chọn.")
                else:
                    await query.edit_message_text(search_result['message'], parse_mode="Markdown")
        elif callback_data.startswith("danhsach_"):
            # Xử lý khi chọn danh sách sinh viên
            key_lop_hoc_phan = callback_data.split("danhsach_")[1]

            # Hiển thị thông báo đang xử lý
            await query.answer("Đang tải danh sách sinh viên...")

            # Lấy danh sách sinh viên
            result = await self.handle_danh_sach_sinh_vien(user_id, key_lop_hoc_phan)

            if result["success"]:
                # Tạo file Excel
                try:
                    # Chạy tác vụ blocking trong một thread riêng
                    excel_file = await asyncio.to_thread(
                        self.generate_danh_sach_sinh_vien_xlsx,
                        result["data"]
                    )

                    # Gửi file Excel
                    await query.message.reply_document(
                        document=excel_file,
                        filename=f"danh_sach_sinh_vien_{key_lop_hoc_phan}.xlsx",
                        caption="📋 Danh sách sinh viên lớp học phần"
                    )

                    # Xóa tin nhắn menu lúc chọn danh sách sinh viên để giao diện sạch sẽ
                    try:
                        await query.message.delete()
                    except Exception as e:
                        logger.warning(f"Không thể xóa tin nhắn menu: {e}")

                    # Lấy thông tin chi tiết học phần để hiển thị lại
                    selected_nam_hoc = context.user_data.get("selected_nam_hoc")

                    if not selected_nam_hoc:
                        # Nếu không có trong context, lấy năm học - học kỳ đầu tiên
                        result_hoc_phan = await self.handle_hoc_phan(user_id)
                        if result_hoc_phan["success"]:
                            nam_hoc_hoc_ky_list = self.get_nam_hoc_hoc_ky_list(result_hoc_phan["data"])
                            if nam_hoc_hoc_ky_list:
                                selected_nam_hoc = nam_hoc_hoc_ky_list[0]["key"]
                            else:
                                await query.message.reply_text("Không có năm học - học kỳ nào để tìm kiếm.")
                                return
                        else:
                            await query.message.reply_text(result_hoc_phan['message'], parse_mode="Markdown")
                            return

                    # Tìm kiếm học phần với năm học - học kỳ đã chọn
                    search_result = await self.handle_search_hoc_phan(user_id, [selected_nam_hoc])

                    if search_result["success"]:
                        # Tìm học phần phù hợp
                        hoc_phan_list = search_result["data"].get("hoc_phan_list", [])

                        selected_hoc_phan = None

                        for hoc_phan in hoc_phan_list:
                            hocphan_key_check = hoc_phan.get("key_check")
                            if hocphan_key_check == key_lop_hoc_phan:
                                selected_hoc_phan = hoc_phan
                                break

                        if selected_hoc_phan:
                            # Định dạng thông tin chi tiết học phần
                            message = self.format_hoc_phan_detail_message(selected_hoc_phan)

                            # Tạo keyboard cho các chức năng
                            keyboard = [
                                [
                                    make_inline_button("Danh sách sinh viên", f"danhsach_{key_lop_hoc_phan}", tone="primary", emoji="📋"),
                                    make_inline_button("Điểm danh", f"diemdanh_lop_hoc_phan_{key_lop_hoc_phan}", tone="success", emoji="📝")
                                ],
                                [
                                    make_inline_button("Quay lại", "hocphan_back", tone="neutral", emoji=None)
                                ]
                            ]
                            reply_markup = InlineKeyboardMarkup(keyboard)

                            # Gửi tin nhắn mới với menu chi tiết học phần
                            await query.message.reply_text(
                                text=message,
                                reply_markup=reply_markup,
                                parse_mode="Markdown"
                            )
                        else:
                            await query.message.reply_text("Không tìm thấy học phần được chọn.")
                    else:
                        await query.message.reply_text(search_result['message'], parse_mode="Markdown")


                except Exception as e:
                    await query.edit_message_text(f"Lỗi tạo file Excel: {str(e)}")
            else:
                await query.edit_message_text(result['message'], parse_mode="Markdown")
        elif callback_data.startswith("diemdanh_lop_hoc_phan_"):
            # Xử lý khi chọn điểm danh
            key_lop_hoc_phan = callback_data.split("diemdanh_lop_hoc_phan_")[1]

            # Hiển thị thông báo đang xử lý
            await query.answer("Đang tải lịch sử điểm danh...")

            # Lấy lịch sử điểm danh
            result = await self.handle_diem_danh(user_id, key_lop_hoc_phan)

            if result["success"]:
                # Định dạng lịch sử điểm danh
                message = self.format_diem_danh_message(result["data"])

                # Tạo keyboard cho các chức năng
                keyboard = [
                    [
                        make_inline_button("Quay lại", "hocphan_back", tone="neutral", emoji=None)
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await query.edit_message_text(
                    text=message,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text(result['message'], parse_mode="Markdown")
        elif callback_data == "lichthi_back":
            # Xử lý khi quay lại từ lịch thi
            await query.edit_message_text(
                "📅 *Lịch Thi*\n\n"
                "Vui lòng thử lại sau hoặc liên hệ admin nếu vấn đề tiếp tục.",
                parse_mode="Markdown"
            )

    def register_commands(self, application: Application) -> None:
        """Đăng ký command handlers với Application"""
        application.add_handler(CommandHandler("hocphan", self.hoc_phan_command))

    def register_callbacks(self, application: Application) -> None:
        """Đăng ký callback handlers với Application"""
        application.add_handler(CallbackQueryHandler(self.hoc_phan_callback, pattern="^(namhoc_|hocphan_|lichthi_|danhsach_|diemdanh_lop_hoc_phan_)"))
