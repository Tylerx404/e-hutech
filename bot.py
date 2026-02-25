#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Bot Telegram HUTECH
File chính để khởi chạy bot
"""

import logging
import asyncio

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config.config import Config
from database.db_manager import DatabaseManager
from cache.cache_manager import CacheManager
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

# Cấu hình logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
# Giảm nhiễu log polling từ HTTP client
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


class HutechBot:
    def __init__(self):
        self.config = Config()
        self.db_manager = DatabaseManager()
        self.cache_manager = CacheManager()

        # Initialize handlers
        self.login_handler = LoginHandler(self.db_manager, self.cache_manager)
        self.logout_handler = LogoutHandler(self.db_manager, self.cache_manager)
        self.tkb_handler = TkbHandler(self.db_manager, self.cache_manager)
        self.lich_thi_handler = LichThiHandler(self.db_manager, self.cache_manager)
        self.diem_handler = DiemHandler(self.db_manager, self.cache_manager)
        self.hoc_phan_handler = HocPhanHandler(self.db_manager, self.cache_manager)
        self.diem_danh_handler = DiemDanhHandler(self.db_manager, self.cache_manager)
        self.diem_danh_tat_ca_handler = DiemDanhTatCaHandler(self.db_manager, self.cache_manager)
        self.vi_tri_handler = ViTriHandler(self.db_manager)
        self.danh_sach_handler = DanhSachHandler(self.db_manager, self.cache_manager, self.logout_handler)
        self.chinh_sach_handler = ChinhSachHandler(self.db_manager, self.cache_manager)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý lệnh /start"""
        user_id = update.effective_user.id
        consented = await self.chinh_sach_handler.has_user_consented(user_id)

        if not consented:
            await update.message.reply_text(
                "Bạn cần chấp nhận chính sách bảo mật trước khi sử dụng các tính năng chính.",
                reply_to_message_id=update.message.message_id
            )
            await self.chinh_sach_handler.send_policy_prompt(update)
            return

        user = update.effective_user
        await update.message.reply_html(
            f"Chào {user.mention_html()}! Tôi là bot HUTECH.\n\n"
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
            f"/chinhsach để xem/chấp nhận chính sách bảo mật.\n"
            f"/dangxuat để đăng xuất khỏi hệ thống.",
            reply_to_message_id=update.message.message_id
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý lệnh /help"""
        user_id = update.effective_user.id
        consented = await self.chinh_sach_handler.has_user_consented(user_id)

        if not consented:
            await update.message.reply_text(
                "Bạn chưa chấp nhận chính sách. Vui lòng chọn Chấp nhận để tiếp tục sử dụng bot.",
                reply_to_message_id=update.message.message_id
            )
            await self.chinh_sach_handler.send_policy_prompt(update)
            return

        help_text = """
Các lệnh có sẵn:

/dangnhap - Đăng nhập vào hệ thống HUTECH
/danhsach - Xem danh sách tài khoản đã đăng nhập
/vitri - Cài đặt vị trí điểm danh mặc định
/diemdanh - Điểm danh cho tài khoản hiện tại
/diemdanhtatca - Điểm danh tất cả tài khoản cùng lúc
/tkb - Xem thời khóa biểu
/lichthi - Xem lịch thi
/diem - Xem điểm
/hocphan - Xem thông tin học phần
/trogiup - Hiển thị trợ giúp
/chinhsach - Xem/chấp nhận chính sách bảo mật
/dangxuat - Đăng xuất khỏi hệ thống
        """
        await update.message.reply_text(help_text, reply_to_message_id=update.message.message_id)

    def setup_handlers(self, application: Application) -> None:
        """Thiết lập các handler cho bot"""
        # Chính sách bảo mật: callback + command + guard
        self.chinh_sach_handler.register_callbacks(application, group=-2)
        self.chinh_sach_handler.register_commands(application, group=-2)
        self.chinh_sach_handler.register_guards(application, group=-1)

        # Basic commands (giữ trong bot.py)
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("trogiup", self.help_command))

        # Login conversation handler
        application.add_handler(self.login_handler.get_conversation_handler())

        # Delegate registrations to handlers
        self.logout_handler.register_commands(application)

        self.tkb_handler.register_commands(application)
        self.tkb_handler.register_callbacks(application)

        self.lich_thi_handler.register_commands(application)

        self.diem_handler.register_commands(application)
        self.diem_handler.register_callbacks(application)

        self.hoc_phan_handler.register_commands(application)
        self.hoc_phan_handler.register_callbacks(application)

        self.diem_danh_handler.register_commands(application)
        self.diem_danh_handler.register_callbacks(application)

        self.diem_danh_tat_ca_handler.register_commands(application)
        self.diem_danh_tat_ca_handler.register_callbacks(application)

        self.vi_tri_handler.register_commands(application)
        self.vi_tri_handler.register_callbacks(application)

        self.danh_sach_handler.register_commands(application)
        self.danh_sach_handler.register_callbacks(application)

    async def auto_refresh_cache_task(self):
        """Tác vụ nền tự động xóa cache của người dùng đang đăng nhập."""
        while True:
            await asyncio.sleep(600)  # Chờ 10 phút

            logged_in_users = await self.db_manager.get_all_logged_in_users()

            if logged_in_users:
                for user_id in logged_in_users:
                    await self.cache_manager.clear_user_cache(user_id, log_info=False)

    async def run(self) -> None:
        """Khởi chạy bot và quản lý vòng đời của các kết nối."""
        # Kết nối đến cơ sở dữ liệu và cache
        await self.db_manager.connect()
        await self.cache_manager.connect()

        auto_refresh_task = None
        try:
            # Tạo ứng dụng
            application = Application.builder().token(self.config.TELEGRAM_BOT_TOKEN).build()

            # Thiết lập handlers
            self.setup_handlers(application)

            # Khởi chạy bot
            logger.info("Bot đang khởi động...")

            # Chạy application.initialize() và application.start() trong background
            # để chúng ta có thể bắt tín hiệu dừng một cách chính xác
            async with application:
                await application.initialize()
                await application.start()
                await application.updater.start_polling()

                # Bắt đầu tác vụ nền
                auto_refresh_task = asyncio.create_task(self.auto_refresh_cache_task())

                # Giữ bot chạy cho đến khi nhận được tín hiệu dừng (ví dụ: Ctrl+C)
                while True:
                    await asyncio.sleep(1)

        except (KeyboardInterrupt, SystemExit):
            logger.info("Đang dừng bot...")
        finally:
            # Hủy tác vụ nền
            if auto_refresh_task:
                auto_refresh_task.cancel()

            # Đảm bảo đóng các kết nối khi bot dừng
            if application.updater and application.updater.running:
                await application.updater.stop()
            await application.stop()
            await application.shutdown()

            await self.db_manager.close()
            await self.cache_manager.close()
            logger.info("Bot đã dừng và đóng các kết nối.")


async def main() -> None:
    """Hàm main bất đồng bộ để chạy bot."""
    bot = HutechBot()
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
