#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Handler cho lệnh /danhsach.

Hiển thị danh sách tài khoản đã đăng nhập, cho phép chuyển đổi account active
bằng callback. Cú pháp callback: `switch_account_<username>`.
"""

import logging
from typing import List, Dict, Any, Optional

from utils.button_style import make_inline_button, build_inline_keyboard
from utils.telegram_api import TelegramAPI, TelegramAPIError
from config.config import Config

logger = logging.getLogger(__name__)


class DanhSachHandler:
    def __init__(self, db_manager, cache_manager, logout_handler, telegram_api: Optional[TelegramAPI] = None):
        self.db_manager = db_manager
        self.cache_manager = cache_manager
        self.logout_handler = logout_handler
        self.config = Config()
        self.telegram = telegram_api or TelegramAPI(self.config)

    def _build_keyboard(self, accounts: List[Dict[str, Any]], active_username: Optional[str]) -> Dict[str, Any]:
        rows = []
        for acc in accounts:
            ho_ten = acc.get("ho_ten") or acc.get("username", "Unknown")
            username = acc.get("username", "")
            tone = "success" if username == active_username else None
            rows.append([make_inline_button(ho_ten, f"switch_account_{username}", tone=tone)])
        return build_inline_keyboard(rows)

    def _format_message(self, active_account: Optional[Dict[str, Any]]) -> str:
        lines = ["📋 *Danh sách tài khoản*"]
        if active_account:
            active_ho_ten = active_account.get("ho_ten") or active_account.get("username", "")
            lines.append("")
            lines.append(f"🔹 *Đang sử dụng:* {active_ho_ten}")
        lines.append("")
        lines.append("Chọn tài khoản để chuyển đổi:")
        return "\n".join(lines)

    async def cmd_danhsach(self, chat_id: int, user_id: int, reply_to_message_id: Optional[int]) -> None:
        accounts = await self.db_manager.get_user_accounts(user_id, order_by_login_time=True)
        if not accounts:
            await self.telegram.send_message(
                chat_id=chat_id,
                text="Bạn chưa đăng nhập tài khoản nào.",
                reply_to_message_id=reply_to_message_id,
            )
            return
        active_account = await self.db_manager.get_active_account(user_id)
        active_username = active_account.get("username") if active_account else None
        await self.telegram.send_message(
            chat_id=chat_id,
            text=self._format_message(active_account),
            reply_markup=self._build_keyboard(accounts, active_username),
            parse_mode="Markdown",
            reply_to_message_id=reply_to_message_id,
        )

    async def cb_switch(self, callback_id: str, chat_id: int, message_id: int,
                       user_id: int, callback_data: str) -> None:
        if not callback_data.startswith("switch_account_"):
            return
        username = callback_data[len("switch_account_"):]

        await self.db_manager.set_active_account(user_id, username)
        await self.cache_manager.clear_user_cache(user_id)

        accounts = await self.db_manager.get_user_accounts(user_id, order_by_login_time=True)
        active_account = await self.db_manager.get_active_account(user_id)
        active_username = active_account.get("username") if active_account else None

        if not accounts:
            await self.telegram.answer_callback_query(
                callback_id, text="Không còn tài khoản nào.", show_alert=True
            )
            return

        try:
            await self.telegram.edit_message_text_plain(
                chat_id=chat_id,
                message_id=message_id,
                text=self._format_message(active_account),
                reply_markup=self._build_keyboard(accounts, active_username),
                parse_mode="Markdown",
            )
            await self.telegram.answer_callback_query(
                callback_id, text=f"Đã chuyển sang tài khoản: {username}"
            )
        except TelegramAPIError as e:
            if "message is not modified" in e.description.lower():
                await self.telegram.answer_callback_query(
                    callback_id, text=f"Đang sử dụng: {username}"
                )
                return
            raise
