#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Thin async client cho Telegram Bot API.

Gọi trực tiếp `https://api.telegram.org/bot<TOKEN>/<METHOD>` qua `aiohttp`,
không qua thư viện python-telegram-bot. Tự quản lý một `aiohttp.ClientSession`
dùng chung cho cả vòng đời bot.

Hỗ trợ:
- Gọi JSON (`call`) và multipart upload (`call_form`).
- Long-polling `getUpdates`.
- High-level helpers: `send_message`, `send_rich_message`, `edit_message_text_*`,
  `answer_callback_query`, `delete_message`, `send_document`.

Cú pháp Rich Message (Bot API 10.1):
- Gửi mới: dùng `send_rich_message` với `rich_message: {"html": "<h1>...</h1>"}`.
- Edit: dùng `edit_message_text_rich` với `rich_message: {"html": "..."}` thay cho
  `text` (text và rich_message là mutually exclusive).
"""

import asyncio
import json
import logging
import mimetypes
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import aiohttp

from config.config import Config

logger = logging.getLogger(__name__)

# Bot API base URL
_API_BASE = "https://api.telegram.org"

# Các update types bot cần nhận (qua long-polling)
DEFAULT_ALLOWED_UPDATES = [
    "message",
    "edited_message",
    "callback_query",
    "my_chat_member",
]


class TelegramAPIError(Exception):
    """Lỗi trả về từ Telegram Bot API (khi `ok=False` trong response)."""

    def __init__(self, method: str, code: int, description: str):
        super().__init__(f"{method} failed: {code} {description}")
        self.method = method
        self.code = code
        self.description = description


class TelegramAPI:
    """Thin async client cho Telegram Bot API."""

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self._session: Optional[aiohttp.ClientSession] = None

    async def start(self) -> None:
        """Khởi tạo aiohttp session. Gọi 1 lần trước khi dùng các method khác."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            logger.info("Đã khởi tạo aiohttp session cho Telegram Bot API.")

    async def close(self) -> None:
        """Đóng aiohttp session khi bot dừng."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            logger.info("Đã đóng aiohttp session.")

    @property
    def session(self) -> aiohttp.ClientSession:
        """Trả về session hiện tại. Raise nếu chưa `start()`."""
        if self._session is None or self._session.closed:
            raise RuntimeError("TelegramAPI chưa được start(). Gọi start() trước.")
        return self._session

    def _url(self, method: str) -> str:
        """Sinh URL đầy đủ cho 1 method của Bot API."""
        return f"{_API_BASE}/bot{self.config.TELEGRAM_BOT_TOKEN}/{method}"

    async def call(
        self,
        method: str,
        *,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Gọi Bot API dạng JSON (POST). Trả về `result` nếu ok=True, raise TelegramAPIError nếu lỗi."""
        url = self._url(method)
        if params:
            params = {k: v for k, v in params.items() if v is not None}
        try:
            async with self.session.post(url, json=params) as resp:
                try:
                    payload = await resp.json(content_type=None)
                except (aiohttp.ContentTypeError, json.JSONDecodeError) as e:
                    text = await resp.text()
                    raise TelegramAPIError(method, resp.status, f"Invalid JSON: {text[:200]}") from e

                if not payload.get("ok"):
                    code = int(payload.get("error_code") or resp.status or 0)
                    description = payload.get("description") or "Unknown error"
                    raise TelegramAPIError(method, code, description)
                return payload.get("result", {})
        except aiohttp.ClientError as e:
            raise TelegramAPIError(method, 0, f"Network error: {e}") from e

    async def call_form(
        self,
        method: str,
        *,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Gọi Bot API dạng multipart/form-data (dùng cho upload file).

        Args:
            method: Tên method (vd `sendDocument`).
            data: Form fields dạng string/int/dict/list (dict/list sẽ tự JSON-encode).
            files: Dict `{field_name: file_value}`. `file_value` có thể là Path,
                   bytes, hoặc tuple đã đúng định dạng.
        """
        url = self._url(method)
        if data:
            data = {k: v for k, v in data.items() if v is not None}
        form = aiohttp.FormData()
        if data:
            for k, v in data.items():
                if isinstance(v, (dict, list)):
                    form.add_field(k, json.dumps(v, ensure_ascii=False))
                else:
                    form.add_field(k, str(v))
        if files:
            for field, value in files.items():
                form.add_field(field, *self._normalize_file(value))
        try:
            async with self.session.post(url, data=form) as resp:
                try:
                    payload = await resp.json(content_type=None)
                except (aiohttp.ContentTypeError, json.JSONDecodeError) as e:
                    text = await resp.text()
                    raise TelegramAPIError(method, resp.status, f"Invalid JSON: {text[:200]}") from e

                if not payload.get("ok"):
                    code = int(payload.get("error_code") or resp.status or 0)
                    description = payload.get("description") or "Unknown error"
                    raise TelegramAPIError(method, code, description)
                return payload.get("result", {})
        except aiohttp.ClientError as e:
            raise TelegramAPIError(method, 0, f"Network error: {e}") from e

    @staticmethod
    def _normalize_file(value: Any) -> tuple:
        """Chuẩn hoá file input thành tuple `(filename, payload, content_type)` cho aiohttp.

        Hỗ trợ:
        - tuple đã đúng định dạng `(filename, payload, content_type)`.
        - `(filename, bytes)`.
        - `(filename, Path)`.
        - `(filename, file_object)`.
        - `Path` thuần.
        - `bytes` / `bytearray`.
        """
        if isinstance(value, tuple):
            if len(value) == 4:
                return value
            if len(value) == 3:
                filename, payload, content_type = value
                if isinstance(payload, (bytes, bytearray)):
                    return filename, bytes(payload), content_type
                return filename, payload, content_type
            if len(value) == 2:
                filename, payload = value
                if isinstance(payload, Path):
                    ctype = mimetypes.guess_type(str(payload))[0] or "application/octet-stream"
                    payload.seek(0) if hasattr(payload, "seek") else None
                    return filename, payload.read(), ctype
                if isinstance(payload, (bytes, bytearray)):
                    ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
                    return filename, bytes(payload), ctype
                return filename, payload, None
        if isinstance(value, Path):
            ctype = mimetypes.guess_type(str(value))[0] or "application/octet-stream"
            return value.name, value.read_bytes(), ctype
        if isinstance(value, (bytes, bytearray)):
            ctype = mimetypes.guess_type("file")[0] or "application/octet-stream"
            return "file", bytes(value), ctype
        raise ValueError(f"Không hỗ trợ kiểu file: {type(value)}")

    # ==================== High-level helpers ====================

    async def get_me(self) -> Dict[str, Any]:
        """Gọi `getMe` — lấy thông tin bot hiện tại."""
        return await self.call("getMe")

    async def get_updates(
        self,
        offset: Optional[int] = None,
        limit: int = 100,
        allowed_updates: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Long-polling `getUpdates`.

        Args:
            offset: Identifier của update tiếp theo. None = lấy từ đầu.
            limit: Số update tối đa mỗi lần (1-100).
            allowed_updates: Danh sách update types cần nhận.
        """
        params: Dict[str, Any] = {
            "offset": offset,
            "limit": limit,
            "timeout": 25,
            "allowed_updates": allowed_updates or DEFAULT_ALLOWED_UPDATES,
        }
        return await self.call("getUpdates", params=params)

    async def send_message(
        self,
        chat_id: Union[int, str],
        text: str,
        *,
        reply_markup: Optional[Dict[str, Any]] = None,
        reply_to_message_id: Optional[int] = None,
        parse_mode: Optional[str] = None,
        link_preview_options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Gửi tin nhắn text đơn giản qua `sendMessage`. Tự tắt link preview khi có parse_mode."""
        params: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "reply_markup": reply_markup,
            "reply_to_message_id": reply_to_message_id,
            "parse_mode": parse_mode,
        }
        if parse_mode and link_preview_options is None:
            params["link_preview_options"] = {"is_disabled": True}
        return await self.call("sendMessage", params=params)

    async def send_rich_message(
        self,
        chat_id: Union[int, str],
        html: str,
        *,
        reply_markup: Optional[Dict[str, Any]] = None,
        reply_to_message_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Gửi Rich Message (Bot API 10.1) qua `sendRichMessage`.

        Args:
            html: Chuỗi HTML đã build bằng `utils/rich_message.py`.
        """
        params: Dict[str, Any] = {
            "chat_id": chat_id,
            "rich_message": {"html": html},
            "reply_markup": reply_markup,
            "reply_to_message_id": reply_to_message_id,
        }
        return await self.call("sendRichMessage", params=params)

    async def edit_message_text_rich(
        self,
        chat_id: Union[int, str],
        message_id: int,
        html: str,
        *,
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> Union[Dict[str, Any], bool]:
        """Edit message dùng Rich Message HTML.

        Trả về `True` nếu API trả về "Message is not modified" (coi như thành công).
        Ngược lại trả về dict Message.
        """
        params: Dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "rich_message": {"html": html},
            "reply_markup": reply_markup,
        }
        try:
            return await self.call("editMessageText", params=params)
        except TelegramAPIError as e:
            if "message is not modified" in e.description.lower():
                return True
            raise

    async def edit_message_text_plain(
        self,
        chat_id: Union[int, str],
        message_id: int,
        text: str,
        *,
        reply_markup: Optional[Dict[str, Any]] = None,
        parse_mode: Optional[str] = None,
    ) -> Union[Dict[str, Any], bool]:
        """Edit message text dạng plain/HTML/Markdown.

        Trả về `True` nếu "Message is not modified".
        """
        params: Dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "reply_markup": reply_markup,
            "parse_mode": parse_mode,
        }
        try:
            return await self.call("editMessageText", params=params)
        except TelegramAPIError as e:
            if "message is not modified" in e.description.lower():
                return True
            raise

    async def edit_message_reply_markup(
        self,
        chat_id: Union[int, str],
        message_id: int,
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> Union[Dict[str, Any], bool]:
        """Chỉ thay đổi reply_markup của message, giữ nguyên text."""
        params: Dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "reply_markup": reply_markup,
        }
        try:
            return await self.call("editMessageReplyMarkup", params=params)
        except TelegramAPIError as e:
            if "message is not modified" in e.description.lower():
                return True
            raise

    async def answer_callback_query(
        self,
        callback_query_id: str,
        *,
        text: Optional[str] = None,
        show_alert: bool = False,
        url: Optional[str] = None,
        cache_time: int = 0,
    ) -> bool:
        """Trả lời callback query. Trả về True nếu thành công hoặc query đã hết hạn."""
        params: Dict[str, Any] = {
            "callback_query_id": callback_query_id,
            "text": text,
            "show_alert": show_alert,
            "url": url,
            "cache_time": cache_time,
        }
        try:
            await self.call("answerCallbackQuery", params=params)
            return True
        except TelegramAPIError as e:
            desc = e.description.lower()
            if "query is too old" in desc or "query id is invalid" in desc:
                logger.debug(
                    "Skip callback answer because query expired: %s",
                    getattr(callback_query_id, "id", "unknown"),
                )
                return False
            raise

    async def delete_message(self, chat_id: Union[int, str], message_id: int) -> bool:
        """Xóa 1 message. Trả về False nếu không thể xóa (vd đã quá 48h)."""
        try:
            await self.call("deleteMessage", params={"chat_id": chat_id, "message_id": message_id})
            return True
        except TelegramAPIError as e:
            logger.debug("Không thể xóa message %s: %s", message_id, e.description)
            return False

    async def send_document(
        self,
        chat_id: Union[int, str],
        file: Any,
        *,
        filename: str,
        caption: Optional[str] = None,
        reply_to_message_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Gửi file (document) qua `sendDocument`.

        Args:
            file: Path, bytes, hoặc tuple theo định dạng aiohttp.
            filename: Tên file hiển thị trên Telegram.
            caption: Mô tả file (optional).
        """
        if isinstance(file, Path):
            file_tuple = (filename, file.open("rb"), mimetypes.guess_type(str(file))[0])
        elif isinstance(file, tuple):
            file_tuple = (filename, *self._normalize_file(file)[1:])
        else:
            file_tuple = (filename, *self._normalize_file(file)[1:])
        return await self.call_form(
            "sendDocument",
            data={
                "chat_id": chat_id,
                "caption": caption,
                "reply_to_message_id": reply_to_message_id,
            },
            files={"document": file_tuple},
        )
