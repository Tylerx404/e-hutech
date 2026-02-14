#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Handler xử lý vị trí điểm danh (campus)
"""

import logging
from typing import Dict, Any, Optional, List

from telegram import ReplyKeyboardMarkup, KeyboardButton

from config.config import Config

logger = logging.getLogger(__name__)

# Danh sách các campus mặc định
CAMPUS_LOCATIONS = {
    "Thu Duc Campus": {"lat": 10.8550845, "long": 106.7853143},
    "Sai Gon Campus": {"lat": 10.8021417, "long": 106.7149192},
    "Ung Van Khiem Campus": {"lat": 10.8098001, "long": 106.714906},
    "Hitech Park Campus": {"lat": 10.8408075, "long": 106.8088987}
}


class ViTriHandler:
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.config = Config()

    async def get_user_preferred_campus(self, telegram_user_id: int) -> Optional[str]:
        """Lấy campus ưu tiên của người dùng từ DB."""
        return await self.db_manager.get_user_preferred_campus(telegram_user_id)

    async def set_user_preferred_campus(self, telegram_user_id: int, campus_name: str) -> bool:
        """Lưu campus ưu tiên vào DB."""
        return await self.db_manager.set_user_preferred_campus(telegram_user_id, campus_name)

    async def delete_user_preferred_campus(self, telegram_user_id: int) -> bool:
        """Xóa campus ưu tiên khỏi DB."""
        return await self.db_manager.delete_user_preferred_campus(telegram_user_id)

    def format_vitri_menu(self, preferred_campus: Optional[str] = None) -> str:
        """
        Định dạng tin nhắn menu vị trí

        Args:
            preferred_campus: Campus đã lưu (nếu có)

        Returns:
            Chuỗi tin nhắn đã định dạng
        """
        try:
            message = "📍 *Quản Lý Vị Trí Điểm Danh*\n\n"

            # Hiển thị vị trí hiện tại
            if preferred_campus:
                # Xóa dấu _ ở đầu nếu có (do lỗi dữ liệu cũ) và escape underscores còn lại
                clean_campus = preferred_campus.lstrip('_')
                escaped_campus = clean_campus.replace('_', '\\_')
                message += f"✅ *Vị trí hiện tại:* {escaped_campus}\n\n"
            else:
                message += "❌ *Chưa cài đặt vị trí*\n\n"

            message += "Chọn một campus để lưu làm vị trí mặc định."

            return message

        except Exception as e:
            logger.error(f"Error formatting vị trí menu message: {e}")
            return f"Lỗi định dạng menu: {str(e)}"

    def format_vitri_keyboard(self, preferred_campus: Optional[str] = None) -> List[List[Dict[str, str]]]:
        """
        Tạo keyboard cho menu vị trí

        Args:
            preferred_campus: Campus đã lưu (nếu có)

        Returns:
            Danh sách các hàng nút bấm
        """
        try:
            keyboard = []

            # Thêm các nút chọn campus (tối đa 2 nút mỗi hàng)
            row = []
            for i, campus_name in enumerate(CAMPUS_LOCATIONS.keys()):
                # Thêm emoji nếu là campus đã chọn
                display_name = campus_name
                if campus_name == preferred_campus:
                    display_name = f"✅ {campus_name}"

                row.append({
                    "text": display_name,
                    "callback_data": f"vitri_select_{campus_name}"
                })
                if len(row) == 2 or i == len(CAMPUS_LOCATIONS) - 1:
                    keyboard.append(row)
                    row = []

            # Thêm nút xóa vị trí nếu có vị trí đã lưu
            if preferred_campus:
                keyboard.append([{
                    "text": "🗑️ Xóa vị trí đã lưu",
                    "callback_data": "vitri_delete"
                }])

            return keyboard

        except Exception as e:
            logger.error(f"Error creating vị trí keyboard: {e}")
            return []

    def get_campus_location(self, campus_name: str) -> Optional[Dict[str, float]]:
        """Lấy vị trí của campus."""
        return CAMPUS_LOCATIONS.get(campus_name)

    def get_all_campuses(self) -> List[str]:
        """Lấy danh sách tất cả campus."""
        return list(CAMPUS_LOCATIONS.keys())

    def format_vitri_reply_keyboard(self, preferred_campus: Optional[str] = None) -> ReplyKeyboardMarkup:
        """
        Tạo ReplyKeyboard cho menu vị trí

        Args:
            preferred_campus: Campus đã lưu (nếu có)

        Returns:
            ReplyKeyboardMarkup object
        """
        try:
            keyboard = []
            campuses = list(CAMPUS_LOCATIONS.keys())

            # Chia 2 cột 2 hàng cho 4 campus
            for i in range(0, len(campuses), 2):
                row = [KeyboardButton(campuses[i])]
                if i + 1 < len(campuses):
                    row.append(KeyboardButton(campuses[i + 1]))
                keyboard.append(row)

            # Thêm nút xóa vị trí nếu có vị trí đã lưu (1 cột 1 hàng)
            if preferred_campus:
                keyboard.append([KeyboardButton("🗑️ Xóa vị trí đã lưu")])

            return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

        except Exception as e:
            logger.error(f"Error creating vị trí reply keyboard: {e}")
            return ReplyKeyboardMarkup([], resize_keyboard=True)

    def format_campus_reply_keyboard(self) -> ReplyKeyboardMarkup:
        """
        Tạo ReplyKeyboard cho chọn campus (dùng chung cho diemdanh, diemdanhtatca)

        Returns:
            ReplyKeyboardMarkup object
        """
        try:
            keyboard = []
            campuses = list(CAMPUS_LOCATIONS.keys())

            # Chia 2 cột 2 hàng cho 4 campus
            for i in range(0, len(campuses), 2):
                row = [KeyboardButton(campuses[i])]
                if i + 1 < len(campuses):
                    row.append(KeyboardButton(campuses[i + 1]))
                keyboard.append(row)

            return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

        except Exception as e:
            logger.error(f"Error creating campus reply keyboard: {e}")
            return ReplyKeyboardMarkup([], resize_keyboard=True)
