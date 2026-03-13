#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Handler xử lý điểm danh tất cả tài khoản từ hệ thống HUTECH
"""

import asyncio
import json
import logging
import aiohttp
from typing import Dict, Any, Optional, List

from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes, Application, CommandHandler, CallbackQueryHandler
from telegram.error import BadRequest

from config.config import Config
from handlers.diem_danh_handler import CAMPUS_LOCATIONS
from utils.button_style import make_inline_button

logger = logging.getLogger(__name__)


class DiemDanhTatCaHandler:
    def __init__(self, db_manager, cache_manager):
        self.db_manager = db_manager
        self.cache_manager = cache_manager
        self.config = Config()

    async def handle_diem_danh_tat_ca_menu(self, telegram_user_id: int) -> Dict[str, Any]:
        """
        Xử lý hiển thị menu chọn vị trí điểm danh cho tất cả tài khoản

        Args:
            telegram_user_id: ID của người dùng trên Telegram

        Returns:
            Dict chứa kết quả và dữ liệu menu
        """
        try:
            # Lấy tất cả tài khoản của người dùng
            accounts = await self.db_manager.get_user_accounts(telegram_user_id)

            if not accounts:
                return {
                    "success": False,
                    "message": "Bạn chưa có tài khoản nào. Vui lòng /dangnhap để đăng nhập.",
                    "data": None
                }

            # Trả về danh sách campus để hiển thị menu
            return {
                "success": True,
                "message": "Lấy danh sách campus thành công",
                "data": {
                    "campus_list": list(CAMPUS_LOCATIONS.keys()),
                    "accounts_count": len(accounts)
                }
            }

        except Exception as e:
            logger.error(f"Điểm danh tất cả menu error for user {telegram_user_id}: {e}")
            return {
                "success": False,
                "message": f"🚫 *Lỗi*\n\nĐã xảy ra lỗi khi lấy danh sách campus: {str(e)}",
                "data": None
            }

    async def handle_submit_diem_danh_tat_ca(self, telegram_user_id: int, code: str, campus_name: str) -> Dict[str, Any]:
        """
        Xử lý gửi request điểm danh cho TẤT CẢ tài khoản

        Args:
            telegram_user_id: ID của người dùng trên Telegram
            code: Mã QR cần quét để điểm danh
            campus_name: Tên campus đã chọn

        Returns:
            Dict chứa kết quả và dữ liệu response tổng hợp
        """
        try:
            # Lấy tất cả tài khoản của người dùng
            accounts = await self.db_manager.get_user_accounts(telegram_user_id)

            if not accounts:
                return {
                    "success": False,
                    "message": "Không tìm thấy tài khoản nào. Vui lòng đăng nhập lại.",
                    "data": None
                }

            # Lấy vị trí campus
            if campus_name not in CAMPUS_LOCATIONS:
                return {
                    "success": False,
                    "message": "🚫 *Lỗi*\n\nCampus bạn chọn không hợp lệ. Vui lòng thử lại.",
                    "data": None
                }

            location = CAMPUS_LOCATIONS[campus_name]

            # Hàm phụ để điểm danh cho một account
            async def diem_danh_single_account(account: Dict[str, Any]) -> Dict[str, Any]:
                """Hàm phụ để điểm danh cho một account"""
                username = account.get('username', 'Unknown')
                ho_ten = account.get('ho_ten', username)

                try:
                    # Lấy token cho account này
                    response_data = await self.db_manager.get_user_login_response_by_username(
                        telegram_user_id, username
                    )

                    if not response_data:
                        return {
                            "username": ho_ten,
                            "username_raw": username,
                            "success": False,
                            "message": "Không lấy được thông tin đăng nhập"
                        }

                    # Ưu tiên token từ old_login_info
                    old_login_info = response_data.get("old_login_info")
                    if isinstance(old_login_info, dict) and old_login_info.get("token"):
                        token = old_login_info["token"]
                    else:
                        token = response_data.get("token")

                    if not token:
                        return {
                            "username": ho_ten,
                            "username_raw": username,
                            "success": False,
                            "message": "Token không hợp lệ"
                        }

                    # Lấy device_uuid
                    device_uuid = await self.db_manager.get_user_device_uuid_by_username(
                        telegram_user_id, username
                    )

                    if not device_uuid:
                        return {
                            "username": ho_ten,
                            "username_raw": username,
                            "success": False,
                            "message": "Không tìm thấy device UUID"
                        }

                    # Gọi API điểm danh
                    api_result = await self._call_diem_danh_api(token, code, device_uuid, location)

                    # Parse kết quả
                    if api_result and not api_result.get("error"):
                        return {
                            "username": ho_ten,
                            "username_raw": username,
                            "success": True,
                            "message": api_result.get("message", "Điểm danh thành công")
                        }
                    else:
                        error_msg = api_result.get("message", "Lỗi gọi API") if api_result else "Lỗi gọi API"
                        return {
                            "username": ho_ten,
                            "username_raw": username,
                            "success": False,
                            "message": error_msg
                        }

                except Exception as e:
                    logger.error(f"Error diem danh for account {username}: {e}")
                    return {
                        "username": ho_ten,
                        "username_raw": username,
                        "success": False,
                        "message": f"Lỗi: {str(e)}"
                    }

            # Chạy song song tất cả accounts
            tasks = [diem_danh_single_account(acc) for acc in accounts]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Xử lý kết quả (loại bỏ exception nếu có)
            processed_results = []
            for result in results:
                if isinstance(result, Exception):
                    processed_results.append({
                        "username": "Unknown",
                        "username_raw": "unknown",
                        "success": False,
                        "message": f"Lỗi ngoại lệ: {str(result)}"
                    })
                else:
                    processed_results.append(result)

            # Tạo message kết quả
            message = self.format_diem_danh_tat_ca_message(processed_results)

            return {
                "success": True,
                "message": message,
                "data": processed_results
            }

        except Exception as e:
            logger.error(f"Submit điểm danh tất cả error for user {telegram_user_id}: {e}")
            return {
                "success": False,
                "message": f"🚫 *Lỗi*\n\nĐã xảy ra lỗi trong quá trình điểm danh: {str(e)}",
                "data": None
            }

    async def _call_diem_danh_api(self, token: str, code: str, device_uuid: str, location: Dict[str, float]) -> Optional[Dict[str, Any]]:
        """
        Gọi API điểm danh của HUTECH

        Args:
            token: Token xác thực
            code: Mã QR cần quét
            device_uuid: UUID của thiết bị
            location: Vị trí GPS

        Returns:
            Response data từ API hoặc None nếu có lỗi
        """
        try:
            url = f"{self.config.HUTECH_API_BASE_URL}{self.config.HUTECH_DIEM_DANH_SUBMIT_ENDPOINT}"

            # Tạo headers
            headers = self.config.HUTECH_MOBILE_HEADERS.copy()
            headers["authorization"] = f"JWT {token}"

            # Tạo request body
            request_data = {
                "code": code,
                "qr_key": "DIEM_DANH",
                "device_id": device_uuid,
                "diuu": device_uuid,
                "location": {
                    "lat": location["lat"],
                    "long": location["long"]
                }
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=headers,
                    json=request_data
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        logger.error(f"Điểm danh API error: {response.status} - {error_text}")
                        try:
                            error_json = await response.json()
                            return {
                                "error": True,
                                "status_code": response.status,
                                "message": error_json.get("reasons", {}).get("message", error_text),
                                "full_response": error_json
                            }
                        except:
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

    def format_diem_danh_tat_ca_message(self, results: List[Dict[str, Any]]) -> str:
        """
        Format tin nhắn kết quả cho nhiều tài khoản

        Args:
            results: Danh sách kết quả điểm danh của từng tài khoản

        Returns:
            Chuỗi tin nhắn đã định dạng
        """
        try:
            if not results:
                return "🚫 *Kết Quả Điểm Danh Tất Cả*\n\nKhông có tài khoản nào để điểm danh."

            lines = ["📍 *Kết Quả Điểm Danh Tất Cả*\n"]

            success_count = 0
            fail_count = 0

            for result in results:
                username = result.get("username", "Unknown")
                success = result.get("success", False)
                message = result.get("message", "")

                if success:
                    success_count += 1
                    lines.append(f"✅ *{username}*")
                    lines.append(f"→ {message}\n")
                else:
                    fail_count += 1
                    lines.append(f"❌ *{username}*")
                    lines.append(f"→ {message}\n")

            lines.append("─" * 20)
            lines.append(f"Tổng: {len(results)} tài khoản | ✅ {success_count} thành công | ❌ {fail_count} thất bại")

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"Error formatting diem danh tat ca message: {e}")
            return f"Lỗi định dạng kết quả: {str(e)}"

    def format_diem_danh_tat_ca_keyboard(self) -> List[List[Dict[str, str]]]:
        """
        Tạo keyboard cho các nút chọn campus (giống DiemDanhHandler)

        Returns:
            Danh sách các hàng nút bấm
        """
        try:
            keyboard = []

            # Thêm các nút chọn campus (tối đa 2 nút mỗi hàng)
            row = []
            for i, campus_name in enumerate(CAMPUS_LOCATIONS.keys()):
                row.append({
                    "text": campus_name,
                    "callback_data": f"diemdanhtatca_campus_{campus_name}",
                    "emoji": "📍",
                })
                if len(row) == 2 or i == len(CAMPUS_LOCATIONS) - 1:
                    keyboard.append(row)
                    row = []

            return keyboard

        except Exception as e:
            logger.error(f"Error creating diem danh tat ca keyboard: {e}")
            return []

    def format_diem_danh_tat_ca_numeric_keyboard(self) -> List[List[Dict[str, str]]]:
        """
        Tạo bàn phím số cho nhập 4 số (giống DiemDanhHandler)

        Returns:
            Danh sách các hàng nút bấm
        """
        try:
            keyboard = []

            # Hàng 1: 1 2 3
            keyboard.append([
                {"text": "1", "callback_data": "num_tatca_1"},
                {"text": "2", "callback_data": "num_tatca_2"},
                {"text": "3", "callback_data": "num_tatca_3"}
            ])

            # Hàng 2: 4 5 6
            keyboard.append([
                {"text": "4", "callback_data": "num_tatca_4"},
                {"text": "5", "callback_data": "num_tatca_5"},
                {"text": "6", "callback_data": "num_tatca_6"}
            ])

            # Hàng 3: 7 8 9
            keyboard.append([
                {"text": "7", "callback_data": "num_tatca_7"},
                {"text": "8", "callback_data": "num_tatca_8"},
                {"text": "9", "callback_data": "num_tatca_9"}
            ])

            # Hàng 4: Thoát 0 Xoá
            keyboard.append([
                {"text": "Thoát", "callback_data": "num_tatca_exit", "tone": "danger"},
                {"text": "0", "callback_data": "num_tatca_0"},
                {"text": "Xoá", "callback_data": "num_tatca_delete", "tone": "warning"}
            ])

            return keyboard

        except Exception as e:
            logger.error(f"Error creating diem danh tat ca numeric keyboard: {e}")
            return []

    def format_diem_danh_tat_ca_numeric_message(self, campus_name: str, accounts_count: int = 0, current_input: str = "") -> str:
        """
        Định dạng tin nhắn hiển thị menu với bàn phím số cho điểm danh tất cả

        Args:
            campus_name: Tên campus đã chọn
            accounts_count: Số lượng tài khoản sẽ được điểm danh
            current_input: Chuỗi số đã nhập

        Returns:
            Chuỗi tin nhắn đã định dạng
        """
        try:
            display = self.format_diem_danh_tat_ca_numeric_display(current_input)
            message = f"📍 *Điểm Danh Tất Cả Tại {campus_name}*\n\n"
            message += f"📊 Sẽ điểm danh cho *{accounts_count} tài khoản*\n\n"
            message += f"Nhập mã điểm danh: {display}"

            return message

        except Exception as e:
            logger.error(f"Error formatting diem danh tat ca numeric message: {e}")
            return f"Lỗi định dạng tin nhắn: {str(e)}"

    def format_diem_danh_tat_ca_numeric_display(self, current_input: str) -> str:
        """
        Định dạng hiển thị trạng thái nhập số hiện tại

        Args:
            current_input: Chuỗi số đã nhập

        Returns:
            Chuỗi hiển thị trạng thái
        """
        try:
            # Hiển thị dưới dạng ô vuông cho từng số
            display = ""
            for i in range(4):
                if i < len(current_input):
                    display += f"{current_input[i]} "
                else:
                    display += "▫️"

            return display

        except Exception as e:
            logger.error(f"Error formatting diem danh tat ca numeric display: {e}")
            return "▫️▫️▫️▫️"

    def format_campus_menu_message(self) -> str:
        """
        Định dạng danh sách campus thành tin nhắn menu

        Returns:
            Chuỗi tin nhắn đã định dạng
        """
        try:
            message = "📍 *Chọn Vị Trí Điểm Danh Tất Cả*\n\n"
            message += "💡 *Tip:* Bạn có thể dùng /vitri để lưu vị trí mặc định và bỏ qua bước này."

            return message

        except Exception as e:
            logger.error(f"Error formatting campus menu message: {e}")
            return f"Lỗi định dạng menu campus: {str(e)}"

    # ==================== Command Methods ====================

    async def diemdanhtatca_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý lệnh /diemdanhtatca"""
        user_id = update.effective_user.id

        # Lấy menu chọn campus
        result = await self.handle_diem_danh_tat_ca_menu(user_id)

        if not result["success"]:
            await update.message.reply_text(result['message'], reply_to_message_id=update.message.message_id, parse_mode="Markdown")
            return

        # Kiểm tra xem người dùng đã thiết lập vị trí mặc định chưa
        preferred_campus = await self.db_manager.get_user_preferred_campus(user_id)

        if preferred_campus:
            # Đã có vị trí mặc định -> Bỏ qua chọn campus, đi trực tiếp đến nhập mã
            campus_name = preferred_campus
            context.user_data["diemdanhtatca_campus"] = campus_name
            context.user_data["diemdanhtatca_input"] = ""

            accounts = await self.db_manager.get_user_accounts(user_id)
            accounts_count = len(accounts) if accounts else 0

            message = self.format_diem_danh_tat_ca_numeric_message(campus_name, accounts_count, "")
            keyboard_data = self.format_diem_danh_tat_ca_numeric_keyboard()
            keyboard = []
            for row in keyboard_data:
                keyboard.append([
                    make_inline_button(
                        btn["text"],
                        btn["callback_data"],
                        tone=btn.get("tone"),
                        emoji=btn.get("emoji"),
                    )
                    for btn in row
                ])

            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                message,
                reply_markup=reply_markup,
                parse_mode="Markdown",
                reply_to_message_id=update.message.message_id
            )
        else:
            # Chưa có vị trí mặc định -> Hiển thị menu chọn campus
            message = self.format_campus_menu_message()

            keyboard_data = self.format_diem_danh_tat_ca_keyboard()
            keyboard = []
            for row in keyboard_data:
                keyboard.append([
                    make_inline_button(
                        btn["text"],
                        btn["callback_data"],
                        tone=btn.get("tone"),
                        emoji=btn.get("emoji"),
                    )
                    for btn in row
                ])

            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                message,
                reply_markup=reply_markup,
                parse_mode="Markdown",
                reply_to_message_id=update.message.message_id
            )

    # ==================== Callback Methods ====================

    async def _safe_edit_message_text(
        self,
        query,
        *,
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        parse_mode: Optional[str] = None
    ) -> bool:
        """Edit callback message và bỏ qua lỗi khi nội dung không thay đổi hoặc message đã bị xóa."""
        try:
            await query.edit_message_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            return True
        except BadRequest as e:
            error_msg = str(e)
            if "Message is not modified" in error_msg:
                logger.debug(
                    "Skip diem danh tat ca message edit because content is unchanged | user_id=%s callback_data=%s",
                    getattr(query.from_user, "id", "unknown"),
                    getattr(query, "data", "unknown")
                )
                return False
            if "Message to edit not found" in error_msg:
                logger.warning(
                    "Message to edit not found, sending new message | user_id=%s callback_data=%s",
                    getattr(query.from_user, "id", "unknown"),
                    getattr(query, "data", "unknown")
                )
                if getattr(query, "message", None):
                    try:
                        await query.message.reply_text(
                            text=text,
                            reply_markup=reply_markup,
                            parse_mode=parse_mode
                        )
                    except Exception as send_err:
                        logger.error("Fallback send failed in diem danh tat ca handler: %s", send_err)
                return False
            raise

    async def diemdanhtatca_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý callback từ các nút chọn campus"""
        query = update.callback_query
        user_id = query.from_user.id

        # Lấy callback_data
        callback_data = query.data

        # Xử lý chọn campus
        if callback_data.startswith("diemdanhtatca_campus_"):
            campus_name = callback_data[21:]  # Bỏ "diemdanhtatca_campus_" prefix
            context.user_data["diemdanhtatca_campus"] = campus_name
            context.user_data["diemdanhtatca_input"] = ""

            # Lấy số lượng tài khoản
            accounts = await self.db_manager.get_user_accounts(user_id)
            accounts_count = len(accounts) if accounts else 0

            # Hiển thị bàn phím số
            message = self.format_diem_danh_tat_ca_numeric_message(campus_name, accounts_count, "")

            keyboard_data = self.format_diem_danh_tat_ca_numeric_keyboard()
            keyboard = []
            for row in keyboard_data:
                keyboard.append([
                    make_inline_button(
                        btn["text"],
                        btn["callback_data"],
                        tone=btn.get("tone"),
                        emoji=btn.get("emoji"),
                    )
                    for btn in row
                ])

            reply_markup = InlineKeyboardMarkup(keyboard)

            await self._safe_edit_message_text(
                query,
                text=message,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )

    async def diemdanhtatca_numeric_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý callback từ bàn phím số"""
        query = update.callback_query
        user_id = query.from_user.id

        # Lấy callback_data
        callback_data = query.data

        # Lấy trạng thái nhập hiện tại
        current_input = context.user_data.get("diemdanhtatca_input", "")
        campus_name = context.user_data.get("diemdanhtatca_campus", "")

        # Xử lý các nút
        if callback_data == "num_tatca_exit":
            # Thoát
            context.user_data.pop("diemdanhtatca_input", None)
            context.user_data.pop("diemdanhtatca_campus", None)
            await self._safe_edit_message_text(
                query,
                text="❎ *Đã thoát lệnh.*\n\nDùng /diemdanhtatca để bắt đầu lại.",
                parse_mode="Markdown"
            )
            return

        elif callback_data == "num_tatca_delete":
            # Xoá ký tự cuối
            current_input = current_input[:-1]
            context.user_data["diemdanhtatca_input"] = current_input

        elif callback_data.startswith("num_tatca_"):
            # Nhập số
            num = callback_data[10:]  # Bỏ "num_tatca_" prefix
            if len(current_input) < 4:
                current_input += num
                context.user_data["diemdanhtatca_input"] = current_input

        # Cập nhật hiển thị
        accounts = await self.db_manager.get_user_accounts(user_id)
        accounts_count = len(accounts) if accounts else 0

        message = self.format_diem_danh_tat_ca_numeric_message(campus_name, accounts_count, current_input)

        keyboard_data = self.format_diem_danh_tat_ca_numeric_keyboard()
        keyboard = []
        for row in keyboard_data:
            keyboard.append([
                make_inline_button(
                    btn["text"],
                    btn["callback_data"],
                    tone=btn.get("tone"),
                    emoji=btn.get("emoji"),
                )
                for btn in row
            ])

        reply_markup = InlineKeyboardMarkup(keyboard)

        # Kiểm tra nếu đã nhập đủ 4 số
        if len(current_input) == 4:
            # Thực hiện điểm danh tất cả
            await self._safe_edit_message_text(
                query,
                text=f"{message}\n\nĐang điểm danh tất cả tài khoản...",
                parse_mode="Markdown"
            )

            result = await self.handle_submit_diem_danh_tat_ca(user_id, current_input, campus_name)

            await self._safe_edit_message_text(
                query,
                text=result['message'],
                parse_mode="Markdown"
            )

            # Xóa dữ liệu tạm
            context.user_data.pop("diemdanhtatca_input", None)
            context.user_data.pop("diemdanhtatca_campus", None)
        else:
            await self._safe_edit_message_text(
                query,
                text=message,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )

    def register_commands(self, application: Application) -> None:
        """Đăng ký command handlers với Application"""
        application.add_handler(CommandHandler("diemdanhtatca", self.diemdanhtatca_command))

    def register_callbacks(self, application: Application) -> None:
        """Đăng ký callback handlers với Application"""
        application.add_handler(CallbackQueryHandler(self.diemdanhtatca_callback, pattern="^diemdanhtatca_campus_"))
        application.add_handler(CallbackQueryHandler(self.diemdanhtatca_numeric_callback, pattern="^num_tatca_"))
