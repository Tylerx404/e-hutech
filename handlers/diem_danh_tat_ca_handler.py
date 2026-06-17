#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Handler xử lý điểm danh tất cả tài khoản cùng lúc.

State tạm per user (Redis):
    feature: "diemdanhtatca"
    campus: tên campus
    input: chuỗi số đã nhập
    accounts: danh sách accounts (cache lại lúc bắt đầu)

Cú pháp callback:
    diemdanhtatca_campus_<campus>
    num_tatca_<digit>  | num_tatca_exit  | num_tatca_delete
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import aiohttp
from datetime import datetime, timedelta

from config.config import Config
from utils.button_style import make_inline_button, build_inline_keyboard
from utils.state_store import StateStore
from utils.telegram_api import TelegramAPI, TelegramAPIError
from handlers.vi_tri_handler import CAMPUS_LOCATIONS

logger = logging.getLogger(__name__)

CODE_LENGTH = 4


class DiemDanhTatCaHandler:
    def __init__(self, db_manager, cache_manager, telegram_api: Optional[TelegramAPI] = None):
        self.db_manager = db_manager
        self.cache_manager = cache_manager
        self.config = Config()
        self.telegram = telegram_api or TelegramAPI(self.config)
        self.state = StateStore(self.cache_manager)

    # ==================== Command ====================

    async def cmd_diemdanhtatca(self, chat_id: int, user_id: int, reply_to_message_id: Optional[int]) -> None:
        accounts = await self.db_manager.get_user_accounts(user_id)
        if not accounts:
            await self.telegram.send_message(
                chat_id=chat_id,
                text="Bạn chưa có tài khoản nào. Vui lòng /dangnhap để đăng nhập.",
                parse_mode="HTML",
                reply_to_message_id=reply_to_message_id,
            )
            return

        preferred = await self.db_manager.get_user_preferred_campus(user_id)
        if preferred:
            await self._start_numeric(chat_id, user_id, preferred, len(accounts), reply_to_message_id)
        else:
            await self._show_campus_menu(chat_id, len(accounts), reply_to_message_id)

    # ==================== Callbacks ====================

    async def cb_campus(self, callback_id: str, chat_id: int, message_id: int,
                       user_id: int, callback_data: str) -> None:
        if not callback_data.startswith("diemdanhtatca_campus_"):
            return
        campus = callback_data[len("diemdanhtatca_campus_"):]
        accounts = await self.db_manager.get_user_accounts(user_id)
        await self.state.set_state(user_id, {
            "feature": "diemdanhtatca",
            "campus": campus,
            "input": "",
            "accounts_count": len(accounts),
        })
        try:
            await self.telegram.edit_message_text_plain(
                chat_id=chat_id,
                message_id=message_id,
                text=self._numeric_text(campus, len(accounts), ""),
                reply_markup=build_inline_keyboard(self._numeric_rows()),
                parse_mode="Markdown",
            )
        except TelegramAPIError:
            pass

    async def cb_numeric(self, callback_id: str, chat_id: int, message_id: int,
                        user_id: int, callback_data: str) -> None:
        st = await self.state.get_state(user_id)
        if st.get("feature") != "diemdanhtatca":
            return
        campus = st.get("campus", "")
        accounts_count = st.get("accounts_count", 0)
        current = st.get("input", "")

        if callback_data == "num_tatca_exit":
            await self.state.clear_state(user_id)
            try:
                await self.telegram.edit_message_text_plain(
                    chat_id=chat_id,
                    message_id=message_id,
                    text="❎ *Đã thoát lệnh.*\n\nDùng /diemdanhtatca để bắt đầu lại.",
                    parse_mode="Markdown",
                )
            except TelegramAPIError:
                pass
            return
        if callback_data == "num_tatca_delete":
            current = current[:-1]
        elif callback_data.startswith("num_tatca_"):
            num = callback_data[len("num_tatca_"):]
            if num.isdigit() and len(current) < CODE_LENGTH:
                current += num
        else:
            return

        await self.state.set_state(user_id, {**st, "input": current})

        if len(current) == CODE_LENGTH:
            await self._do_submit(chat_id, message_id, user_id, campus, current)
        else:
            try:
                await self.telegram.edit_message_text_plain(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=self._numeric_text(campus, accounts_count, current),
                    reply_markup=build_inline_keyboard(self._numeric_rows()),
                    parse_mode="Markdown",
                )
            except TelegramAPIError as e:
                if "message is not modified" not in e.description.lower():
                    raise

    # ==================== Internal ====================

    async def _show_campus_menu(self, chat_id: int, accounts_count: int,
                                reply_to_message_id: Optional[int]) -> None:
        text = (
            f"📍 *Chọn Vị Trí Điểm Danh Tất Cả ({accounts_count} tài khoản)*\n\n"
            "💡 *Tip:* Bạn có thể dùng /vitri để lưu vị trí mặc định và bỏ qua bước này."
        )
        rows: List[List[Dict[str, Any]]] = []
        row: List[Dict[str, Any]] = []
        keys = list(CAMPUS_LOCATIONS.keys())
        for i, name in enumerate(keys):
            row.append(make_inline_button(name, f"diemdanhtatca_campus_{name}", tone=None, emoji="📍"))
            if len(row) == 2 or i == len(keys) - 1:
                rows.append(row)
                row = []
        await self.telegram.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=build_inline_keyboard(rows),
            parse_mode="Markdown",
            reply_to_message_id=reply_to_message_id,
        )

    async def _start_numeric(self, chat_id: int, user_id: int, campus: str,
                             accounts_count: int, reply_to_message_id: Optional[int]) -> None:
        await self.state.set_state(user_id, {
            "feature": "diemdanhtatca",
            "campus": campus,
            "input": "",
            "accounts_count": accounts_count,
        })
        await self.telegram.send_message(
            chat_id=chat_id,
            text=self._numeric_text(campus, accounts_count, ""),
            reply_markup=build_inline_keyboard(self._numeric_rows()),
            parse_mode="Markdown",
            reply_to_message_id=reply_to_message_id,
        )

    @staticmethod
    def _numeric_text(campus: str, accounts_count: int, current: str) -> str:
        display = "".join((current[i] + " ") if i < len(current) else "▫️" for i in range(CODE_LENGTH))
        return (
            f"📍 *Điểm Danh Tất Cả Tại {campus}*\n\n"
            f"📊 Sẽ điểm danh cho *{accounts_count} tài khoản*\n\n"
            f"Nhập mã điểm danh: {display}"
        )

    @staticmethod
    def _numeric_rows() -> List[List[Dict[str, Any]]]:
        return [
            [
                make_inline_button("1", "num_tatca_1", tone=None),
                make_inline_button("2", "num_tatca_2", tone=None),
                make_inline_button("3", "num_tatca_3", tone=None),
            ],
            [
                make_inline_button("4", "num_tatca_4", tone=None),
                make_inline_button("5", "num_tatca_5", tone=None),
                make_inline_button("6", "num_tatca_6", tone=None),
            ],
            [
                make_inline_button("7", "num_tatca_7", tone=None),
                make_inline_button("8", "num_tatca_8", tone=None),
                make_inline_button("9", "num_tatca_9", tone=None),
            ],
            [
                make_inline_button("Thoát", "num_tatca_exit", tone="danger"),
                make_inline_button("0", "num_tatca_0", tone=None),
                make_inline_button("Xoá", "num_tatca_delete", tone="warning"),
            ],
        ]

    async def _do_submit(self, chat_id: int, message_id: int, user_id: int,
                         campus: str, code: str) -> None:
        st = await self.state.get_state(user_id)
        accounts_count = st.get("accounts_count", 0)
        try:
            await self.telegram.edit_message_text_plain(
                chat_id=chat_id,
                message_id=message_id,
                text=self._numeric_text(campus, accounts_count, code) + "\n\n⏳ Đang điểm danh tất cả...",
                parse_mode="Markdown",
            )
        except TelegramAPIError:
            pass

        result = await self.handle_submit_all(user_id, code, campus)
        await self.state.clear_state(user_id)

        try:
            await self.telegram.edit_message_text_plain(
                chat_id=chat_id,
                message_id=message_id,
                text=result["message"],
                parse_mode="HTML",
            )
        except TelegramAPIError:
            await self.telegram.send_message(
                chat_id=chat_id, text=result["message"], parse_mode="HTML"
            )

    # ==================== HUTECH API ====================

    async def handle_submit_all(self, telegram_user_id: int, code: str, campus_name: str) -> Dict[str, Any]:
        try:
            accounts = await self.db_manager.get_user_accounts(telegram_user_id)
            if not accounts:
                return {"success": False, "message": "Không tìm thấy tài khoản nào. Vui lòng đăng nhập lại."}
            if campus_name not in CAMPUS_LOCATIONS:
                return {"success": False, "message": "🚫 Lỗi: Campus không hợp lệ."}
            location = CAMPUS_LOCATIONS[campus_name]

            async def submit_one(account: Dict[str, Any]) -> Dict[str, Any]:
                username = account.get("username", "Unknown")
                ho_ten = account.get("ho_ten") or username
                try:
                    response = await self.db_manager.get_user_login_response_by_username(
                        telegram_user_id, username
                    )
                    if not response:
                        return {"username": ho_ten, "success": False, "message": "Không lấy được thông tin đăng nhập"}
                    old_login_info = response.get("old_login_info")
                    token = old_login_info.get("token") if isinstance(old_login_info, dict) and old_login_info.get("token") else response.get("token")
                    if not token:
                        return {"username": ho_ten, "success": False, "message": "Token không hợp lệ"}
                    device_uuid = await self.db_manager.get_user_device_uuid_by_username(
                        telegram_user_id, username
                    )
                    if not device_uuid:
                        return {"username": ho_ten, "success": False, "message": "Không tìm thấy device UUID"}
                    api_result = await self._call_api(token, code, device_uuid, location)
                    if api_result and not api_result.get("error"):
                        return {"username": ho_ten, "success": True, "message": api_result.get("message", "Điểm danh thành công")}
                    msg = api_result.get("message", "Lỗi gọi API") if api_result else "Lỗi gọi API"
                    return {"username": ho_ten, "success": False, "message": msg}
                except Exception as e:
                    logger.error("Error diem danh for account %s: %s", username, e)
                    return {"username": ho_ten, "success": False, "message": f"Lỗi: {str(e)}"}

            tasks = [submit_one(acc) for acc in accounts]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            processed: List[Dict[str, Any]] = []
            for r in results:
                if isinstance(r, Exception):
                    processed.append({"username": "Unknown", "success": False, "message": f"Lỗi ngoại lệ: {str(r)}"})
                else:
                    processed.append(r)

            return {"success": True, "message": self._format_result(processed), "data": processed}
        except Exception as e:
            logger.error("Submit điểm danh tất cả error for user %s: %s", telegram_user_id, e)
            return {"success": False, "message": f"🚫 Lỗi: {str(e)}"}

    @staticmethod
    def _format_result(results: List[Dict[str, Any]]) -> str:
        if not results:
            return "🚫 Kết Quả Điểm Danh Tất Cả\n\nKhông có tài khoản nào để điểm danh."
        lines = ["📍 <b>Kết Quả Điểm Danh Tất Cả</b>", ""]
        success = fail = 0
        for r in results:
            username = r.get("username", "Unknown")
            ok = r.get("success", False)
            msg = r.get("message", "")
            if ok:
                success += 1
                lines.append(f"✅ <b>{username}</b>")
            else:
                fail += 1
                lines.append(f"❌ <b>{username}</b>")
            lines.append(f"→ {msg}")
            lines.append("")
        lines.append("─" * 20)
        lines.append(f"Tổng: {len(results)} tài khoản | ✅ {success} thành công | ❌ {fail} thất bại")
        return "\n".join(lines)

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
                        return {"error": True, "status_code": response.status, "message": err.get("reasons", {}).get("message", error_text)}
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
