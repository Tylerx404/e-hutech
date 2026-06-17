#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Bot Telegram HUTECH - entrypoint.

Gọi trực tiếp `https://api.telegram.org/bot<TOKEN>/<METHOD>` qua aiohttp,
không qua thư viện python-telegram-bot.

Cơ chế:
- Long-polling getUpdates với offset + exponential backoff
- Tự dispatch update: command / text / callback
- State tạm per user lưu trong Redis (qua utils/state_store)
- Instance lock qua DatabaseManager để chỉ 1 instance bot chạy polling
- Tác vụ nền: auto refresh cache mỗi 10 phút
"""

import asyncio
import hashlib
import logging
import signal
from contextlib import suppress
from typing import Any, Dict, List, Optional

from config.config import Config
from database.db_manager import DatabaseManager
from cache.cache_manager import CacheManager
from utils.logging_config import setup_logging
from utils.state_store import StateStore
from utils.telegram_api import TelegramAPI, TelegramAPIError, DEFAULT_ALLOWED_UPDATES

from handlers.login_handler import LoginHandler
from handlers.logout_handler import LogoutHandler
from handlers.tkb_handler import TkbHandler
from handlers.lich_thi_handler import LichThiHandler
from handlers.diem_handler import DiemHandler
from handlers.hoc_phan_handler import HocPhanHandler
from handlers.diem_danh_handler import DiemDanhHandler
from handlers.diem_danh_tat_ca_handler import DiemDanhTatCaHandler
from handlers.danh_sach_handler import DanhSachHandler
from handlers.vi_tri_handler import ViTriHandler
from handlers.chinh_sach_handler import ChinhSachHandler

setup_logging()
logger = logging.getLogger(__name__)


class HutechBot:
    def __init__(self) -> None:
        self.config = Config()
        self.db_manager = DatabaseManager()
        self.cache_manager = CacheManager()
        self.telegram = TelegramAPI(self.config)
        self.state = StateStore(self.cache_manager)

        # Handlers
        self.login_handler = LoginHandler(self.db_manager, self.cache_manager, self.telegram)
        self.logout_handler = LogoutHandler(self.db_manager, self.cache_manager, self.telegram)
        self.tkb_handler = TkbHandler(self.db_manager, self.cache_manager, self.telegram)
        self.lich_thi_handler = LichThiHandler(self.db_manager, self.cache_manager, self.telegram)
        self.diem_handler = DiemHandler(self.db_manager, self.cache_manager, self.telegram)
        self.hoc_phan_handler = HocPhanHandler(self.db_manager, self.cache_manager, self.telegram)
        self.diem_danh_handler = DiemDanhHandler(self.db_manager, self.cache_manager, self.telegram)
        self.diem_danh_tat_ca_handler = DiemDanhTatCaHandler(
            self.db_manager, self.cache_manager, self.telegram
        )
        self.vi_tri_handler = ViTriHandler(self.db_manager, self.telegram)
        self.danh_sach_handler = DanhSachHandler(
            self.db_manager, self.cache_manager, self.logout_handler, self.telegram
        )
        self.chinh_sach_handler = ChinhSachHandler(
            self.db_manager, self.cache_manager, self.telegram
        )

        self._stop_event = asyncio.Event()
        self._auto_refresh_task: Optional[asyncio.Task] = None

    # ==================== Lifecycle ====================

    async def run(self) -> None:
        await self.db_manager.connect()
        await self.cache_manager.connect()
        await self.telegram.start()

        lock_key = self._build_instance_lock_key(self.config.TELEGRAM_BOT_TOKEN)
        acquired = await self.db_manager.acquire_bot_instance_lock(lock_key)
        if not acquired:
            logger.error(
                "Phát hiện instance bot khác đang chạy (lock key=%s). Thoát.", lock_key
            )
            await self._cleanup()
            return

        try:
            await self._run_polling_loop()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Đang dừng bot...")
        except Exception:
            logger.exception("Bot crashed unexpectedly.")
            raise
        finally:
            await self._cleanup()

    async def _cleanup(self) -> None:
        if self._auto_refresh_task and not self._auto_refresh_task.done():
            self._auto_refresh_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._auto_refresh_task
        await self.telegram.close()
        await self.db_manager.close()
        await self.cache_manager.close()
        logger.info("Bot đã dừng và đóng các kết nối.")

    @staticmethod
    def _build_instance_lock_key(bot_token: str) -> int:
        digest = hashlib.blake2b(bot_token.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, byteorder="big", signed=True)

    # ==================== Polling ====================

    async def _run_polling_loop(self) -> None:
        backoff = 1
        offset: Optional[int] = None
        try:
            me = await self.telegram.get_me()
            logger.info("Bot đang chạy: @%s (id=%s)", me.get("username"), me.get("id"))
        except Exception as e:
            logger.warning("Không thể gọi getMe lúc khởi động: %s", e)

        self._auto_refresh_task = asyncio.create_task(self._auto_refresh_cache_task())

        while not self._stop_event.is_set():
            try:
                updates = await self.telegram.get_updates(
                    offset=offset,
                    limit=100,
                    allowed_updates=DEFAULT_ALLOWED_UPDATES,
                )
                backoff = 1  # Reset backoff khi thành công
                for update in updates:
                    offset = update["update_id"] + 1
                    try:
                        await self._dispatch(update)
                    except Exception:
                        logger.exception(
                            "Lỗi xử lý update_id=%s", update.get("update_id")
                        )
            except TelegramAPIError as e:
                logger.warning("Telegram API error, retry sau %ss: %s", backoff, e.description)
                await self._sleep_or_stop(backoff)
                backoff = min(backoff * 2, 30)

    async def _sleep_or_stop(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            return

    # ==================== Dispatch ====================

    async def _dispatch(self, update: Dict[str, Any]) -> None:
        # 1. Callback query
        if "callback_query" in update:
            await self._handle_callback(update["callback_query"])
            return

        # 2. Message
        if "message" in update:
            await self._handle_message(update["message"])
            return

        # 3. edited_message - hiện không xử lý
        # 4. my_chat_member - hiện không xử lý

    async def _handle_message(self, message: Dict[str, Any]) -> None:
        chat = message.get("chat") or {}
        from_user = message.get("from") or {}
        chat_id = chat.get("id")
        user_id = from_user.get("id")
        text = (message.get("text") or "").strip()
        message_id = message.get("message_id")

        if chat_id is None or user_id is None:
            return

        # Nếu user có state login (text message không phải command) → xử lý login
        st = await self.state.get_state(user_id)
        if st and st.get("step") in ("awaiting_username", "awaiting_password") and not text.startswith("/"):
            handled = await self.login_handler.on_user_text(chat_id, user_id, text, message_id)
            if handled:
                return

        # Nếu là command
        if text.startswith("/"):
            await self._handle_command(chat_id, user_id, text, message_id)
            return

        # Text không phải command và không trong state → bỏ qua
        logger.debug("Bỏ qua text message không xử lý: %s", text[:50])

    async def _handle_command(self, chat_id: int, user_id: int, text: str, message_id: int) -> None:
        # Tách command và args
        parts = text.split()
        cmd = parts[0][1:].split("@")[0].lower()  # bỏ / và bot username
        args = parts[1:]

        # Guard chính sách
        if await self.chinh_sach_handler.check_command_guard(user_id, cmd):
            await self.telegram.send_message(
                chat_id=chat_id,
                text="Bạn cần chấp nhận chính sách bảo mật trước khi dùng lệnh này.",
                reply_to_message_id=message_id,
            )
            await self.chinh_sach_handler.cmd_chinhsach(chat_id, user_id, message_id)
            return

        reply_to = message_id
        if cmd == "start":
            await self._cmd_start(chat_id, user_id, reply_to)
        elif cmd == "trogiup" or cmd == "help":
            await self._cmd_help(chat_id, reply_to)
        elif cmd == "dangnhap":
            await self.login_handler.start(chat_id, user_id, reply_to)
        elif cmd == "dangxuat":
            await self.logout_handler.handle(chat_id, user_id, reply_to)
        elif cmd == "tkb":
            await self.tkb_handler.cmd_tkb(chat_id, user_id, args, reply_to)
        elif cmd == "lichthi":
            await self.lich_thi_handler.cmd_lichthi(chat_id, user_id, reply_to)
        elif cmd == "diem":
            await self.diem_handler.cmd_diem(chat_id, user_id, reply_to)
        elif cmd == "hocphan":
            await self.hoc_phan_handler.cmd_hocphan(chat_id, user_id, reply_to)
        elif cmd == "diemdanh":
            await self.diem_danh_handler.cmd_diemdanh(chat_id, user_id, reply_to)
        elif cmd == "diemdanhtatca":
            await self.diem_danh_tat_ca_handler.cmd_diemdanhtatca(chat_id, user_id, reply_to)
        elif cmd == "vitri":
            await self.vi_tri_handler.cmd_vitri(chat_id, user_id, reply_to)
        elif cmd == "danhsach":
            await self.danh_sach_handler.cmd_danhsach(chat_id, user_id, reply_to)
        elif cmd == "chinhsach":
            await self.chinh_sach_handler.cmd_chinhsach(chat_id, user_id, reply_to)
        else:
            await self.telegram.send_message(
                chat_id=chat_id,
                text=f"Lệnh không tồn tại. Dùng /trogiup để xem danh sách lệnh.",
                reply_to_message_id=reply_to,
            )

    async def _handle_callback(self, callback_query: Dict[str, Any]) -> None:
        callback_id = callback_query.get("id")
        from_user = callback_query.get("from") or {}
        message = callback_query.get("message") or {}
        user_id = from_user.get("id")
        chat_id = (message.get("chat") or {}).get("id")
        message_id = message.get("message_id")
        callback_data = callback_query.get("data") or ""

        if not callback_id or user_id is None or chat_id is None or message_id is None:
            return

        # Guard chính sách
        if await self.chinh_sach_handler.check_callback_guard(user_id, callback_data):
            await self.telegram.answer_callback_query(
                callback_id, text="Bạn cần chấp nhận chính sách trước khi sử dụng bot.",
                show_alert=True,
            )
            return

        try:
            if callback_data.startswith("consent_"):
                await self.chinh_sach_handler.cb_consent(
                    callback_id, chat_id, message_id, user_id, callback_data
                )
            elif callback_data.startswith("diemdanh_campus_"):
                await self.diem_danh_handler.cb_campus(
                    callback_id, chat_id, message_id, user_id, callback_data
                )
            elif callback_data.startswith("num_") and not callback_data.startswith("num_tatca_"):
                await self.diem_danh_handler.cb_numeric(
                    callback_id, chat_id, message_id, user_id, callback_data
                )
            elif callback_data.startswith("diemdanhtatca_campus_"):
                await self.diem_danh_tat_ca_handler.cb_campus(
                    callback_id, chat_id, message_id, user_id, callback_data
                )
            elif callback_data.startswith("num_tatca_"):
                await self.diem_danh_tat_ca_handler.cb_numeric(
                    callback_id, chat_id, message_id, user_id, callback_data
                )
            elif callback_data.startswith("vitri_"):
                await self.vi_tri_handler.cb_handle(
                    callback_id, chat_id, message_id, user_id, callback_data
                )
            elif callback_data.startswith("switch_account_"):
                await self.danh_sach_handler.cb_switch(
                    callback_id, chat_id, message_id, user_id, callback_data
                )
            elif callback_data.startswith("tkb_"):
                await self.tkb_handler.cb_route(
                    callback_id, chat_id, message_id, user_id, callback_data
                )
            elif callback_data.startswith("diem_"):
                await self.diem_handler.cb_route(
                    callback_id, chat_id, message_id, user_id, callback_data
                )
            elif (
                callback_data.startswith("namhoc_")
                or callback_data.startswith("hocphan_")
                or callback_data.startswith("danhsach_")
                or callback_data.startswith("diemdanh_lop_hoc_phan_")
            ):
                await self.hoc_phan_handler.cb_route(
                    callback_id, chat_id, message_id, user_id, callback_data
                )
            else:
                await self.telegram.answer_callback_query(callback_id)
                logger.debug("Callback không xử lý: %s", callback_data)
        except TelegramAPIError as e:
            logger.warning("Lỗi khi xử lý callback: %s", e.description)
        except Exception:
            logger.exception("Lỗi không xác định khi xử lý callback data=%s", callback_data)

    # ==================== Commands ====================

    async def _cmd_start(self, chat_id: int, user_id: int, reply_to_message_id: Optional[int]) -> None:
        from_user_first_name = ""
        # Lấy first name từ start message (gọi lại getUpdates thì tốn kém; bỏ qua)
        message = (
            f"Chào bạn! Tôi là bot HUTECH.\n\n"
            f"/dangnhap để đăng nhập vào hệ thống HUTECH.\n"
            f"/danhsach để xem danh sách tài khoản đã đăng nhập.\n"
            f"/vitri để cài đặt vị trí điểm danh mặc định.\n"
            f"/diemdanh để điểm danh cho tài khoản hiện tại.\n"
            f"/diemdanhtatca để điểm danh tất cả tài khoản cùng lúc.\n"
            f"/tkb để xem thời khóa biểu của bạn.\n"
            f"/lichthi để xem lịch thi của bạn.\n"
            f"/diem để xem điểm của bạn.\n"
            f"/hocphan để xem thông tin học phần.\n"
            f"/trogiup để xem các lệnh có sẵn.\n"
            f"/chinhsach để xem chính sách bảo mật.\n"
            f"/dangxuat để đăng xuất khỏi hệ thống."
        )
        await self.telegram.send_message(
            chat_id=chat_id, text=message, reply_to_message_id=reply_to_message_id
        )

    async def _cmd_help(self, chat_id: int, reply_to_message_id: Optional[int]) -> None:
        help_text = (
            "Các lệnh có sẵn:\n\n"
            "/dangnhap - Đăng nhập vào hệ thống HUTECH\n"
            "/danhsach - Xem danh sách tài khoản đã đăng nhập\n"
            "/vitri - Cài đặt vị trí điểm danh mặc định\n"
            "/diemdanh - Điểm danh cho tài khoản hiện tại\n"
            "/diemdanhtatca - Điểm danh tất cả tài khoản cùng lúc\n"
            "/tkb - Xem thời khóa biểu\n"
            "/lichthi - Xem lịch thi\n"
            "/diem - Xem điểm\n"
            "/hocphan - Xem thông tin học phần\n"
            "/trogiup - Hiển thị trợ giúp\n"
            "/chinhsach - Xem chính sách bảo mật\n"
            "/dangxuat - Đăng xuất khỏi hệ thống"
        )
        await self.telegram.send_message(
            chat_id=chat_id, text=help_text, reply_to_message_id=reply_to_message_id
        )

    # ==================== Background task ====================

    async def _auto_refresh_cache_task(self) -> None:
        """Tác vụ nền tự động xóa cache của người dùng đang đăng nhập mỗi 10 phút."""
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=600)
                return
            except asyncio.TimeoutError:
                try:
                    logged_in_users = await self.db_manager.get_all_logged_in_users()
                    for user_id in logged_in_users:
                        await self.cache_manager.clear_user_cache(user_id, log_info=False)
                except Exception:
                    logger.exception("Lỗi trong tác vụ auto refresh cache.")


async def main() -> None:
    bot = HutechBot()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, bot._stop_event.set)
        except (NotImplementedError, RuntimeError):
            # Windows không hỗ trợ add_signal_handler cho SIGTERM; bỏ qua
            pass

    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
