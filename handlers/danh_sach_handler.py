#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Handler cho lệnh /danhsach
Xử lý hiển thị danh sách tài khoản đã đăng nhập
"""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class DanhSachHandler:
    """Handler cho lệnh /danhsach"""

    def __init__(self, db_manager, cache_manager, logout_handler):
        """
        Khởi tạo DanhSachHandler

        Args:
            db_manager: DatabaseManager instance
            cache_manager: CacheManager instance
            logout_handler: LogoutHandler instance
        """
        self.db_manager = db_manager
        self.cache_manager = cache_manager
        self.logout_handler = logout_handler

    async def danhsach_command(self, update, context: ContextTypes.DEFAULT_TYPE, set_state: bool = True) -> None:
        """Xử lý lệnh /danhsach - Hiển thị danh sách tài khoản đã đăng nhập"""
        user_id = update.effective_user.id

        accounts = await self.db_manager.get_user_accounts(user_id)

        if not accounts:
            await update.message.reply_text("Bạn chưa đăng nhập tài khoản nào.", reply_to_message_id=update.message.message_id)
            return

        # Tạo reply keyboard hiển thị danh sách tài khoản (2 cột)
        keyboard = []
        for i in range(0, len(accounts), 2):
            row = []
            acc = accounts[i]
            ho_ten = acc.get('ho_ten') or acc.get('username', 'Unknown')
            marker = "✅ " if acc.get('is_active') else ""
            row.append(KeyboardButton(f"{marker}{ho_ten}"))

            if i + 1 < len(accounts):
                acc2 = accounts[i + 1]
                ho_ten2 = acc2.get('ho_ten') or acc2.get('username', 'Unknown')
                marker2 = "✅ " if acc2.get('is_active') else ""
                row.append(KeyboardButton(f"{marker2}{ho_ten2}"))

            keyboard.append(row)

        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

        # Set state để biết user đang ở menu danhsach
        if set_state:
            context.user_data["reply_keyboard_state"] = "danhsach"

        await update.message.reply_text(
            "📋 *Danh sách tài khoản*\n\nChọn tài khoản để chuyển đổi:",
            reply_markup=reply_markup,
            parse_mode="Markdown",
            reply_to_message_id=update.message.message_id
        )

    async def danhsach_callback(self, update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý callback từ menu danh sách tài khoản"""
        query = update.callback_query
        user_id = query.from_user.id
        callback_data = query.data

        if callback_data.startswith("switch_account_"):
            username = callback_data.split("_")[2]
            await self.db_manager.set_active_account(user_id, username)
            await self.cache_manager.clear_user_cache(user_id)
            await query.answer(f"Đã chuyển sang tài khoản: {username}")

            # Refresh menu
            await self._refresh_danhsach_menu(query, context)

    async def _refresh_danhsach_menu(self, query, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Refresh menu danh sách tài khoản"""
        user_id = query.from_user.id
        accounts = await self.db_manager.get_user_accounts(user_id)

        if not accounts:
            await query.edit_message_text("Bạn chưa đăng nhập tài khoản nào.")
            return

        # Tạo menu hiển thị danh sách tài khoản
        keyboard = []
        for acc in accounts:
            ho_ten = acc.get('ho_ten') or acc.get('username', 'Unknown')
            marker = "✅ " if acc.get('is_active') else ""
            keyboard.append([
                InlineKeyboardButton(
                    f"{marker}{ho_ten}",
                    callback_data=f"switch_account_{acc['username']}"
                )
            ])

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "📋 *Danh sách tài khoản*\n\nChọn tài khoản để chuyển đổi:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
