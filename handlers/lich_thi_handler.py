#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Handler xử lý lịch thi từ hệ thống HUTECH
"""

import json
import logging
import aiohttp
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import ContextTypes, Application, CommandHandler

from config.config import Config

logger = logging.getLogger(__name__)

class LichThiHandler:
    def __init__(self, db_manager, cache_manager):
        self.db_manager = db_manager
        self.cache_manager = cache_manager
        self.config = Config()
    
    async def handle_lich_thi(self, telegram_user_id: int) -> Dict[str, Any]:
        """
        Xử lý lấy lịch thi của người dùng
        
        Args:
            telegram_user_id: ID của người dùng trên Telegram
            
        Returns:
            Dict chứa kết quả và dữ liệu lịch thi
        """
        try:
            cache_key = f"lichthi:{telegram_user_id}"

            # 1. Kiểm tra cache
            cached_result = await self.cache_manager.get(cache_key)
            if cached_result:
                lich_thi_data = cached_result.get("data")
                timestamp = cached_result.get("timestamp")

                processed_data = self._process_lich_thi_data(lich_thi_data)
                processed_data["timestamp"] = timestamp

                return {
                    "success": True,
                    "message": "Lấy lịch thi thành công",
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
            
            response_data = await self._call_lich_thi_api(token)
            
            # 3. Lưu vào cache
            if response_data and isinstance(response_data, list):
                await self.cache_manager.set(cache_key, response_data, ttl=86400) # Cache trong 24 giờ
            
            # Kiểm tra kết quả
            if response_data and isinstance(response_data, list):
                # Xử lý dữ liệu lịch thi
                processed_data = self._process_lich_thi_data(response_data)
                
                # Lấy timestamp từ cache manager để đồng bộ
                cached_data = await self.cache_manager.get(cache_key)
                if cached_data:
                    processed_data["timestamp"] = cached_data.get("timestamp")
                else:
                    processed_data["timestamp"] = datetime.utcnow().isoformat()
                
                return {
                    "success": True,
                    "message": "Lấy lịch thi thành công (dữ liệu mới)",
                    "data": processed_data
                }
            else:
                return {
                    "success": True,
                    "message": "📅 *Lịch Thi*\n\nKhông có lịch thi nào được tìm thấy.",
                    "data": {
                        "hocky_data": {},
                        "timestamp": datetime.utcnow().isoformat()
                    }
                }
        
        except Exception as e:
            logger.error(f"Lịch thi error for user {telegram_user_id}: {e}")
            return {
                "success": False,
                "message": f"🚫 *Lỗi*\n\nĐã xảy ra lỗi khi lấy lịch thi: {str(e)}",
                "data": None,
                "show_back_button": True
            }
    
    async def _call_lich_thi_api(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Gọi API lịch thi của HUTECH
        
        Args:
            token: Token xác thực
            
        Returns:
            Response data từ API hoặc None nếu có lỗi
        """
        try:
            url = f"{self.config.HUTECH_API_BASE_URL}{self.config.HUTECH_LICHTHI_ENDPOINT}"
            
            # Tạo headers riêng cho API lịch thi
            headers = self.config.HUTECH_MOBILE_HEADERS.copy()
            headers["authorization"] = f"JWT {token}"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=headers,
                    json={}  # Request body rỗng theo tài liệu
                ) as response:
                    if response.status == 201:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        logger.error(f"Lịch thi API error: {response.status} - {error_text}")
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
    
    def _process_lich_thi_data(self, lich_thi_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Xử lý dữ liệu lịch thi
        
        Args:
            lich_thi_data: Dữ liệu lịch thi thô từ API
            
        Returns:
            Dữ liệu đã được xử lý
        """
        try:
            # Nhóm lịch thi theo học kỳ
            hocky_data = {}
            
            for hocky in lich_thi_data:
                if "nam_hoc_hoc_ky" in hocky and "lich_thi" in hocky:
                    hocky_key = hocky["nam_hoc_hoc_ky"]
                    hocky_name = hocky.get("nam_hoc_hoc_ky_name", "")
                    lich_thi_list = hocky.get("lich_thi", [])
                    
                    # Sắp xếp lịch thi theo ngày thi
                    lich_thi_list.sort(key=lambda x: x.get("ngay_thi", ""))
                    
                    hocky_data[hocky_key] = {
                        "hocky_name": hocky_name,
                        "lich_thi": lich_thi_list
                    }
            
            return {
                "hocky_data": hocky_data
            }
        
        except Exception as e:
            logger.error(f"Error processing lịch thi data: {e}")
            return {
                "hocky_data": {}
            }
    
    def format_lich_thi_message(self, lich_thi_data: Dict[str, Any]) -> str:
        """
        Định dạng dữ liệu lịch thi thành tin nhắn
        
        Args:
            lich_thi_data: Dữ liệu lịch thi đã được xử lý
            
        Returns:
            Chuỗi tin nhắn đã định dạng
        """
        try:
            hocky_data = lich_thi_data.get("hocky_data", {})
            timestamp_str = lich_thi_data.get("timestamp")

            if not hocky_data:
                message = "📅 *Lịch Thi*\n\nKhông có lịch thi nào được tìm thấy."
                if timestamp_str:
                    try:
                        ts_utc = datetime.fromisoformat(timestamp_str)
                        ts_local = ts_utc + timedelta(hours=7)
                        message += f"\n\n_Dữ liệu cập nhật lúc: {ts_local.strftime('%H:%M %d/%m/%Y')}_"
                    except (ValueError, TypeError):
                        pass
                return message

            message = "📅 *Lịch Thi Sắp Tới*\n"
            
            sorted_hocky_keys = sorted(hocky_data.keys(), reverse=True)

            for hocky_key in sorted_hocky_keys:
                data = hocky_data[hocky_key]
                hocky_name = data.get("hocky_name", "N/A")
                lich_thi_list = data.get("lich_thi", [])
                
                if not lich_thi_list:
                    continue

                message += f"\n\n- - - - - *{hocky_name.upper()}* - - - - -\n"
                
                for mon_thi in lich_thi_list:
                    ten_hp = mon_thi.get("ten_hp", "N/A")
                    ma_hp = mon_thi.get("ma_hp", "N/A")
                    ngay_thi = mon_thi.get("ngay_thi", "N/A")
                    gio_thi = mon_thi.get("gio_thi", "N/A")
                    phong_thi = mon_thi.get("phong_thi", "N/A")
                    hinh_thuc_thi = mon_thi.get("hinh_thuc_thi", "N/A")
                    so_phut = mon_thi.get("so_phut", "N/A")
                    
                    try:
                        ngay_thi_dt = datetime.strptime(ngay_thi, "%Y-%m-%d")
                        ngay_thi_str = ngay_thi_dt.strftime("%d/%m/%Y")
                    except ValueError:
                        ngay_thi_str = ngay_thi
                    
                    message += f"\n📚 *{ten_hp}*\n"
                    message += f"   - *Mã HP:* `{ma_hp}`\n"
                    message += f"   - *Ngày thi:* {ngay_thi_str}\n"
                    message += f"   - *Giờ thi:* {gio_thi}\n"
                    message += f"   - *Phòng thi:* `{phong_thi}`\n"
                    message += f"   - *Hình thức:* {hinh_thuc_thi}\n"
                    message += f"   - *Thời lượng:* {so_phut} phút\n"

            if timestamp_str:
                try:
                    ts_utc = datetime.fromisoformat(timestamp_str)
                    ts_local = ts_utc + timedelta(hours=7)
                    message += f"\n\n_Dữ liệu cập nhật lúc: {ts_local.strftime('%H:%M %d/%m/%Y')}_"
                except (ValueError, TypeError):
                    pass
            
            return message
        
        except Exception as e:
            logger.error(f"Error formatting lịch thi message: {e}")
            return f"Lỗi định dạng lịch thi: {str(e)}"

    # ==================== Command Methods ====================

    async def lichthi_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý lệnh /lichthi"""
        user_id = update.effective_user.id

        # Kiểm tra xem người dùng đã đăng nhập chưa
        if not await self.db_manager.is_user_logged_in(user_id):
            await update.message.reply_text("Bạn chưa đăng nhập. Vui lòng /dangnhap để đăng nhập.", reply_to_message_id=update.message.message_id)
            return

        # Lấy lịch thi
        result = await self.handle_lich_thi(user_id)

        if result["success"]:
            # Định dạng dữ liệu lịch thi
            message = self.format_lich_thi_message(result["data"])

            await update.message.reply_text(
                message,
                parse_mode="Markdown",
                reply_to_message_id=update.message.message_id
            )
        else:
            await update.message.reply_text(f"Không thể lấy lịch thi: {result.get('message', 'Lỗi không xác định')}", reply_to_message_id=update.message.message_id, parse_mode="Markdown")

    def register_commands(self, application: Application) -> None:
        """Đăng ký command handlers với Application"""
        application.add_handler(CommandHandler("lichthi", self.lichthi_command))