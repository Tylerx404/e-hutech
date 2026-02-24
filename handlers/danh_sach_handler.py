#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Handler cho lệnh /danhsach
Xử lý hiển thị danh sách tài khoản đã đăng nhập
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, Application, CommandHandler, CallbackQueryHandler
from telegram.error import BadRequest

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

    def format_danhsach_keyboard(self, accounts: list, active_username: str = None) -> InlineKeyboardMarkup:
        """Tạo InlineKeyboard cho danh sách tài khoản"""
        keyboard = []
        for acc in accounts:
            ho_ten = acc.get('ho_ten') or acc.get('username', 'Unknown')
            username = acc.get('username', '')
            keyboard.append([
                InlineKeyboardButton(
                    ho_ten,
                    callback_data=f"switch_account_{username}"
                )
            ])
        return InlineKeyboardMarkup(keyboard)

    async def danhsach_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý lệnh /danhsach - Hiển thị danh sách tài khoản đã đăng nhập"""
        user_id = update.effective_user.id

        accounts = await self.db_manager.get_user_accounts(user_id, order_by_login_time=True)

        if not accounts:
            await update.message.reply_text(
                "Bạn chưa đăng nhập tài khoản nào.",
                reply_to_message_id=update.message.message_id
            )
            return

        # Lấy tài khoản đang active
        active_account = await self.db_manager.get_active_account(user_id)
        active_username = active_account.get('username') if active_account else None

        reply_markup = self.format_danhsach_keyboard(accounts, active_username)

        # Tạo message hiển thị trạng thái tài khoản hiện tại
        message = "📋 *Danh sách tài khoản*\n\n"
        if active_account:
            active_ho_ten = active_account.get('ho_ten') or active_username
            message += f"🔹 *Đang sử dụng:* {active_ho_ten}\n\n"
        message += "Chọn tài khoản để chuyển đổi:"

        await update.message.reply_text(
            message,
            reply_markup=reply_markup,
            parse_mode="Markdown",
            reply_to_message_id=update.message.message_id
        )

    async def danhsach_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý callback từ menu danh sách tài khoản"""
        query = update.callback_query
        user_id = query.from_user.id
        callback_data = query.data

        if callback_data.startswith("switch_account_"):
            username = callback_data[len("switch_account_"):]
            await self.db_manager.set_active_account(user_id, username)
            await self.cache_manager.clear_user_cache(user_id)

            # Refresh menu
            accounts = await self.db_manager.get_user_accounts(user_id, order_by_login_time=True)
            # Lấy tài khoản đang active (sau khi đã chuyển)
            active_account = await self.db_manager.get_active_account(user_id)
            active_username = active_account.get('username') if active_account else None

            if accounts:
                reply_markup = self.format_danhsach_keyboard(accounts, active_username)
                # Tạo message hiển thị trạng thái tài khoản hiện tại
                message = "📋 *Danh sách tài khoản*\n\n"
                if active_account:
                    active_ho_ten = active_account.get('ho_ten') or active_username
                    message += f"🔹 *Đang sử dụng:* {active_ho_ten}\n\n"
                message += "Chọn tài khoản để chuyển đổi:"
                try:
                    await query.edit_message_text(
                        message,
                        reply_markup=reply_markup,
                        parse_mode="Markdown"
                    )
                except BadRequest as e:
                    if "Message is not modified" in str(e):
                        await query.answer(f"Đang sử dụng: {username}")
                    else:
                        raise
                else:
                    await query.answer(f"Đã chuyển sang tài khoản: {username}")

    def register_commands(self, application: Application) -> None:
        """Đăng ký command handlers với Application"""
        application.add_handler(CommandHandler("danhsach", self.danhsach_command))

    def register_callbacks(self, application: Application) -> None:
        """Đăng ký callback handlers với Application"""
        application.add_handler(CallbackQueryHandler(self.danhsach_callback, pattern="^switch_account_"))
