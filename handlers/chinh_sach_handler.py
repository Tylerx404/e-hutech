#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Handler chính sách bảo mật + guard chấp nhận.

Cú pháp callback: `consent_accept` / `consent_decline`.
Hàm `consent_required(user_id)` trả về True nếu user chưa chấp nhận.
"""

import logging
from typing import Optional

from utils.button_style import make_inline_button, build_inline_keyboard
from utils.telegram_api import TelegramAPI
from config.config import Config

logger = logging.getLogger(__name__)

ALLOWED_COMMANDS_WITHOUT_CONSENT = {"start", "trogiup", "chinhsach"}


class ChinhSachHandler:
    def __init__(self, db_manager, cache_manager, telegram_api: Optional[TelegramAPI] = None):
        self.db_manager = db_manager
        self.cache_manager = cache_manager
        self.config = Config()
        self.telegram = telegram_api or TelegramAPI(self.config)

    # ==================== Helpers ====================

    @staticmethod
    def extract_command_name(message_text: str) -> str:
        if not message_text or not message_text.startswith("/"):
            return ""
        first = message_text.split()[0]
        command = first[1:]
        if "@" in command:
            command = command.split("@")[0]
        return command.lower()

    async def has_user_consented(self, user_id: int) -> bool:
        return await self.db_manager.has_accepted_policy(user_id)

    # ==================== Public API ====================

    def get_policy_message(self) -> str:
        return (
            "🔐 <b>Chính sách bảo mật & điều khoản sử dụng</b>\n\n"
            "Khi sử dụng bot này, bạn xác nhận và đồng ý:\n"
            "<blockquote>"
            "1. Bot sẽ lưu trữ thông tin tài khoản để cung cấp tính năng.\n"
            "2. Dữ liệu được lưu trên hệ thống máy chủ và có thể tồn tại rủi ro bảo mật ngoài ý muốn.\n"
            "3. Chủ bot không chịu trách nhiệm cho các thiệt hại phát sinh do rò rỉ dữ liệu, truy cập trái phép hoặc sự cố từ bên thứ ba.\n"
            "4. Bạn tự chịu trách nhiệm với quyết định cung cấp thông tin tài khoản cho bot."
            "</blockquote>\n\n"
            "Nhấn nút bên dưới để tiếp tục."
        )

    def get_policy_keyboard(self, has_consented: bool) -> dict:
        if has_consented:
            rows = [[make_inline_button("Từ chối", "consent_decline", tone="danger")]]
        else:
            rows = [[
                make_inline_button("Chấp nhận", "consent_accept", tone="success"),
                make_inline_button("Từ chối", "consent_decline", tone="danger"),
            ]]
        return build_inline_keyboard(rows)

    async def cmd_chinhsach(self, chat_id: int, user_id: int, reply_to_message_id: Optional[int]) -> None:
        has_consented = await self.has_user_consented(user_id)
        await self.telegram.send_message(
            chat_id=chat_id,
            text=self.get_policy_message(),
            reply_markup=self.get_policy_keyboard(has_consented),
            parse_mode="HTML",
            reply_to_message_id=reply_to_message_id,
        )

    async def cb_consent(self, callback_id: str, chat_id: int, message_id: int,
                        user_id: int, callback_data: str) -> None:
        await self.telegram.answer_callback_query(callback_id)

        if callback_data == "consent_accept":
            await self.db_manager.set_policy_consent(user_id, True)
            new_text = (
                "✅ Bạn đã chấp nhận chính sách.\n\n"
                "Bây giờ bạn có thể sử dụng các lệnh chính như /dangnhap, /tkb, /diemdanh..."
            )
        elif callback_data == "consent_decline":
            await self.db_manager.set_policy_consent(user_id, False)
            await self.db_manager.delete_all_accounts(user_id)
            await self.cache_manager.clear_user_cache(user_id)
            new_text = (
                "❌ Bạn đã từ chối chính sách.\n"
                "Toàn bộ dữ liệu tài khoản đã được xóa khỏi hệ thống.\n\n"
                "Nếu muốn sử dụng lại bot, hãy dùng /chinhsach để chấp nhận."
            )
        else:
            return

        try:
            await self.telegram.edit_message_text_plain(
                chat_id=chat_id, message_id=message_id, text=new_text
            )
        except Exception as e:
            logger.debug("Không thể edit consent message: %s", e)

    # ==================== Guard ====================

    async def check_command_guard(self, user_id: int, command_name: str) -> bool:
        """
        Trả về True nếu command bị chặn (cần gửi policy prompt trước).
        """
        if not command_name or command_name in ALLOWED_COMMANDS_WITHOUT_CONSENT:
            return False
        return not await self.has_user_consented(user_id)

    async def check_callback_guard(self, user_id: int, callback_data: str) -> bool:
        """
        Trả về True nếu callback bị chặn.
        """
        if callback_data.startswith("consent_"):
            return False
        return not await self.has_user_consented(user_id)
