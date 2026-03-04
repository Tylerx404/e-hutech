#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Handler xử lý vị trí điểm danh (campus)
"""

import logging
from typing import Dict, Any, Optional, List

from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes, Application, CommandHandler, CallbackQueryHandler
from telegram.error import BadRequest

from config.config import Config
from utils.button_style import make_inline_button

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

    async def _safe_answer_callback(
        self,
        query,
        *,
        text: Optional[str] = None,
        show_alert: bool = False
    ) -> bool:
        """Answer callback query và bỏ qua lỗi hết hạn query."""
        try:
            await query.answer(text=text, show_alert=show_alert)
            return True
        except BadRequest as e:
            error_msg = str(e)
            if "Query is too old" in error_msg or "query id is invalid" in error_msg:
                logger.debug(
                    "Skip callback answer because query expired | user_id=%s callback_data=%s",
                    getattr(query.from_user, "id", "unknown"),
                    getattr(query, "data", "unknown")
                )
                return False
            raise

    async def _safe_edit_message_text(
        self,
        query,
        *,
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        parse_mode: Optional[str] = None
    ) -> bool:
        """Edit callback message và bỏ qua lỗi khi nội dung không thay đổi."""
        try:
            await query.edit_message_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            return True
        except BadRequest as e:
            if "Message is not modified" in str(e):
                logger.debug(
                    "Skip vị trí message edit because content is unchanged | user_id=%s callback_data=%s",
                    getattr(query.from_user, "id", "unknown"),
                    getattr(query, "data", "unknown")
                )
                return False
            raise

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

    def format_vitri_keyboard(self, preferred_campus: Optional[str] = None) -> InlineKeyboardMarkup:
        """
        Tạo InlineKeyboard cho menu vị trí

        Args:
            preferred_campus: Campus đã lưu (nếu có)

        Returns:
            InlineKeyboardMarkup object
        """
        try:
            keyboard = []

            # Thêm các nút chọn campus (tối đa 2 nút mỗi hàng)
            row = []
            for i, campus_name in enumerate(CAMPUS_LOCATIONS.keys()):
                row.append(make_inline_button(campus_name, f"vitri_select_{campus_name}", tone=None, emoji="📍"))
                if len(row) == 2 or i == len(CAMPUS_LOCATIONS) - 1:
                    keyboard.append(row)
                    row = []

            # Thêm nút xóa vị trí nếu có vị trí đã lưu
            if preferred_campus:
                keyboard.append([
                    make_inline_button("Xóa vị trí đã lưu", "vitri_delete", tone="danger")
                ])

            return InlineKeyboardMarkup(keyboard)

        except Exception as e:
            logger.error(f"Error creating vị trí keyboard: {e}")
            return InlineKeyboardMarkup([])

    def get_campus_location(self, campus_name: str) -> Optional[Dict[str, float]]:
        """Lấy vị trí của campus."""
        return CAMPUS_LOCATIONS.get(campus_name)

    def get_all_campuses(self) -> List[str]:
        """Lấy danh sách tất cả campus."""
        return list(CAMPUS_LOCATIONS.keys())

    # ==================== Command Methods ====================

    async def vitri_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý lệnh /vitri"""
        user_id = update.effective_user.id

        # Lấy campus ưu tiên hiện tại
        preferred_campus = await self.get_user_preferred_campus(user_id)

        # Định dạng menu
        message = self.format_vitri_menu(preferred_campus)

        # Tạo keyboard
        reply_markup = self.format_vitri_keyboard(preferred_campus)

        await update.message.reply_text(
            message,
            reply_markup=reply_markup,
            parse_mode="Markdown",
            reply_to_message_id=update.message.message_id
        )

    # ==================== Callback Methods ====================

    async def vitri_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý callback từ các nút chọn vị trí"""
        query = update.callback_query
        user_id = query.from_user.id

        # Lấy callback_data
        callback_data = query.data
        await self._safe_answer_callback(query)

        if callback_data == "vitri_delete":
            # Xóa vị trí đã lưu
            success = await self.delete_user_preferred_campus(user_id)

            if success:
                message = self.format_vitri_menu(None)
                reply_markup = self.format_vitri_keyboard(None)
            else:
                message = "❌ *Lỗi*\n\nKhông thể xóa vị trí. Vui lòng thử lại."
                reply_markup = InlineKeyboardMarkup([])

            await self._safe_edit_message_text(
                query,
                text=message,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )

        elif callback_data.startswith("vitri_select_"):
            # Chọn campus mới
            campus_name = callback_data[13:]  # Bỏ "vitri_select_" prefix

            success = await self.set_user_preferred_campus(user_id, campus_name)

            if success:
                message = self.format_vitri_menu(campus_name)
                reply_markup = self.format_vitri_keyboard(campus_name)
            else:
                message = "❌ *Lỗi*\n\nKhông thể lưu vị trí. Vui lòng thử lại."
                reply_markup = InlineKeyboardMarkup([])

            await self._safe_edit_message_text(
                query,
                text=message,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )

    def register_commands(self, application: Application) -> None:
        """Đăng ký command handlers với Application"""
        application.add_handler(CommandHandler("vitri", self.vitri_command))

    def register_callbacks(self, application: Application) -> None:
        """Đăng ký callback handlers với Application"""
        application.add_handler(CallbackQueryHandler(self.vitri_callback, pattern="^vitri_"))
