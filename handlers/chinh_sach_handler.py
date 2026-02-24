#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Handler xử lý chính sách bảo mật và trạng thái chấp nhận của người dùng
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import (
    ContextTypes,
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ApplicationHandlerStop,
    filters,
)


ALLOWED_COMMANDS_WITHOUT_CONSENT = {"start", "trogiup", "chinhsach"}


class ChinhSachHandler:
    """Handler cho lệnh /chinhsach và guard chấp nhận chính sách."""

    def __init__(self, db_manager, cache_manager):
        self.db_manager = db_manager
        self.cache_manager = cache_manager

    @staticmethod
    def extract_command_name(message_text: str) -> str:
        """Tách tên command từ text Telegram command."""
        if not message_text or not message_text.startswith("/"):
            return ""
        first = message_text.split()[0]
        command = first[1:]
        if "@" in command:
            command = command.split("@")[0]
        return command.lower()

    def get_policy_message(self) -> str:
        """Nội dung chính sách bảo mật và điều khoản sử dụng."""
        return (
            "🔐 <b>Chính sách bảo mật & điều khoản sử dụng</b>\n\n"
            "<blockquote>"
            "Khi sử dụng bot này, bạn xác nhận và đồng ý:\n"
            "1. Bot có thể lưu trữ thông tin tài khoản để cung cấp tính năng.\n"
            "2. Dữ liệu được lưu trên hệ thống máy chủ và có thể tồn tại rủi ro bảo mật ngoài ý muốn.\n"
            "3. Chủ bot không chịu trách nhiệm cho các thiệt hại phát sinh do rò rỉ dữ liệu, truy cập trái phép hoặc sự cố từ bên thứ ba.\n"
            "4. Bạn tự chịu trách nhiệm với quyết định cung cấp thông tin tài khoản cho bot.\n"
            "5. Nếu không đồng ý, hãy chọn Từ chối."
            "</blockquote>\n\n"
            "Nhấn nút bên dưới để tiếp tục."
        )

    def get_policy_keyboard(self) -> InlineKeyboardMarkup:
        """Tạo keyboard chấp nhận/từ chối chính sách."""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Chấp nhận", callback_data="consent_accept")],
            [InlineKeyboardButton("❌ Từ chối", callback_data="consent_decline")],
        ])

    async def send_policy_prompt(self, update: Update) -> None:
        """Hiển thị thông báo chính sách cùng menu chấp nhận/từ chối."""
        policy_message = self.get_policy_message()
        reply_markup = self.get_policy_keyboard()

        if update.message:
            await update.message.reply_text(policy_message, reply_markup=reply_markup, parse_mode="HTML")
            return

        if update.callback_query and update.callback_query.message:
            await update.callback_query.message.reply_text(policy_message, reply_markup=reply_markup, parse_mode="HTML")
            return

        if update.effective_chat:
            await update.effective_chat.send_message(policy_message, reply_markup=reply_markup, parse_mode="HTML")

    async def has_user_consented(self, user_id: int) -> bool:
        """Kiểm tra trạng thái đã chấp nhận chính sách của người dùng."""
        return await self.db_manager.has_accepted_policy(user_id)

    async def chinhsach_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Hiển thị chính sách để người dùng chấp nhận hoặc từ chối."""
        await self.send_policy_prompt(update)

    async def chinhsach_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý callback chấp nhận/từ chối chính sách."""
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        callback_data = query.data or ""

        if callback_data == "consent_accept":
            await self.db_manager.set_policy_consent(user_id, True)
            message = (
                "✅ Bạn đã chấp nhận chính sách.\n\n"
                "Bây giờ bạn có thể sử dụng các lệnh chính như /dangnhap, /tkb, /diemdanh..."
            )
        elif callback_data == "consent_decline":
            await self.db_manager.set_policy_consent(user_id, False)
            await self.db_manager.delete_all_accounts(user_id)
            await self.cache_manager.clear_user_cache(user_id)
            message = (
                "❌ Bạn đã từ chối chính sách.\n"
                "Toàn bộ dữ liệu tài khoản đã được xóa khỏi hệ thống.\n\n"
                "Nếu muốn sử dụng lại bot, hãy dùng /chinhsach để chấp nhận."
            )
        else:
            return

        try:
            await query.edit_message_text(message)
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                raise

    async def consent_command_guard(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Chặn command nếu người dùng chưa chấp nhận chính sách."""
        if not update.message or not update.message.text:
            return

        command_name = self.extract_command_name(update.message.text)
        if not command_name or command_name in ALLOWED_COMMANDS_WITHOUT_CONSENT:
            return

        user_id = update.effective_user.id
        if await self.db_manager.has_accepted_policy(user_id):
            return

        await update.message.reply_text(
            "Bạn cần chấp nhận chính sách bảo mật trước khi dùng lệnh này.",
            reply_to_message_id=update.message.message_id
        )
        await self.send_policy_prompt(update)
        raise ApplicationHandlerStop

    async def consent_callback_guard(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Chặn callback chức năng nếu người dùng chưa chấp nhận chính sách."""
        query = update.callback_query
        if not query:
            return

        callback_data = query.data or ""
        if callback_data.startswith("consent_"):
            return

        user_id = query.from_user.id
        if await self.db_manager.has_accepted_policy(user_id):
            return

        await query.answer("Bạn cần chấp nhận chính sách trước khi sử dụng bot.", show_alert=True)
        await self.send_policy_prompt(update)
        raise ApplicationHandlerStop

    def register_commands(self, application: Application, group: int = -2) -> None:
        """Đăng ký command /chinhsach."""
        application.add_handler(CommandHandler("chinhsach", self.chinhsach_command), group=group)

    def register_callbacks(self, application: Application, group: int = -2) -> None:
        """Đăng ký callback chấp nhận/từ chối."""
        application.add_handler(CallbackQueryHandler(self.chinhsach_callback, pattern="^consent_"), group=group)

    def register_guards(self, application: Application, group: int = -1) -> None:
        """Đăng ký guard chặn command/callback khi chưa chấp nhận chính sách."""
        application.add_handler(MessageHandler(filters.COMMAND, self.consent_command_guard), group=group)
        application.add_handler(CallbackQueryHandler(self.consent_callback_guard), group=group)
