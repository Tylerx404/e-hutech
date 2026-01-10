#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Bot Telegram HUTECH
File chính để khởi chạy bot
"""

import logging
import os
import sys
import asyncio
from pathlib import Path


from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler

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
from utils.utils import generate_uuid

# Cấu hình logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Các trạng thái cho conversation handler
USERNAME, PASSWORD = range(2)

class HutechBot:
    def __init__(self):
        self.config = Config()
        self.db_manager = DatabaseManager()
        self.cache_manager = CacheManager()
        self.login_handler = LoginHandler(self.db_manager, self.cache_manager)
        self.logout_handler = LogoutHandler(self.db_manager, self.cache_manager)
        self.tkb_handler = TkbHandler(self.db_manager, self.cache_manager)
        self.lich_thi_handler = LichThiHandler(self.db_manager, self.cache_manager)
        self.diem_handler = DiemHandler(self.db_manager, self.cache_manager)
        self.hoc_phan_handler = HocPhanHandler(self.db_manager, self.cache_manager)
        self.diem_danh_handler = DiemDanhHandler(self.db_manager, self.cache_manager)
        
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý lệnh /start"""
        user = update.effective_user
        await update.message.reply_html(
            f"Chào {user.mention_html()}! Tôi là bot HUTECH.\n\n"
            f"/dangnhap để đăng nhập vào hệ thống HUTECH.\n"
            f"/diemdanh để điểm danh.\n"
            f"/tkb để xem thời khóa biểu của bạn.\n"
            f"/lichthi để xem lịch thi của bạn.\n"
            f"/diem để xem điểm của bạn.\n"
            f"/hocphan để xem thông tin học phần.\n"
            f"/huy để hủy quá trình đang thực hiện.\n"
            f"/trogiup để xem các lệnh có sẵn.\n"
            f"/dangxuat để đăng xuất khỏi hệ thống.",
            reply_to_message_id=update.message.message_id
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý lệnh /help"""
        help_text = """
Các lệnh có sẵn:

/dangnhap - Đăng nhập vào hệ thống HUTECH
/diemdanh - Điểm danh
/tkb - Xem thời khóa biểu
/lichthi - Xem lịch thi
/diem - Xem điểm
/hocphan - Xem thông tin học phần
/huy - Hủy quá trình đang thực hiện
/trogiup - Hiển thị trợ giúp
/dangxuat - Đăng xuất khỏi hệ thống
        """
        await update.message.reply_text(help_text, reply_to_message_id=update.message.message_id)
    
    async def login_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Bắt đầu quá trình đăng nhập"""
        user_id = update.effective_user.id
        
        # Kiểm tra xem người dùng đã đăng nhập chưa
        if await self.db_manager.is_user_logged_in(user_id):
            await update.message.reply_text("Bạn đã đăng nhập rồi. /dangxuat để đăng xuất trước.", reply_to_message_id=update.message.message_id)
            return ConversationHandler.END
        
        # Gửi tin nhắn yêu cầu nhập tài khoản và lưu message_id để xóa sau này
        sent_message = await update.message.reply_text("Vui lòng nhập tên tài khoản HUTECH của bạn:", reply_to_message_id=update.message.message_id)
        context.user_data["username_prompt_message_id"] = sent_message.message_id
        return USERNAME
    
    async def username_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Nhận tên tài khoản từ người dùng"""
        context.user_data["username"] = update.message.text
        
        # Xóa tin nhắn chứa tài khoản
        try:
            await update.message.delete()
        except Exception as e:
            logger.warning(f"Không thể xóa tin nhắn: {e}")
        
        # Xóa tin nhắn yêu cầu nhập tài khoản
        try:
            username_prompt_message_id = context.user_data.get("username_prompt_message_id")
            if username_prompt_message_id:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=username_prompt_message_id
                )
        except Exception as e:
            logger.warning(f"Không thể xóa tin nhắn yêu cầu nhập tài khoản: {e}")
        
        # Gửi tin nhắn yêu cầu nhập mật khẩu và lưu message_id để xóa sau này
        sent_message = await update.message.reply_text("Vui lòng nhập mật khẩu của bạn:")
        context.user_data["password_prompt_message_id"] = sent_message.message_id
        return PASSWORD
    
    async def password_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Nhận mật khẩu từ người dùng và thực hiện đăng nhập"""
        username = context.user_data.get("username")
        password = update.message.text
        
        # Xóa tin nhắn chứa mật khẩu
        try:
            await update.message.delete()
        except Exception as e:
            logger.warning(f"Không thể xóa tin nhắn: {e}")
        
        # Xóa tin nhắn yêu cầu nhập mật khẩu
        try:
            password_prompt_message_id = context.user_data.get("password_prompt_message_id")
            if password_prompt_message_id:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=password_prompt_message_id
                )
        except Exception as e:
            logger.warning(f"Không thể xóa tin nhắn yêu cầu nhập mật khẩu: {e}")
        
        user_id = update.effective_user.id
        device_uuid = generate_uuid()
        
        # Thực hiện đăng nhập
        result = await self.login_handler.handle_login(user_id, username, password, device_uuid)
        
        if result["success"]:
            await update.message.reply_text("Đăng nhập thành công!")
        else:
            await update.message.reply_text(f"Đăng nhập thất bại: {result['message']}", reply_to_message_id=update.message.message_id)
        
        # Xóa dữ liệu tạm thời
        context.user_data.clear()
        
        return ConversationHandler.END
    
    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Hủy quá trình đang thực hiện"""
        # Kiểm tra xem có lệnh đang hoạt động không
        has_active_command = False
        
        # Kiểm tra xem người dùng có đang trong conversation đăng nhập không
        if context.user_data.get("username_prompt_message_id") or context.user_data.get("password_prompt_message_id"):
            has_active_command = True
            # Xóa tin nhắn yêu cầu nhập tài khoản nếu có
            try:
                username_prompt_message_id = context.user_data.get("username_prompt_message_id")
                if username_prompt_message_id:
                    await context.bot.delete_message(
                        chat_id=update.effective_chat.id,
                        message_id=username_prompt_message_id
                    )
            except Exception as e:
                logger.warning(f"Không thể xóa tin nhắn yêu cầu nhập tài khoản: {e}")
            
            # Xóa tin nhắn yêu cầu nhập mật khẩu nếu có
            try:
                password_prompt_message_id = context.user_data.get("password_prompt_message_id")
                if password_prompt_message_id:
                    await context.bot.delete_message(
                        chat_id=update.effective_chat.id,
                        message_id=password_prompt_message_id
                    )
            except Exception as e:
                logger.warning(f"Không thể xóa tin nhắn yêu cầu nhập mật khẩu: {e}")
        
        # Kiểm tra xem người dùng có đang trong quá trình điểm danh không
        if context.user_data.get("selected_campus") or context.user_data.get("numeric_input"):
            has_active_command = True
        
        # Nếu không có lệnh đang hoạt động
        if not has_active_command:
            await update.message.reply_text("Hiện tại không có lệnh nào đang hoạt động để hủy.", reply_to_message_id=update.message.message_id)
            return ConversationHandler.END
        
        # Xóa dữ liệu tạm thời
        context.user_data.clear()
        await update.message.reply_text("Quá trình đang thực hiện đã bị hủy.", reply_to_message_id=update.message.message_id)
        return ConversationHandler.END
    
    async def logout_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý lệnh /logout"""
        user_id = update.effective_user.id
        
        # Kiểm tra xem người dùng đã đăng nhập chưa
        if not await self.db_manager.is_user_logged_in(user_id):
            await update.message.reply_text("Bạn chưa đăng nhập.", reply_to_message_id=update.message.message_id)
            return
        
        # Thực hiện đăng xuất
        result = await self.logout_handler.handle_logout(user_id)
        
        if result["success"]:
            await update.message.reply_text("Đăng xuất thành công!", reply_to_message_id=update.message.message_id)
        else:
            await update.message.reply_text(f"Đăng xuất thất bại: {result['message']}", reply_to_message_id=update.message.message_id)
    
    async def tkb_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý lệnh /tkb"""
        user_id = update.effective_user.id
        
        # Kiểm tra xem người dùng đã đăng nhập chưa
        if not await self.db_manager.is_user_logged_in(user_id):
            await update.message.reply_text("Bạn chưa đăng nhập. Vui lòng /dangnhap để đăng nhập.", reply_to_message_id=update.message.message_id)
            return
        
        # Lấy tuần offset từ context (nếu có)
        week_offset = 0
        if context.args:
            try:
                week_offset = int(context.args[0])
            except (ValueError, IndexError):
                week_offset = 0
        
        # Lấy thời khóa biểu
        result = await self.tkb_handler.handle_tkb(user_id, week_offset)
        
        if result["success"]:
            # Định dạng dữ liệu thời khóa biểu
            message = self.tkb_handler.format_tkb_message(result["data"])
            
            # Tạo keyboard cho các nút điều hướng
            keyboard = [
                [
                    InlineKeyboardButton("⬅️ Tuần trước", callback_data=f"tkb_{week_offset-1}"),
                    InlineKeyboardButton("Tuần hiện tại", callback_data=f"tkb_0"),
                    InlineKeyboardButton("Tuần tới ➡️", callback_data=f"tkb_{week_offset+1}")
                ],
                [
                    InlineKeyboardButton("🗓️ Xuất ra iCalendar (.ics)", callback_data="tkb_export_ics")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            sent_message = await update.message.reply_text(
                message,
                reply_markup=reply_markup,
                parse_mode="Markdown",
                reply_to_message_id=update.message.message_id
            )
            # Lưu ID của tin nhắn lệnh gốc và tin nhắn trả lời của bot
            context.user_data['tkb_command_message_id'] = update.message.message_id
            context.user_data['tkb_reply_message_id'] = sent_message.message_id
        else:
            await update.message.reply_text(f"Không thể lấy thời khóa biểu: {result['message']}", reply_to_message_id=update.message.message_id, parse_mode="Markdown")
    
    async def lich_thi_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý lệnh /lichthi"""
        user_id = update.effective_user.id
        
        # Kiểm tra xem người dùng đã đăng nhập chưa
        if not await self.db_manager.is_user_logged_in(user_id):
            await update.message.reply_text("Bạn chưa đăng nhập. Vui lòng /dangnhap để đăng nhập.", reply_to_message_id=update.message.message_id)
            return
        
        # Lấy lịch thi
        result = await self.lich_thi_handler.handle_lich_thi(user_id)
        
        if result["success"]:
            # Định dạng dữ liệu lịch thi
            message = self.lich_thi_handler.format_lich_thi_message(result["data"])
            
            await update.message.reply_text(
                message,
                parse_mode="Markdown",
                reply_to_message_id=update.message.message_id
            )
        else:
            await update.message.reply_text(f"Không thể lấy lịch thi: {result.get('message', 'Lỗi không xác định')}", reply_to_message_id=update.message.message_id, parse_mode="Markdown")

    
    async def diem_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý lệnh /diem"""
        user_id = update.effective_user.id
        
        # Kiểm tra xem người dùng đã đăng nhập chưa
        if not await self.db_manager.is_user_logged_in(user_id):
            await update.message.reply_text("Bạn chưa đăng nhập. Vui lòng /dangnhap để đăng nhập.", reply_to_message_id=update.message.message_id)
            return
        
        # Lấy điểm
        result = await self.diem_handler.handle_diem(user_id)
        
        if result["success"]:
            # Định dạng dữ liệu điểm thành menu
            message = self.diem_handler.format_diem_menu_message(result["data"])
            
            # Tạo keyboard cho các nút chọn học kỳ
            hocky_list = self.diem_handler.get_hocky_list(result["data"])
            keyboard = []
            
            # Thêm các nút chọn học kỳ (mỗi nút một hàng)
            for hocky in hocky_list:
                keyboard.append([InlineKeyboardButton(hocky["name"], callback_data=f"diem_{hocky['key']}")])
            
            # Thêm nút xuất Excel
            keyboard.append([InlineKeyboardButton("📄 Xuất Excel toàn bộ", callback_data="diem_export_all")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                message,
                reply_markup=reply_markup,
                parse_mode="Markdown",
                reply_to_message_id=update.message.message_id
            )
        else:
            await update.message.reply_text(f"Không thể lấy điểm: {result['message']}", reply_to_message_id=update.message.message_id, parse_mode="Markdown")
    
    async def hoc_phan_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý lệnh /hocphan"""
        user_id = update.effective_user.id
        
        # Kiểm tra xem người dùng đã đăng nhập chưa
        if not await self.db_manager.is_user_logged_in(user_id):
            await update.message.reply_text("Bạn chưa đăng nhập. Vui lòng /dangnhap để đăng nhập.", reply_to_message_id=update.message.message_id)
            return
        
        # Lấy danh sách năm học - học kỳ
        result = await self.hoc_phan_handler.handle_hoc_phan(user_id)
        
        if result["success"]:
            # Định dạng dữ liệu năm học - học kỳ thành menu
            message = self.hoc_phan_handler.format_nam_hoc_hoc_ky_message(result["data"])
            
            # Tạo keyboard cho các nút chọn năm học - học kỳ
            nam_hoc_hoc_ky_list = self.hoc_phan_handler.get_nam_hoc_hoc_ky_list(result["data"])
            keyboard = []
            
            # Thêm các nút chọn năm học - học kỳ (tối đa 3 nút mỗi hàng)
            row = []
            for i, nam_hoc_hoc_ky in enumerate(nam_hoc_hoc_ky_list):
                row.append(InlineKeyboardButton(nam_hoc_hoc_ky["name"], callback_data=f"namhoc_{nam_hoc_hoc_ky['key']}"))
                if len(row) == 3 or i == len(nam_hoc_hoc_ky_list) - 1:
                    keyboard.append(row)
                    row = []
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                message,
                reply_markup=reply_markup,
                parse_mode="Markdown",
                reply_to_message_id=update.message.message_id
            )
        else:
            await update.message.reply_text(f"Không thể lấy danh sách năm học - học kỳ: {result['message']}", reply_to_message_id=update.message.message_id, parse_mode="Markdown")
    
    async def diemdanh_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý lệnh /diemdanh"""
        user_id = update.effective_user.id
        
        # Kiểm tra xem người dùng đã đăng nhập chưa
        if not await self.db_manager.is_user_logged_in(user_id):
            await update.message.reply_text("Bạn chưa đăng nhập. Vui lòng /dangnhap để đăng nhập.", reply_to_message_id=update.message.message_id)
            return
        
        # Lấy danh sách campus để hiển thị menu
        result = await self.diem_danh_handler.handle_diem_danh_menu(user_id)
        
        if result["success"]:
            # Định dạng dữ liệu campus thành menu
            message = self.diem_danh_handler.format_campus_menu_message()
            
            # Tạo keyboard cho các nút chọn campus
            keyboard = self.diem_danh_handler.format_campus_keyboard()
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                message,
                reply_markup=reply_markup,
                parse_mode="Markdown",
                reply_to_message_id=update.message.message_id
            )
        else:
            await update.message.reply_text(f"Không thể hiển thị menu campus: {result['message']}", reply_to_message_id=update.message.message_id, parse_mode="Markdown")
    
    async def diemdanh_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý callback từ các nút chọn campus"""
        query = update.callback_query
        user_id = query.from_user.id
        
        # Lấy callback_data
        callback_data = query.data
        
        if callback_data.startswith("diemdanh_campus_"):
            campus_name = callback_data[16:]  # Bỏ "diemdanh_campus_" prefix
            
            # Hiển thị thông báo đang xử lý
            await query.answer("Đang chuẩn bị điểm danh...")
            
            # Lưu campus đã chọn vào context
            context.user_data["selected_campus"] = campus_name
            
            # Hiển thị tin nhắn yêu cầu nhập mã QR với bàn phím số
            message = self.diem_danh_handler.format_diem_danh_numeric_message(campus_name)
            
            # Tạo bàn phím số
            keyboard = self.diem_danh_handler.format_diem_danh_numeric_keyboard()
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Hiển thị trạng thái nhập số hiện tại
            display = self.diem_danh_handler.format_diem_danh_numeric_display("")
            
            # Gửi tin nhắn mới với yêu cầu nhập mã QR và bàn phím số
            await query.edit_message_text(
                text=f"{message}\n\n{display}",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            
            # Lưu trạng thái nhập số
            context.user_data["numeric_input"] = ""
            context.user_data["numeric_message_id"] = query.message.message_id
        elif callback_data.startswith("diemdanh_lop_hoc_phan_"):
            # Xử lý khi chọn điểm danh
            key_lop_hoc_phan = callback_data.split("diemdanh_lop_hoc_phan_")[1]
            
            # Hiển thị thông báo đang xử lý
            await query.answer("Đang tải lịch sử điểm danh...")
            
            # Lấy lịch sử điểm danh
            result = await self.hoc_phan_handler.handle_diem_danh(user_id, key_lop_hoc_phan)
            
            if result["success"]:
                # Định dạng lịch sử điểm danh
                message = self.hoc_phan_handler.format_diem_danh_message(result["data"])
                
                # Tạo keyboard cho các chức năng
                keyboard = [
                    [
                        InlineKeyboardButton("⬅️ Quay lại", callback_data="hocphan_back")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    text=message,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text(f"Không thể lấy lịch sử điểm danh: {result['message']}", parse_mode="Markdown")
    
    async def diemdanh_code_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Nhận mã QR từ người dùng và thực hiện điểm danh"""
        user_id = update.effective_user.id
        code = update.message.text.strip()

        # Kiểm tra xem người dùng có đang trong trạng thái điểm danh không
        if "selected_campus" not in context.user_data:
            # Người dùng không đang trong trạng thái điểm danh, bỏ qua
            return

        # Lấy campus đã chọn và message_id của menu
        campus_name = context.user_data.get("selected_campus")
        numeric_message_id = context.user_data.get("numeric_message_id")

        if not campus_name:
            await update.message.reply_text("Lỗi: Không tìm thấy campus đã chọn. Vui lòng thử lại.", reply_to_message_id=update.message.message_id)
            return

        # Xóa tin nhắn chứa mã QR của người dùng
        try:
            await update.message.delete()
        except Exception as e:
            logger.warning(f"Không thể xóa tin nhắn mã QR: {e}")

        # Kiểm tra mã điểm danh
        if not code.isdigit() or len(code) != 4:
            # Xóa tin nhắn menu cũ
            if numeric_message_id:
                try:
                    await context.bot.delete_message(
                        chat_id=update.effective_chat.id,
                        message_id=numeric_message_id
                    )
                except Exception as e:
                    logger.warning(f"Không thể xóa tin nhắn menu điểm danh: {e}")
            
            # Gửi thông báo lỗi và lưu message_id
            error_message = await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Mã điểm danh phải là 4 chữ số. Vui lòng nhập lại."
            )
            context.user_data["diemdanh_error_message_id"] = error_message.message_id

            # Gửi lại menu nhập mã
            message = self.diem_danh_handler.format_diem_danh_numeric_message(campus_name)
            keyboard = self.diem_danh_handler.format_diem_danh_numeric_keyboard()
            reply_markup = InlineKeyboardMarkup(keyboard)
            display = self.diem_danh_handler.format_diem_danh_numeric_display("")
            
            new_menu_message = await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"{message}\n\n{display}",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            context.user_data["numeric_message_id"] = new_menu_message.message_id
            context.user_data["numeric_input"] = ""
            return

        # Xóa tin nhắn lỗi nếu có
        error_message_id = context.user_data.pop("diemdanh_error_message_id", None)
        if error_message_id:
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=error_message_id
                )
            except Exception as e:
                logger.warning(f"Không thể xóa tin nhắn lỗi điểm danh: {e}")

        # Xóa tin nhắn menu bàn phím số
        if numeric_message_id:
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=numeric_message_id
                )
            except Exception as e:
                logger.warning(f"Không thể xóa tin nhắn menu điểm danh: {e}")

        # Gửi tin nhắn tạm thời
        processing_message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Đang gửi mã điểm danh..."
        )

        # Thực hiện điểm danh
        result = await self.diem_danh_handler.handle_submit_diem_danh(user_id, code, campus_name)

        # Cập nhật tin nhắn với kết quả
        try:
            if result["success"]:
                if result.get("has_status_code", False):
                    await processing_message.edit_text(result['message'], parse_mode="Markdown")
                else:
                    await processing_message.edit_text(f"✅ {result['message']}")
            else:
                await processing_message.edit_text(result['message'], parse_mode="Markdown")
        except Exception:
            # Nếu lỗi parse Markdown, gửi lại dưới dạng text thường
            await processing_message.edit_text(result['message'])

        # Xóa dữ liệu tạm thời
        context.user_data.clear()
    
    async def diemdanh_numeric_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý callback từ bàn phím số"""
        query = update.callback_query
        user_id = query.from_user.id
        
        # Lấy callback_data
        callback_data = query.data
        
        # Lấy trạng thái nhập số hiện tại
        current_input = context.user_data.get("numeric_input", "")
        
        if callback_data.startswith("num_"):
            # Xử lý các nút số
            if callback_data == "num_exit":
                # Thoát khỏi menu điểm danh
                await query.edit_message_text("Đã hủy điểm danh.")
                context.user_data.clear()
                return
            elif callback_data == "num_delete":
                # Xóa ký tự cuối cùng
                if len(current_input) > 0:
                    current_input = current_input[:-1]
            else:
                # Thêm số vào chuỗi hiện tại
                digit = callback_data[4:]
                if len(current_input) < 4:
                    current_input += digit

            # Cập nhật trạng thái nhập số
            context.user_data["numeric_input"] = current_input

            # Nếu đã nhập đủ 4 số, tự động gửi
            if len(current_input) == 4:
                campus_name = context.user_data.get("selected_campus")
                if campus_name:
                    # Hiển thị thông báo đang gửi
                    await query.edit_message_text("Đang gửi mã điểm danh...")
                    
                    result = await self.diem_danh_handler.handle_submit_diem_danh(user_id, current_input, campus_name)
                    
                    if result["success"]:
                        if result.get("has_status_code", False):
                            await query.edit_message_text(result['message'], parse_mode="Markdown")
                        else:
                            await query.edit_message_text(f"✅ {result['message']}")
                    else:
                        await query.edit_message_text(result['message'], parse_mode="Markdown")
                    
                    context.user_data.clear()
                    return
                else:
                    await query.edit_message_text("❌ Lỗi: Không tìm thấy campus đã chọn.")
                    return

            # Cập nhật hiển thị
            display = self.diem_danh_handler.format_diem_danh_numeric_display(current_input)
            campus_name = context.user_data.get("selected_campus", "Campus")
            message = self.diem_danh_handler.format_diem_danh_numeric_message(campus_name)
            keyboard = self.diem_danh_handler.format_diem_danh_numeric_keyboard()
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                text=f"{message}\n\n{display}",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )

        await query.answer()
    
    async def hoc_phan_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý callback từ các nút chọn năm học - học kỳ"""
        query = update.callback_query
        user_id = query.from_user.id
        
        # Lấy callback_data
        callback_data = query.data
        
        if callback_data.startswith("namhoc_"):
            nam_hoc_key = callback_data[7:]  # Bỏ "namhoc_" prefix
            
            # Hiển thị thông báo đang xử lý
            await query.answer("Đang tìm kiếm học phần...")
            
            # Lưu năm học - học kỳ đã chọn vào context
            context.user_data["selected_nam_hoc"] = nam_hoc_key
            
            # Lấy danh sách năm học - học kỳ
            result = await self.hoc_phan_handler.handle_hoc_phan(user_id)
            
            if result["success"]:
                # Lấy danh sách năm học - học kỳ
                nam_hoc_hoc_ky_list = self.hoc_phan_handler.get_nam_hoc_hoc_ky_list(result["data"])
                
                # Tìm các năm học - học kỳ phù hợp
                selected_nam_hoc_list = []
                for item in nam_hoc_hoc_ky_list:
                    if item["key"] == nam_hoc_key:
                        selected_nam_hoc_list.append(item["key"])
                        break
                
                
                if selected_nam_hoc_list:
                    # Tìm kiếm học phần
                    search_result = await self.hoc_phan_handler.handle_search_hoc_phan(user_id, selected_nam_hoc_list)
                    
                    if search_result["success"]:
                        # Định dạng dữ liệu học phần thành menu
                        message = self.hoc_phan_handler.format_search_hoc_phan_message(search_result["data"])
                        
                        # Tạo keyboard cho các nút chọn học phần
                        hoc_phan_list = self.hoc_phan_handler.get_hoc_phan_list(search_result["data"])
                        
                        keyboard = []
                        
                        # Thêm các nút chọn học phần (tối đa 2 nút mỗi hàng)
                        row = []
                        for i, hoc_phan in enumerate(hoc_phan_list):
                            row.append(InlineKeyboardButton(hoc_phan["name"], callback_data=f"hocphan_{hoc_phan['key']}"))
                            if len(row) == 2 or i == len(hoc_phan_list) - 1:
                                keyboard.append(row)
                                row = []
                        
                        # Thêm nút quay lại
                        keyboard.append([InlineKeyboardButton("⬅️ Quay lại", callback_data="hocphan_back")])
                        
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        await query.edit_message_text(
                            text=message,
                            reply_markup=reply_markup,
                            parse_mode="Markdown"
                        )
                    else:
                        # Thêm menu quay lại khi không tìm thấy học phần
                        keyboard = [
                            [InlineKeyboardButton("⬅️ Quay lại", callback_data="hocphan_back")]
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        await query.edit_message_text(
                            text=f"{search_result['message']}",
                            reply_markup=reply_markup,
                            parse_mode="Markdown"
                        )
                else:
                    await query.edit_message_text("Không tìm thấy năm học - học kỳ được chọn.")
            else:
                await query.edit_message_text(f"Không thể lấy danh sách năm học - học kỳ: {result['message']}", parse_mode="Markdown")
        elif callback_data.startswith("hocphan_"):
            # Xử lý khi chọn học phần
            if callback_data == "hocphan_back":
                # Quay lại menu chọn năm học - học kỳ
                result = await self.hoc_phan_handler.handle_hoc_phan(user_id)
                
                if result["success"]:
                    # Định dạng dữ liệu năm học - học kỳ thành menu
                    message = self.hoc_phan_handler.format_nam_hoc_hoc_ky_message(result["data"])
                    
                    # Tạo keyboard cho các nút chọn năm học - học kỳ
                    nam_hoc_hoc_ky_list = self.hoc_phan_handler.get_nam_hoc_hoc_ky_list(result["data"])
                    keyboard = []
                    
                    # Thêm các nút chọn năm học - học kỳ (tối đa 3 nút mỗi hàng)
                    row = []
                    for i, nam_hoc_hoc_ky in enumerate(nam_hoc_hoc_ky_list):
                        row.append(InlineKeyboardButton(nam_hoc_hoc_ky["name"], callback_data=f"namhoc_{nam_hoc_hoc_ky['key']}"))
                        if len(row) == 3 or i == len(nam_hoc_hoc_ky_list) - 1:
                            keyboard.append(row)
                            row = []
                    
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await query.edit_message_text(
                        text=message,
                        reply_markup=reply_markup,
                        parse_mode="Markdown"
                    )
                else:
                    await query.edit_message_text(f"Không thể lấy danh sách năm học - học kỳ: {result['message']}")
            else:
                # Xem chi tiết học phần
                key_lop_hoc_phan = callback_data.split("hocphan_")[1]
                
                # Lấy thông tin chi tiết học phần
                # Lấy năm học - học kỳ đã chọn từ context
                selected_nam_hoc = context.user_data.get("selected_nam_hoc")
                
                if not selected_nam_hoc:
                    # Nếu không có trong context, lấy năm học - học kỳ đầu tiên
                    result = await self.hoc_phan_handler.handle_hoc_phan(user_id)
                    if result["success"]:
                        nam_hoc_hoc_ky_list = self.hoc_phan_handler.get_nam_hoc_hoc_ky_list(result["data"])
                        if nam_hoc_hoc_ky_list:
                            selected_nam_hoc = nam_hoc_hoc_ky_list[0]["key"]
                        else:
                            logger.error("No nam_hoc_hoc_ky available")
                            await query.edit_message_text("Không có năm học - học kỳ nào để tìm kiếm.")
                            return
                    else:
                        await query.edit_message_text(f"Không thể lấy danh sách năm học - học kỳ: {result['message']}", parse_mode="Markdown")
                        return
                
                # Tìm kiếm học phần với năm học - học kỳ đã chọn
                search_result = await self.hoc_phan_handler.handle_search_hoc_phan(user_id, [selected_nam_hoc])
                
                if search_result["success"]:
                    # Tìm học phần phù hợp
                    hoc_phan_list = search_result["data"].get("hoc_phan_list", [])
                    logger.info(f"Searching in {len(hoc_phan_list)} hoc_phan items")
                    
                    selected_hoc_phan = None
                    
                    for hoc_phan in hoc_phan_list:
                        hocphan_key_check = hoc_phan.get("key_check")
                        if hocphan_key_check == key_lop_hoc_phan:
                            selected_hoc_phan = hoc_phan
                            break
                    
                    if selected_hoc_phan:
                        # Định dạng thông tin chi tiết học phần
                        message = self.hoc_phan_handler.format_hoc_phan_detail_message(selected_hoc_phan)
                        
                        # Tạo keyboard cho các chức năng
                        keyboard = [
                            [
                                InlineKeyboardButton("📋 Danh sách sinh viên", callback_data=f"danhsach_{key_lop_hoc_phan}"),
                                InlineKeyboardButton("📝 Điểm danh", callback_data=f"diemdanh_lop_hoc_phan_{key_lop_hoc_phan}")
                            ],
                            [
                                InlineKeyboardButton("⬅️ Quay lại", callback_data="hocphan_back")
                            ]
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        await query.edit_message_text(
                            text=message,
                            reply_markup=reply_markup,
                            parse_mode="Markdown"
                        )
                    else:
                        await query.edit_message_text("Không tìm thấy học phần được chọn.")
                else:
                    await query.edit_message_text(f"Không thể tìm kiếm học phần: {search_result['message']}", parse_mode="Markdown")
        elif callback_data.startswith("danhsach_"):
            # Xử lý khi chọn danh sách sinh viên
            key_lop_hoc_phan = callback_data.split("danhsach_")[1]
            
            # Hiển thị thông báo đang xử lý
            await query.answer("Đang tải danh sách sinh viên...")
            
            # Lấy danh sách sinh viên
            result = await self.hoc_phan_handler.handle_danh_sach_sinh_vien(user_id, key_lop_hoc_phan)
            
            if result["success"]:
                # Tạo file Excel
                try:
                    # Chạy tác vụ blocking trong một thread riêng
                    excel_file = await asyncio.to_thread(
                        self.hoc_phan_handler.generate_danh_sach_sinh_vien_xlsx,
                        result["data"]
                    )
                    
                    # Gửi file Excel
                    await query.message.reply_document(
                        document=excel_file,
                        filename=f"danh_sach_sinh_vien_{key_lop_hoc_phan}.xlsx",
                        caption="📋 Danh sách sinh viên lớp học phần"
                    )
                    
                    # Xóa tin nhắn menu lúc chọn danh sách sinh viên để giao diện sạch sẽ
                    try:
                        await query.message.delete()
                    except Exception as e:
                        logger.warning(f"Không thể xóa tin nhắn menu: {e}")
                    
                    # Lấy thông tin chi tiết học phần để hiển thị lại
                    selected_nam_hoc = context.user_data.get("selected_nam_hoc")
                    
                    if not selected_nam_hoc:
                        # Nếu không có trong context, lấy năm học - học kỳ đầu tiên
                        result_hoc_phan = await self.hoc_phan_handler.handle_hoc_phan(user_id)
                        if result_hoc_phan["success"]:
                            nam_hoc_hoc_ky_list = self.hoc_phan_handler.get_nam_hoc_hoc_ky_list(result_hoc_phan["data"])
                            if nam_hoc_hoc_ky_list:
                                selected_nam_hoc = nam_hoc_hoc_ky_list[0]["key"]
                            else:
                                await query.message.reply_text("Không có năm học - học kỳ nào để tìm kiếm.")
                                return
                        else:
                            await query.message.reply_text(f"Không thể lấy danh sách năm học - học kỳ: {result_hoc_phan['message']}")
                            return
                    
                    # Tìm kiếm học phần với năm học - học kỳ đã chọn
                    search_result = await self.hoc_phan_handler.handle_search_hoc_phan(user_id, [selected_nam_hoc])
                    
                    if search_result["success"]:
                        # Tìm học phần phù hợp
                        hoc_phan_list = search_result["data"].get("hoc_phan_list", [])
                        
                        selected_hoc_phan = None
                        
                        for hoc_phan in hoc_phan_list:
                            hocphan_key_check = hoc_phan.get("key_check")
                            if hocphan_key_check == key_lop_hoc_phan:
                                selected_hoc_phan = hoc_phan
                                break
                        
                        if selected_hoc_phan:
                            # Định dạng thông tin chi tiết học phần
                            message = self.hoc_phan_handler.format_hoc_phan_detail_message(selected_hoc_phan)
                            
                            # Tạo keyboard cho các chức năng
                            keyboard = [
                                [
                                    InlineKeyboardButton("📋 Danh sách sinh viên", callback_data=f"danhsach_{key_lop_hoc_phan}"),
                                    InlineKeyboardButton("📝 Điểm danh", callback_data=f"diemdanh_lop_hoc_phan_{key_lop_hoc_phan}")
                                ],
                                [
                                    InlineKeyboardButton("⬅️ Quay lại", callback_data="hocphan_back")
                                ]
                            ]
                            reply_markup = InlineKeyboardMarkup(keyboard)
                            
                            # Gửi tin nhắn mới với menu chi tiết học phần
                            await query.message.reply_text(
                                text=message,
                                reply_markup=reply_markup,
                                parse_mode="Markdown"
                            )
                        else:
                            await query.message.reply_text("Không tìm thấy học phần được chọn.")
                    else:
                        await query.message.reply_text(f"Không thể tìm kiếm học phần: {search_result['message']}", parse_mode="Markdown")
                
                except Exception as e:
                    await query.edit_message_text(f"Lỗi tạo file Excel: {str(e)}")
            else:
                await query.edit_message_text(f"Không thể lấy danh sách sinh viên: {result['message']}", parse_mode="Markdown")
        elif callback_data == "lichthi_back":
            # Xử lý khi quay lại từ lịch thi
            await query.edit_message_text(
                "📅 *Lịch Thi*\n\n"
                "Vui lòng thử lại sau hoặc liên hệ admin nếu vấn đề tiếp tục.",
                parse_mode="Markdown"
            )
    
    async def diem_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý callback từ các nút chọn học kỳ"""
        query = update.callback_query
        user_id = query.from_user.id
        
        # Lấy callback_data
        callback_data = query.data
        if callback_data.startswith("diem_"):
            hocky_key = callback_data[5:]  # Bỏ "diem_" prefix
            
            # Hiển thị thông báo đang xử lý
            await query.answer("Đang tải điểm...")
            
            if hocky_key == "more":
                # Xem thêm học kỳ cũ hơn
                result = await self.diem_handler.handle_diem(user_id)
                
                if result["success"]:
                    # Lấy danh sách học kỳ cũ hơn
                    older_hocky_list = self.diem_handler.get_older_hocky_list(result["data"])
                    
                    if older_hocky_list:
                        message = self.diem_handler.format_older_hocky_menu_message(result["data"])
                        
                        # Tạo keyboard cho các nút chọn học kỳ cũ
                        keyboard = []
                        for hocky in older_hocky_list:
                            keyboard.append([InlineKeyboardButton(hocky["name"], callback_data=f"diem_{hocky['key']}")])
                        
                        # Thêm nút quay lại
                        keyboard.append([InlineKeyboardButton("⬅️ Quay lại", callback_data="diem_back")])
                        
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        await query.edit_message_text(
                            text=message,
                            reply_markup=reply_markup,
                            parse_mode="Markdown"
                        )
                    else:
                        await query.edit_message_text("Không có học kỳ cũ hơn để hiển thị.")
                else:
                    await query.edit_message_text(f"Không thể lấy điểm: {result['message']}", parse_mode="Markdown")
            elif hocky_key == "back":
                # Quay lại menu chính
                result = await self.diem_handler.handle_diem(user_id)
                
                if result["success"]:
                    # Định dạng dữ liệu điểm thành menu
                    message = self.diem_handler.format_diem_menu_message(result["data"])
                    
                    # Tạo keyboard cho các nút chọn học kỳ
                    hocky_list = self.diem_handler.get_hocky_list(result["data"])
                    keyboard = []
                    
                    # Thêm các nút chọn học kỳ (mỗi nút một hàng)
                    for hocky in hocky_list:
                        keyboard.append([InlineKeyboardButton(hocky["name"], callback_data=f"diem_{hocky['key']}")])
                    
                    # Thêm nút xuất Excel
                    keyboard.append([InlineKeyboardButton("📄 Xuất Excel toàn bộ", callback_data="diem_export_all")])
                    
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await query.edit_message_text(
                        text=message,
                        reply_markup=reply_markup,
                        parse_mode="Markdown"
                    )
                else:
                    await query.edit_message_text(f"{result['message']}", parse_mode="Markdown")
            
            elif hocky_key.startswith("export_"):
                # Xử lý xuất file Excel
                export_type = hocky_key.split("_", 1)[1]
                
                await query.answer("Đang tạo file Excel...")
                
                # Lấy dữ liệu điểm
                result = await self.diem_handler.handle_diem(user_id)
                
                if result["success"]:
                    try:
                        if export_type == "all":
                            # Xuất toàn bộ
                            excel_file = await asyncio.to_thread(
                                self.diem_handler.generate_diem_xlsx,
                                result["data"]
                            )
                            filename = "diem_toan_bo.xlsx"
                            caption = "📄 Bảng điểm toàn bộ"
                        else:
                            # Xuất theo học kỳ
                            excel_file = await asyncio.to_thread(
                                self.diem_handler.generate_diem_xlsx,
                                result["data"],
                                export_type # hocky_key
                            )
                            hocky_name = result["data"]["hocky_data"][export_type].get("hocky_name", export_type)
                            filename = f"diem_{hocky_name}.xlsx"
                            caption = f"📄 Bảng điểm {hocky_name}"

                        await query.message.reply_document(
                            document=excel_file,
                            filename=filename,
                            caption=caption
                        )

                        # Xóa tin nhắn menu cũ
                        await query.message.delete()

                        # Gửi lại menu điểm
                        result = await self.diem_handler.handle_diem(user_id)
                        if result["success"]:
                            message = self.diem_handler.format_diem_menu_message(result["data"])
                            hocky_list = self.diem_handler.get_hocky_list(result["data"])
                            keyboard = []
                            row = []
                            for i, hocky in enumerate(hocky_list):
                                row.append(InlineKeyboardButton(hocky["name"], callback_data=f"diem_{hocky['key']}"))
                                if len(row) == 3 or i == len(hocky_list) - 1:
                                    keyboard.append(row)
                                    row = []
                            keyboard.append([InlineKeyboardButton("📄 Xuất Excel toàn bộ", callback_data="diem_export_all")])
                            reply_markup = InlineKeyboardMarkup(keyboard)
                            await query.message.reply_text(
                                message,
                                reply_markup=reply_markup,
                                parse_mode="Markdown"
                            )

                    except Exception as e:
                        logger.error(f"Lỗi tạo file Excel: {e}", exc_info=True)
                        await query.edit_message_text(f"Lỗi tạo file Excel: {str(e)}")
                else:
                    await query.edit_message_text(f"Không thể lấy dữ liệu điểm để xuất file: {result['message']}", parse_mode="Markdown")
            else:
                # Xem điểm chi tiết của học kỳ được chọn
                result = await self.diem_handler.handle_diem(user_id, hocky_key)
                
                if result["success"]:
                    # Định dạng dữ liệu điểm chi tiết
                    message = self.diem_handler.format_diem_detail_message(result["data"])
                    
                    # Tạo keyboard cho các nút điều hướng
                    keyboard = [
                        [
                            InlineKeyboardButton("📄 Xuất Excel", callback_data=f"diem_export_{hocky_key}"),
                            InlineKeyboardButton("⬅️ Quay lại", callback_data="diem_back")
                        ]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await query.edit_message_text(
                        text=message,
                        reply_markup=reply_markup,
                        parse_mode="Markdown"
                    )
                else:
                    await query.edit_message_text(f"Không thể lấy điểm chi tiết: {result['message']}", parse_mode="Markdown")
    
    async def tkb_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Xử lý callback từ các nút điều hướng tuần và xuất file"""
        query = update.callback_query
        user_id = query.from_user.id
        
        # Lấy callback_data
        callback_data = query.data

        if callback_data == "tkb_export_ics":
            await query.answer("Đang tạo file .ics, vui lòng chờ...", show_alert=False)
            result = await self.tkb_handler.handle_export_tkb_ics(user_id)
            
            if result.get("success"):
                file_path = result.get("file_path")
                if file_path and os.path.exists(file_path):
                    try:
                        await query.message.reply_document(
                            document=open(file_path, 'rb'),
                            filename=os.path.basename(file_path),
                            caption="🗓️ File iCalendar thời khóa biểu của bạn."
                        )
                        # Xóa tin nhắn menu (tin nhắn của bot)
                        await query.message.delete()
                        
                        # Xóa tin nhắn lệnh /tkb gốc của người dùng
                        command_message_id = context.user_data.get('tkb_command_message_id')
                        if command_message_id:
                            await context.bot.delete_message(
                                chat_id=query.message.chat_id,
                                message_id=command_message_id
                            )
                    except Exception as e:
                        logger.error(f"Lỗi gửi file ICS cho user {user_id}: {e}")
                        await query.answer("Có lỗi xảy ra khi gửi file.", show_alert=True)
                    finally:
                        os.remove(file_path) # Xóa file tạm
                else:
                    await query.answer("Không thể tạo file TKB do không có dữ liệu.", show_alert=True)
            else:
                await query.answer(f"Lỗi: {result.get('message', 'Không rõ')}", show_alert=True)
            return

        if callback_data.startswith("tkb_"):
            try:
                week_offset = int(callback_data.split("_")[1])
            except (ValueError, IndexError):
                week_offset = 0
            
            # Hiển thị thông báo đang xử lý
            await query.answer("Đang tải thời khóa biểu...")
            
            # Lấy thời khóa biểu
            result = await self.tkb_handler.handle_tkb(user_id, week_offset)
            
            if result["success"]:
                # Định dạng dữ liệu thời khóa biểu
                message = self.tkb_handler.format_tkb_message(result["data"])
                
                # Tạo keyboard cho các nút điều hướng
                keyboard = [
                    [
                        InlineKeyboardButton("⬅️ Tuần trước", callback_data=f"tkb_{week_offset-1}"),
                        InlineKeyboardButton("Tuần hiện tại", callback_data=f"tkb_0"),
                        InlineKeyboardButton("Tuần tới ➡️", callback_data=f"tkb_{week_offset+1}")
                    ],
                    [
                        InlineKeyboardButton("🗓️ Xuất ra iCalendar (.ics)", callback_data="tkb_export_ics")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Cập nhật tin nhắn
                await query.edit_message_text(
                    text=message,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text(f"Không thể lấy thời khóa biểu: {result['message']}", parse_mode="Markdown")
    
    def setup_handlers(self, application: Application) -> None:
        """Thiết lập các handler cho bot"""
        # Handler cho lệnh cơ bản
        application.add_handler(CommandHandler("start", self.start_command))
        # Conversation handler cho đăng nhập được định nghĩa riêng
        application.add_handler(CommandHandler("diemdanh", self.diemdanh_command))
        application.add_handler(CommandHandler("tkb", self.tkb_command))
        application.add_handler(CommandHandler("lichthi", self.lich_thi_command))
        application.add_handler(CommandHandler("diem", self.diem_command))
        application.add_handler(CommandHandler("hocphan", self.hoc_phan_command))
        application.add_handler(CommandHandler("huy", self.cancel_command))
        application.add_handler(CommandHandler("trogiup", self.help_command))
        application.add_handler(CommandHandler("dangxuat", self.logout_command))
        
        # Conversation handler cho đăng nhập
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("dangnhap", self.login_command)],
            states={
                USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.username_received)],
                PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.password_received)],
            },
            fallbacks=[CommandHandler("huy", self.cancel_command)],
        )
        
        # Handler cho callback queries
        application.add_handler(CallbackQueryHandler(self.tkb_callback, pattern="^tkb_"))
        application.add_handler(CallbackQueryHandler(self.diem_callback, pattern="^diem_"))
        application.add_handler(CallbackQueryHandler(self.hoc_phan_callback, pattern="^(namhoc_|hocphan_|danhsach_|lichthi_)"))
        application.add_handler(CallbackQueryHandler(self.diemdanh_callback, pattern="^diemdanh_"))
        application.add_handler(CallbackQueryHandler(self.diemdanh_numeric_callback, pattern="^num_"))
        
        application.add_handler(conv_handler)
        
        # Handler cho nhập mã QR (chỉ hoạt động khi không có conversation nào đang diễn ra)
        # Đặt ở group=-1 để đảm bảo nó chỉ được xử lý sau khi các handler khác không khớp
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.diemdanh_code_received), group=-1)
    
    async def auto_refresh_cache_task(self):
        """Tác vụ nền tự động xóa cache của người dùng đang đăng nhập."""
        while True:
            await asyncio.sleep(600) # Chờ 10 phút
            
            logger.info("Bắt đầu tác vụ tự động làm mới cache...")
            logged_in_users = await self.db_manager.get_all_logged_in_users()
            
            if logged_in_users:
                logger.info(f"Tìm thấy {len(logged_in_users)} người dùng đang đăng nhập. Tiến hành xóa cache.")
                for user_id in logged_in_users:
                    await self.cache_manager.clear_user_cache(user_id)
                logger.info("Hoàn tất tác vụ tự động làm mới cache.")
            else:
                logger.info("Không có người dùng nào đang đăng nhập. Bỏ qua lần làm mới này.")

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
            if application.updater and application.updater.is_running:
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
    # try/except đã được chuyển vào trong hàm run
    asyncio.run(main())