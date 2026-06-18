#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Handler xử lý đăng nhập vào hệ thống HUTECH.

Luồng đăng nhập 2 bước, dùng state tạm để nhớ user đang ở bước nào:
1. User gửi `/dangnhap` → hỏi username.
2. User nhập username → hỏi password.
3. User nhập password → gọi API HUTECH, lưu account vào DB, xóa state.

State per user (lưu trong cache qua `utils/state_store`):
    {
        "step": "awaiting_username" | "awaiting_password",
        "username": "...",
        "username_prompt_message_id": ...,
        "password_prompt_message_id": ...,
        "login_command_message_id": ...,
    }
"""

import json
import logging
from typing import Any, Dict, Optional

import aiohttp

from config.config import Config
from utils.state_store import StateStore
from utils.telegram_api import TelegramAPI, TelegramAPIError
from utils.utils import generate_uuid
from utils.rich_message import p, b, code, section_heading

logger = logging.getLogger(__name__)

# Tên các step trong state
STEP_AWAITING_USERNAME = "awaiting_username"
STEP_AWAITING_PASSWORD = "awaiting_password"


class LoginHandler:
    """Handler quản lý flow đăng nhập 2 bước vào hệ thống HUTECH."""

    def __init__(self, db_manager, cache_manager, telegram_api: Optional[TelegramAPI] = None):
        self.db_manager = db_manager
        self.cache_manager = cache_manager
        self.config = Config()
        self.telegram = telegram_api or TelegramAPI(self.config)
        self.state = StateStore(self.cache_manager)

    # ==================== Public API ====================

    async def start(self, chat_id: int, user_id: int, reply_to_message_id: Optional[int]) -> None:
        """
        Bắt đầu luồng đăng nhập: gửi prompt hỏi username, lưu state.
        """
        # Nếu user đã trong state login (vd: gõ /dangnhap 2 lần), hủy state cũ.
        await self.state.clear_state(user_id)

        sent = await self.telegram.send_message(
            chat_id=chat_id,
            text="Vui lòng nhập tên tài khoản HUTECH của bạn:",
            reply_to_message_id=reply_to_message_id,
        )
        await self.state.set_state(user_id, {
            "step": STEP_AWAITING_USERNAME,
            "login_command_message_id": reply_to_message_id,
            "username_prompt_message_id": sent.get("message_id"),
        })

    async def on_user_text(self, chat_id: int, user_id: int, text: str, message_id: int) -> bool:
        """
        Nhận text từ user khi đang ở trong luồng login.

        Trả về True nếu text được xử lý (kết thúc luồng), False nếu không.
        """
        st = await self.state.get_state(user_id)
        step = st.get("step")

        if step == STEP_AWAITING_USERNAME:
            await self._handle_username(chat_id, user_id, text, message_id, st)
            return True

        if step == STEP_AWAITING_PASSWORD:
            await self._handle_password(chat_id, user_id, text, message_id, st)
            return True

        return False

    async def cancel(self, chat_id: int, user_id: int, message_id: Optional[int] = None) -> None:
        """Hủy luồng login, xóa state và message prompt nếu có."""
        st = await self.state.get_state(user_id)
        prompt_id = st.get("username_prompt_message_id")
        if prompt_id:
            await self.telegram.delete_message(chat_id, prompt_id)
        await self.state.clear_state(user_id)
        if message_id:
            await self.telegram.delete_message(chat_id, message_id)
        await self.telegram.send_message(chat_id=chat_id, text="Đã hủy đăng nhập.")

    # ==================== Internal ====================

    async def _handle_username(
        self, chat_id: int, user_id: int, username: str, message_id: int, st: Dict[str, Any]
    ) -> None:
        """User vừa gửi username. Xoá message user + prompt, hỏi password."""
        login_command_message_id = st.get("login_command_message_id")
        username_prompt_message_id = st.get("username_prompt_message_id")

        # Xoá message user chứa username
        await self.telegram.delete_message(chat_id, message_id)
        # Xoá message prompt hỏi username
        if username_prompt_message_id:
            await self.telegram.delete_message(chat_id, username_prompt_message_id)

        # Gửi prompt hỏi password
        sent = await self.telegram.send_message(
            chat_id=chat_id,
            text="Vui lòng nhập mật khẩu của bạn:",
            reply_to_message_id=login_command_message_id,
        )
        await self.state.set_state(user_id, {
            "step": STEP_AWAITING_PASSWORD,
            "username": username,
            "login_command_message_id": login_command_message_id,
            "password_prompt_message_id": sent.get("message_id"),
        })

    async def _handle_password(
        self, chat_id: int, user_id: int, password: str, message_id: int, st: Dict[str, Any]
    ) -> None:
        """User vừa gửi password. Xoá message user + prompt, gọi API đăng nhập."""
        username = st.get("username", "")
        login_command_message_id = st.get("login_command_message_id")
        password_prompt_message_id = st.get("password_prompt_message_id")

        # Xoá message chứa password và prompt ngay để tránh lộ
        await self.telegram.delete_message(chat_id, message_id)
        if password_prompt_message_id:
            await self.telegram.delete_message(chat_id, password_prompt_message_id)

        device_uuid = generate_uuid()
        result = await self.handle_login(user_id, username, password, device_uuid)

        # Xóa state
        await self.state.clear_state(user_id)

        if result["success"]:
            ho_ten = result.get("ho_ten")
            text = f"Đăng nhập thành công! ({ho_ten})" if ho_ten else "Đăng nhập thành công!"
            await self.telegram.send_message(
                chat_id=chat_id,
                text=text,
                reply_to_message_id=login_command_message_id,
            )
        else:
            await self.telegram.send_message(
                chat_id=chat_id,
                text=result["message"],
                reply_to_message_id=login_command_message_id,
                parse_mode="HTML",
            )

    # ==================== HUTECH login ====================

    async def handle_login(
        self, telegram_user_id: int, username: str, password: str, device_uuid: str
    ) -> Dict[str, Any]:
        """
        Xử lý đăng nhập vào hệ thống HUTECH.

        Returns: dict {success, message, data, ho_ten}
        """
        try:
            request_data = {
                "diuu": device_uuid,
                "username": username,
                "password": password,
            }
            response_data = await self._call_login_api(request_data)

            if response_data and "token" in response_data:
                ho_ten = self._extract_ho_ten(response_data)
                account_saved = await self.db_manager.add_account(
                    telegram_user_id, username, password, device_uuid, response_data, ho_ten
                )
                if account_saved:
                    await self.cache_manager.clear_user_cache(telegram_user_id)
                    return {
                        "success": True,
                        "message": "Đăng nhập thành công!",
                        "data": response_data,
                        "ho_ten": ho_ten,
                    }
                return {
                    "success": False,
                    "message": "🚫 Lỗi: Không thể lưu thông tin đăng nhập. Vui lòng thử lại sau.",
                    "data": None,
                    "show_back_button": True,
                }
            return {
                "success": False,
                "message": "🚫 Đăng nhập thất bại\n\nTài khoản hoặc mật khẩu không đúng. Vui lòng kiểm tra lại.",
                "data": response_data,
                "show_back_button": True,
            }
        except Exception as e:
            logger.error("Login error for user %s: %s", telegram_user_id, e)
            return {
                "success": False,
                "message": f"🚫 Lỗi\n\nĐã xảy ra lỗi trong quá trình đăng nhập: {str(e)}",
                "data": None,
                "show_back_button": True,
            }

    def _extract_ho_ten(self, response_data: Dict[str, Any]) -> str:
        if "data" in response_data and isinstance(response_data["data"], dict):
            data = response_data["data"]
            if "ho_ten" in data:
                return data["ho_ten"]
        if "old_login_info" in response_data and isinstance(response_data["old_login_info"], dict):
            old_info = response_data["old_login_info"]
            if "result" in old_info and isinstance(old_info["result"], dict):
                result = old_info["result"]
                if "Ho_Ten" in result:
                    return result["Ho_Ten"]
        return ""

    async def _call_login_api(self, request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            url = f"{self.config.HUTECH_API_BASE_URL}{self.config.HUTECH_LOGIN_ENDPOINT}"
            headers = self.config.HUTECH_STUDENT_HEADERS.copy()
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=request_data) as response:
                    if response.status == 200:
                        return await response.json()
                    error_text = await response.text()
                    logger.error("Login API error: %s - %s", response.status, error_text)
                    return {
                        "error": True,
                        "status_code": response.status,
                        "message": error_text,
                    }
        except aiohttp.ClientError as e:
            logger.error("HTTP client error: %s", e)
            return {"error": True, "message": f"Lỗi kết nối: {str(e)}"}
        except json.JSONDecodeError as e:
            logger.error("JSON decode error: %s", e)
            return {"error": True, "message": f"Lỗi phân tích dữ liệu: {str(e)}"}
        except Exception as e:
            logger.error("Unexpected error: %s", e)
            return {"error": True, "message": f"Lỗi không xác định: {str(e)}"}

    # ==================== Getter giữ tương thích ====================

    async def get_user_token(self, telegram_user_id: int) -> Optional[str]:
        try:
            response_data = await self.db_manager.get_user_login_response(telegram_user_id)
            if response_data and "token" in response_data:
                return response_data["token"]
            return None
        except Exception as e:
            logger.error("Error getting token for user %s: %s", telegram_user_id, e)
            return None

    async def get_user_token_by_username(self, telegram_user_id: int, username: str) -> Optional[str]:
        try:
            response_data = await self.db_manager.get_user_login_response_by_username(telegram_user_id, username)
            if response_data and "token" in response_data:
                return response_data["token"]
            return None
        except Exception as e:
            logger.error("Error getting token for user %s/%s: %s", telegram_user_id, username, e)
            return None

    async def get_user_device_uuid(self, telegram_user_id: int) -> Optional[str]:
        try:
            user = await self.db_manager.get_user(telegram_user_id)
            if user:
                return user.get("device_uuid")
            return None
        except Exception as e:
            logger.error("Error getting device UUID for user %s: %s", telegram_user_id, e)
            return None

    async def get_user_info(self, telegram_user_id: int) -> Optional[Dict[str, Any]]:
        return await self._extract_user_info(
            await self.db_manager.get_user_login_response(telegram_user_id)
        )

    async def get_user_info_by_username(
        self, telegram_user_id: int, username: str
    ) -> Optional[Dict[str, Any]]:
        return await self._extract_user_info(
            await self.db_manager.get_user_login_response_by_username(telegram_user_id, username)
        )

    @staticmethod
    def _extract_user_info(response_data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not response_data:
            return None
        user_info: Dict[str, Any] = {}
        if "username" in response_data:
            user_info["username"] = response_data["username"]
        if "data" in response_data and isinstance(response_data["data"], dict):
            data = response_data["data"]
            for k in ("email", "ho_ten", "so_dien_thoai"):
                if k in data:
                    user_info[k] = data[k]
        if "old_login_info" in response_data and isinstance(response_data["old_login_info"], dict):
            old_info = response_data["old_login_info"]
            if "result" in old_info and isinstance(old_info["result"], dict):
                result = old_info["result"]
                for k in ("Ho_Ten", "email", "contact_id"):
                    if k in result:
                        user_info[k] = result[k]
        if "contact_id" in response_data:
            user_info["contact_id"] = response_data["contact_id"]
        return user_info or None
