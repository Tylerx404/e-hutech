#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Handler điểm danh cho tài khoản đang active.

Luồng `/diemdanh`:
1. Chọn campus (hoặc dùng campus đã lưu).
2. Nhập mã số điểm danh `CODE_LENGTH` chữ số (mặc định 4).
3. Gọi API HUTECH submit điểm danh với GPS của campus.

UI dùng Rich Message (Bot API 10.1): mỗi message hiển thị `<tg-map>`
preview vị trí GPS của campus đã chọn. Khi nhập từng số / submit, message
được edit để cập nhật map + keypad.

State tạm per user (lưu trong cache):
    feature: "diemdanh"
    campus: tên campus đã chọn
    input: chuỗi số đã nhập

Cú pháp callback:
    diemdanh_campus_<campus>  - chọn campus
    num_<digit>               - nhập 1 số
    num_exit                  - thoát
    num_delete                - xóa 1 số
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

import aiohttp
from datetime import datetime, timedelta

from config.config import Config
from utils.button_style import make_inline_button, build_inline_keyboard
from utils.rich_message import (
    escape_html,
    join_blocks,
    p,
    p_html,
    section_heading,
)
from utils.state_store import StateStore
from utils.telegram_api import TelegramAPI, TelegramAPIError
from handlers.vi_tri_handler import CAMPUS_LOCATIONS, build_campus_map_block

logger = logging.getLogger(__name__)

# Số chữ số cần nhập cho mã điểm danh
CODE_LENGTH = 4


class DiemDanhHandler:
    """Handler cho `/diemdanh` — điểm danh tài khoản active."""

    def __init__(self, db_manager, cache_manager, telegram_api: Optional[TelegramAPI] = None):
        self.db_manager = db_manager
        self.cache_manager = cache_manager
        self.config = Config()
        self.telegram = telegram_api or TelegramAPI(self.config)
        self.state = StateStore(self.cache_manager)

    # ==================== Command ====================

    async def cmd_diemdanh(self, chat_id: int, user_id: int, reply_to_message_id: Optional[int]) -> None:
        if not await self.db_manager.is_user_logged_in(user_id):
            await self.telegram.send_message(
                chat_id=chat_id,
                text="Bạn chưa đăng nhập. Vui lòng /dangnhap để đăng nhập.",
                reply_to_message_id=reply_to_message_id,
            )
            return

        preferred = await self.db_manager.get_user_preferred_campus(user_id)
        if preferred:
            await self._start_numeric_input(chat_id, user_id, preferred, reply_to_message_id)
        else:
            await self._show_campus_menu(chat_id, reply_to_message_id)

    # ==================== Callbacks ====================

    async def cb_campus(self, callback_id: str, chat_id: int, message_id: int,
                       user_id: int, callback_data: str) -> None:
        if not callback_data.startswith("diemdanh_campus_"):
            return
        campus_name = callback_data[len("diemdanh_campus_"):]
        await self.state.set_state(user_id, {
            "feature": "diemdanh",
            "campus": campus_name,
            "input": "",
        })
        await self.telegram.answer_callback_query(
            callback_id, text=f"Bạn đang chọn: {campus_name}"
        )
        await self._render_numeric(chat_id, message_id, user_id, edit=True)

    async def cb_numeric(self, callback_id: str, chat_id: int, message_id: int,
                        user_id: int, callback_data: str) -> None:
        # Phải ở trong state diemdanh mới xử lý
        st = await self.state.get_state(user_id)
        if st.get("feature") != "diemdanh":
            await self.telegram.answer_callback_query(callback_id)
            return
        campus = st.get("campus", "")
        current = st.get("input", "")

        if callback_data == "num_exit":
            await self.state.clear_state(user_id)
            try:
                await self.telegram.edit_message_text_rich(
                    chat_id=chat_id,
                    message_id=message_id,
                    html=self._exit_rich_html(),
                )
            except TelegramAPIError as e:
                if "message is not modified" not in e.description.lower():
                    raise
            return
        if callback_data == "num_delete":
            current = current[:-1]
        elif callback_data.startswith("num_"):
            num = callback_data[len("num_"):]
            if len(current) < CODE_LENGTH:
                current += num
        else:
            return

        await self.state.set_state(user_id, {**st, "input": current})

        if len(current) == CODE_LENGTH:
            await self._do_submit(chat_id, message_id, user_id, campus, current)
        else:
            await self._render_numeric(chat_id, message_id, user_id, edit=True)

    # ==================== Internal ====================

    async def _show_campus_menu(self, chat_id: int, reply_to_message_id: Optional[int]) -> None:
        html = join_blocks([
            section_heading("📍", "Chọn Vị Trí Điểm Danh"),
            p("Chọn campus để bắt đầu điểm danh."),
            p("<i>💡 Tip: Dùng /vitri để lưu vị trí mặc định và bỏ qua bước này.</i>"),
        ])
        rows: List[List[Dict[str, Any]]] = []
        row: List[Dict[str, Any]] = []
        keys = list(CAMPUS_LOCATIONS.keys())
        for i, name in enumerate(keys):
            row.append(make_inline_button(name, f"diemdanh_campus_{name}", tone=None, emoji="📍"))
            if len(row) == 2 or i == len(keys) - 1:
                rows.append(row)
                row = []
        await self.telegram.send_rich_message(
            chat_id=chat_id,
            html=html,
            reply_markup=build_inline_keyboard(rows),
            reply_to_message_id=reply_to_message_id,
        )

    async def _start_numeric_input(self, chat_id: int, user_id: int, campus_name: str,
                                    reply_to_message_id: Optional[int]) -> None:
        await self.state.set_state(user_id, {
            "feature": "diemdanh",
            "campus": campus_name,
            "input": "",
        })
        await self.telegram.send_rich_message(
            chat_id=chat_id,
            html=self._numeric_rich_html(campus_name, ""),
            reply_markup=build_inline_keyboard(self._numeric_keyboard_rows()),
            reply_to_message_id=reply_to_message_id,
        )

    async def _render_numeric(self, chat_id: int, message_id: int, user_id: int, edit: bool = True) -> None:
        st = await self.state.get_state(user_id)
        campus = st.get("campus", "")
        current = st.get("input", "")
        html = self._numeric_rich_html(campus, current)
        if edit:
            try:
                await self.telegram.edit_message_text_rich(
                    chat_id=chat_id,
                    message_id=message_id,
                    html=html,
                    reply_markup=build_inline_keyboard(self._numeric_keyboard_rows()),
                )
            except TelegramAPIError as e:
                if "message is not modified" not in e.description.lower():
                    raise

    @staticmethod
    def _code_display(current: str) -> str:
        return "".join((current[i] + " ") if i < len(current) else "▫️" for i in range(CODE_LENGTH))

    @classmethod
    def _numeric_rich_html(cls, campus: str, current: str) -> str:
        blocks: List[str] = [
            section_heading("📍", f"Điểm Danh Tại {escape_html(campus)}"),
        ]
        map_block = build_campus_map_block(campus)
        if map_block:
            blocks.append(map_block)
        blocks.append(p_html(f"<b>Nhập mã điểm danh:</b> {cls._code_display(current)}"))
        return join_blocks(blocks)

    @staticmethod
    def _exit_rich_html() -> str:
        return join_blocks([
            section_heading("❎", "Đã thoát lệnh"),
            p("Dùng /diemdanh để bắt đầu lại."),
        ])

    @staticmethod
    def _numeric_keyboard_rows() -> List[List[Dict[str, Any]]]:
        return [
            [
                make_inline_button("1", "num_1", tone=None),
                make_inline_button("2", "num_2", tone=None),
                make_inline_button("3", "num_3", tone=None),
            ],
            [
                make_inline_button("4", "num_4", tone=None),
                make_inline_button("5", "num_5", tone=None),
                make_inline_button("6", "num_6", tone=None),
            ],
            [
                make_inline_button("7", "num_7", tone=None),
                make_inline_button("8", "num_8", tone=None),
                make_inline_button("9", "num_9", tone=None),
            ],
            [
                make_inline_button("Thoát", "num_exit", tone="danger"),
                make_inline_button("0", "num_0", tone=None),
                make_inline_button("Xoá", "num_delete", tone="warning"),
            ],
        ]

    async def _do_submit(self, chat_id: int, message_id: int, user_id: int,
                         campus_name: str, code: str) -> None:
        # Hiển thị "Đang điểm danh..." ngay khi nhập đủ (giữ map + keypad)
        try:
            await self.telegram.edit_message_text_rich(
                chat_id=chat_id,
                message_id=message_id,
                html=self._submitting_rich_html(campus_name, code),
            )
        except TelegramAPIError as e:
            if "message is not modified" not in e.description.lower():
                raise

        result = await self.handle_submit_diem_danh(user_id, code, campus_name)
        await self.state.clear_state(user_id)

        result_html = self._result_rich_html(campus_name, result)
        try:
            await self.telegram.edit_message_text_rich(
                chat_id=chat_id,
                message_id=message_id,
                html=result_html,
            )
        except TelegramAPIError as e:
            if "message is not modified" not in e.description.lower():
                # Fallback: gửi text thường nếu rich không khả thi
                await self.telegram.send_message(
                    chat_id=chat_id, text=result["message"], parse_mode="HTML"
                )

    @classmethod
    def _submitting_rich_html(cls, campus: str, code: str) -> str:
        blocks: List[str] = [
            section_heading("⏳", f"Đang điểm danh tại {escape_html(campus)}"),
        ]
        map_block = build_campus_map_block(campus)
        if map_block:
            blocks.append(map_block)
        blocks.append(p_html(f"<b>Mã đã nhập:</b> {cls._code_display(code)}"))
        blocks.append(p("Vui lòng chờ trong giây lát..."))
        return join_blocks(blocks)

    @classmethod
    def _result_rich_html(cls, campus: str, result: Dict[str, Any]) -> str:
        ok = bool(result.get("success"))
        title = "✅ Điểm danh thành công" if ok else "❌ Điểm danh thất bại"
        blocks: List[str] = [
            section_heading("📍" if ok else "⚠️", f"{title} - {escape_html(campus)}"),
        ]
        map_block = build_campus_map_block(campus)
        if map_block:
            blocks.append(map_block)
        blocks.append(p(escape_html(result.get("message", ""))))
        return join_blocks(blocks)

    # ==================== HUTECH API ====================

    async def handle_submit_diem_danh(self, telegram_user_id: int, code: str, campus_name: str) -> Dict[str, Any]:
        try:
            token = await self._get_user_token(telegram_user_id)
            if not token:
                return {
                    "success": False,
                    "message": "Bạn chưa đăng nhập. Vui lòng sử dụng /dangnhap để đăng nhập.",
                }
            if campus_name not in CAMPUS_LOCATIONS:
                return {
                    "success": False,
                    "message": "🚫 Lỗi: Campus bạn chọn không hợp lệ. Vui lòng thử lại.",
                }
            location = CAMPUS_LOCATIONS[campus_name]
            device_uuid = await self._get_user_device_uuid(telegram_user_id)
            if not device_uuid:
                return {
                    "success": False,
                    "message": "🚫 Lỗi: Không tìm thấy thông tin thiết bị (device UUID). Vui lòng đăng nhập lại.",
                }
            response = await self._call_api(token, code, device_uuid, location)
            if not response:
                return {
                    "success": False,
                    "message": "🚫 Lỗi: Không thể gửi yêu cầu điểm danh. Vui lòng thử lại sau.",
                }
            if "statusCode" in response:
                msg = response.get("reasons", {}).get("message", "Điểm danh thất bại")
                return {"success": False, "message": f"❌ Điểm danh thất bại: {msg}"}
            if response.get("error") and "status_code" in response:
                msg = response.get("message", "Điểm danh thất bại")
                return {"success": False, "message": f"❌ Điểm danh thất bại: {msg}"}
            return {
                "success": True,
                "message": f"✅ Điểm danh thành công: {response.get('message', 'Điểm danh thành công')}",
            }
        except Exception as e:
            logger.error("Submit điểm danh error for user %s: %s", telegram_user_id, e)
            return {
                "success": False,
                "message": f"🚫 Lỗi: Đã xảy ra lỗi trong quá trình điểm danh: {str(e)}",
            }

    async def _call_api(self, token: str, code: str, device_uuid: str,
                       location: Dict[str, float]) -> Optional[Dict[str, Any]]:
        try:
            url = f"{self.config.HUTECH_API_BASE_URL}{self.config.HUTECH_DIEM_DANH_SUBMIT_ENDPOINT}"
            headers = self.config.HUTECH_MOBILE_HEADERS.copy()
            headers["authorization"] = f"JWT {token}"
            body = {
                "code": code,
                "qr_key": "DIEM_DANH",
                "device_id": device_uuid,
                "diuu": device_uuid,
                "location": {"lat": location["lat"], "long": location["long"]},
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=body) as response:
                    if response.status == 200:
                        return await response.json()
                    error_text = await response.text()
                    logger.error("Điểm danh API error: %s - %s", response.status, error_text)
                    try:
                        err = await response.json()
                        return {
                            "error": True,
                            "status_code": response.status,
                            "message": err.get("reasons", {}).get("message", error_text),
                        }
                    except Exception:
                        return {"error": True, "status_code": response.status, "message": error_text}
        except aiohttp.ClientError as e:
            logger.error("HTTP client error: %s", e)
            return {"error": True, "message": f"Lỗi kết nối: {str(e)}"}
        except json.JSONDecodeError as e:
            logger.error("JSON decode error: %s", e)
            return {"error": True, "message": f"Lỗi phân tích dữ liệu: {str(e)}"}
        except Exception as e:
            logger.error("Unexpected error: %s", e)
            return {"error": True, "message": f"Lỗi không xác định: {str(e)}"}

    async def _get_user_token(self, telegram_user_id: int) -> Optional[str]:
        try:
            response_data = await self.db_manager.get_user_login_response(telegram_user_id)
            if not response_data:
                return None
            old_login_info = response_data.get("old_login_info")
            if isinstance(old_login_info, dict) and old_login_info.get("token"):
                return old_login_info["token"]
            return response_data.get("token")
        except Exception as e:
            logger.error("Error getting token for user %s: %s", telegram_user_id, e)
            return None

    async def _get_user_device_uuid(self, telegram_user_id: int) -> Optional[str]:
        try:
            user = await self.db_manager.get_user(telegram_user_id)
            return user.get("device_uuid") if user else None
        except Exception as e:
            logger.error("Error getting device UUID for user %s: %s", telegram_user_id, e)
            return None
