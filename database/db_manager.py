#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Quản lý cơ sở dữ liệu PostgreSQL cho bot Telegram HUTECH
"""

import json
import logging
import asyncpg
from typing import Dict, Any, Optional, List

from config.config import Config

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        self.config = Config()
        self.pool = None

    async def connect(self):
        """Khởi tạo connection pool đến PostgreSQL."""
        if not self.pool:
            try:
                self.pool = await asyncpg.create_pool(
                    dsn=self.config.POSTGRES_URL,
                    min_size=5,
                    max_size=20
                )
                logger.info("Đã kết nối thành công đến PostgreSQL và tạo connection pool.")
                await self._init_database()
            except Exception as e:
                logger.error(f"Lỗi không thể kết nối đến PostgreSQL: {e}")
                raise

    async def close(self):
        """Đóng connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("Đã đóng connection pool của PostgreSQL.")

    async def _init_database(self) -> None:
        """Khởi tạo cơ sở dữ liệu và tạo các bảng nếu chưa tồn tại."""
        async with self.pool.acquire() as conn:
            try:
                # Tạo bảng users (hỗ trợ nhiều tài khoản)
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id SERIAL PRIMARY KEY,
                        telegram_user_id BIGINT NOT NULL,
                        username TEXT NOT NULL,
                        password TEXT NOT NULL,
                        device_uuid TEXT NOT NULL,
                        is_active BOOLEAN DEFAULT FALSE,
                        preferred_campus TEXT,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(telegram_user_id, username)
                    )
                ''')

                # Tạo bảng login_responses (hỗ trợ nhiều tài khoản)
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS login_responses (
                        id SERIAL PRIMARY KEY,
                        telegram_user_id BIGINT NOT NULL,
                        username TEXT NOT NULL,
                        response_data JSONB NOT NULL,
                        ho_ten TEXT,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(telegram_user_id, username)
                    )
                ''')

                # Migration: Thêm cột preferred_campus nếu chưa tồn tại
                await conn.execute('''
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_campus TEXT
                ''')

                # Các bảng khác sẽ được tạo tương tự khi cần
                # Ví dụ cho tkb_responses
                logger.info("Database initialized successfully")
            except Exception as e:
                logger.error(f"Lỗi khởi tạo database: {e}")
                raise

    async def save_user(self, telegram_user_id: int, username: str, password: str, device_uuid: str) -> bool:
        """Lưu hoặc cập nhật thông tin người dùng. Account mới sẽ được set là active."""
        query = '''
            INSERT INTO users (telegram_user_id, username, password, device_uuid, is_active, updated_at)
            VALUES ($1, $2, $3, $4, TRUE, CURRENT_TIMESTAMP)
            ON CONFLICT (telegram_user_id, username) DO UPDATE SET
                password = EXCLUDED.password,
                device_uuid = EXCLUDED.device_uuid,
                is_active = TRUE,
                updated_at = CURRENT_TIMESTAMP
        '''
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, telegram_user_id, username, password, device_uuid)
            logger.info(f"User {telegram_user_id}/{username} saved successfully")
            return True
        except Exception as e:
            logger.error(f"Error saving user {telegram_user_id}/{username}: {e}")
            return False

    async def save_login_response(self, telegram_user_id: int, username: str, response_data: Dict[str, Any], ho_ten: str = None) -> bool:
        """Lưu response từ API đăng nhập."""
        query = '''
            INSERT INTO login_responses (telegram_user_id, username, response_data, ho_ten, created_at)
            VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
            ON CONFLICT (telegram_user_id, username) DO UPDATE SET
                response_data = EXCLUDED.response_data,
                ho_ten = EXCLUDED.ho_ten,
                created_at = CURRENT_TIMESTAMP
        '''
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, telegram_user_id, username, json.dumps(response_data), ho_ten)
            logger.info(f"Login response for user {telegram_user_id}/{username} saved successfully")
            return True
        except Exception as e:
            logger.error(f"Error saving login response for user {telegram_user_id}/{username}: {e}")
            return False

    async def get_user_accounts(self, telegram_user_id: int) -> List[Dict[str, Any]]:
        """Lấy danh sách tất cả tài khoản của người dùng."""
        query = '''
            SELECT u.telegram_user_id, u.username, u.device_uuid, u.is_active, u.created_at,
                   lr.ho_ten
            FROM users u
            LEFT JOIN login_responses lr ON u.telegram_user_id = lr.telegram_user_id AND u.username = lr.username
            WHERE u.telegram_user_id = $1
            ORDER BY u.is_active DESC, u.created_at DESC
        '''
        try:
            async with self.pool.acquire() as conn:
                records = await conn.fetch(query, telegram_user_id)
            return [dict(record) for record in records]
        except Exception as e:
            logger.error(f"Error getting accounts for user {telegram_user_id}: {e}")
            return []

    async def add_account(self, telegram_user_id: int, username: str, password: str, device_uuid: str, response_data: Dict[str, Any], ho_ten: str = None) -> bool:
        """Thêm tài khoản mới và set là active, tự động deactivate account cũ."""
        async with self.pool.acquire() as conn:
            try:
                # Deactivate all existing accounts
                await conn.execute(
                    "UPDATE users SET is_active = FALSE WHERE telegram_user_id = $1",
                    telegram_user_id
                )

                # Save user as active
                await conn.execute(
                    '''INSERT INTO users (telegram_user_id, username, password, device_uuid, is_active, updated_at)
                       VALUES ($1, $2, $3, $4, TRUE, CURRENT_TIMESTAMP)
                       ON CONFLICT (telegram_user_id, username) DO UPDATE SET
                           password = EXCLUDED.password,
                           device_uuid = EXCLUDED.device_uuid,
                           is_active = TRUE,
                           updated_at = CURRENT_TIMESTAMP''',
                    telegram_user_id, username, password, device_uuid
                )

                # Save login response
                await conn.execute(
                    '''INSERT INTO login_responses (telegram_user_id, username, response_data, ho_ten, created_at)
                       VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
                       ON CONFLICT (telegram_user_id, username) DO UPDATE SET
                           response_data = EXCLUDED.response_data,
                           ho_ten = EXCLUDED.ho_ten,
                           created_at = CURRENT_TIMESTAMP''',
                    telegram_user_id, username, json.dumps(response_data), ho_ten
                )

                logger.info(f"Account {username} added for user {telegram_user_id}, set as active")
                return True
            except Exception as e:
                logger.error(f"Error adding account for user {telegram_user_id}/{username}: {e}")
                return False

    async def set_active_account(self, telegram_user_id: int, username: str) -> bool:
        """Chuyển đổi tài khoản active."""
        query1 = 'UPDATE users SET is_active = FALSE WHERE telegram_user_id = $1'
        query2 = 'UPDATE users SET is_active = TRUE WHERE telegram_user_id = $1 AND username = $2'
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query1, telegram_user_id)
                await conn.execute(query2, telegram_user_id, username)
            logger.info(f"Account {username} set as active for user {telegram_user_id}")
            return True
        except Exception as e:
            logger.error(f"Error setting active account for user {telegram_user_id}/{username}: {e}")
            return False

    async def get_active_account(self, telegram_user_id: int) -> Optional[Dict[str, Any]]:
        """Lấy tài khoản đang hoạt động."""
        query = '''
            SELECT u.telegram_user_id, u.username, u.device_uuid, u.is_active, u.created_at,
                   lr.ho_ten
            FROM users u
            LEFT JOIN login_responses lr ON u.telegram_user_id = lr.telegram_user_id AND u.username = lr.username
            WHERE u.telegram_user_id = $1 AND u.is_active = TRUE
            LIMIT 1
        '''
        try:
            async with self.pool.acquire() as conn:
                record = await conn.fetchrow(query, telegram_user_id)
            if record:
                return dict(record)
            return None
        except Exception as e:
            logger.error(f"Error getting active account for user {telegram_user_id}: {e}")
            return None

    async def remove_account(self, telegram_user_id: int, username: str) -> bool:
        """Xóa một tài khoản cụ thể."""
        query = "DELETE FROM users WHERE telegram_user_id = $1 AND username = $2"
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, telegram_user_id, username)
            logger.info(f"Account {username} removed for user {telegram_user_id}")
            return True
        except Exception as e:
            logger.error(f"Error removing account {username} for user {telegram_user_id}: {e}")
            return False

    async def delete_all_accounts(self, telegram_user_id: int) -> bool:
        """Xóa tất cả tài khoản của người dùng."""
        query = "DELETE FROM users WHERE telegram_user_id = $1"
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, telegram_user_id)
            logger.info(f"All accounts deleted for user {telegram_user_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting all accounts for user {telegram_user_id}: {e}")
            return False

    async def get_user(self, telegram_user_id: int) -> Optional[Dict[str, Any]]:
        """Lấy thông tin người dùng (lấy account active)."""
        active_account = await self.get_active_account(telegram_user_id)
        if active_account:
            return {
                "telegram_user_id": active_account["telegram_user_id"],
                "username": active_account["username"],
                "device_uuid": active_account["device_uuid"],
                "is_active": active_account["is_active"]
            }
        return None

    async def is_user_logged_in(self, telegram_user_id: int) -> bool:
        """Kiểm tra xem người dùng có ít nhất 1 tài khoản đã đăng nhập."""
        query = "SELECT 1 FROM users WHERE telegram_user_id = $1 LIMIT 1"
        try:
            async with self.pool.acquire() as conn:
                record = await conn.fetchrow(query, telegram_user_id)
            return record is not None
        except Exception as e:
            logger.error(f"Error checking login status for user {telegram_user_id}: {e}")
            return False

    async def set_user_login_status(self, telegram_user_id: int, is_logged_in: bool) -> bool:
        """Cập nhật trạng thái đăng nhập của người dùng (deprecated, giữ lại để tương thích ngược)."""
        # This method is no longer used in the new multi-account system
        # But we keep it for backward compatibility
        return True

    async def get_user_login_response(self, telegram_user_id: int) -> Optional[Dict[str, Any]]:
        """Lấy response đăng nhập của account active."""
        active_account = await self.get_active_account(telegram_user_id)
        if not active_account:
            return None

        query = "SELECT response_data FROM login_responses WHERE telegram_user_id = $1 AND username = $2"
        try:
            async with self.pool.acquire() as conn:
                record = await conn.fetchrow(query, telegram_user_id, active_account["username"])
            if record and record['response_data']:
                return json.loads(record['response_data'])
            return None
        except Exception as e:
            logger.error(f"Error getting login response for user {telegram_user_id}: {e}")
            return None

    async def get_user_login_response_by_username(self, telegram_user_id: int, username: str) -> Optional[Dict[str, Any]]:
        """Lấy response đăng nhập theo username cụ thể."""
        query = "SELECT response_data FROM login_responses WHERE telegram_user_id = $1 AND username = $2"
        try:
            async with self.pool.acquire() as conn:
                record = await conn.fetchrow(query, telegram_user_id, username)
            if record and record['response_data']:
                return json.loads(record['response_data'])
            return None
        except Exception as e:
            logger.error(f"Error getting login response for user {telegram_user_id}/{username}: {e}")
            return None

    async def delete_user(self, telegram_user_id: int) -> bool:
        """Xóa tất cả tài khoản của người dùng."""
        return await self.delete_all_accounts(telegram_user_id)

    async def get_all_logged_in_users(self) -> List[int]:
        """Lấy danh sách ID của tất cả người dùng có ít nhất 1 tài khoản."""
        query = "SELECT DISTINCT telegram_user_id FROM users"
        try:
            async with self.pool.acquire() as conn:
                records = await conn.fetch(query)
            return [record['telegram_user_id'] for record in records]
        except Exception as e:
            logger.error(f"Error getting all logged in users: {e}")
            return []

    async def get_active_user_token(self, telegram_user_id: int) -> Optional[str]:
        """Lấy token của account active."""
        active_account = await self.get_active_account(telegram_user_id)
        if not active_account:
            return None

        query = "SELECT response_data FROM login_responses WHERE telegram_user_id = $1 AND username = $2"
        try:
            async with self.pool.acquire() as conn:
                record = await conn.fetchrow(query, telegram_user_id, active_account["username"])
            if record and record['response_data']:
                response_data = json.loads(record['response_data'])
                return response_data.get("token")
            return None
        except Exception as e:
            logger.error(f"Error getting token for user {telegram_user_id}: {e}")
            return None

    async def get_user_device_uuid_by_username(self, telegram_user_id: int, username: str) -> Optional[str]:
        """Lấy device UUID theo username cụ thể."""
        query = "SELECT device_uuid FROM users WHERE telegram_user_id = $1 AND username = $2"
        try:
            async with self.pool.acquire() as conn:
                record = await conn.fetchrow(query, telegram_user_id, username)
            if record:
                return record['device_uuid']
            return None
        except Exception as e:
            logger.error(f"Error getting device UUID for user {telegram_user_id}/{username}: {e}")
            return None

    async def get_user_preferred_campus(self, telegram_user_id: int) -> Optional[str]:
        """Lấy campus ưu tiên của người dùng."""
        query = "SELECT preferred_campus FROM users WHERE telegram_user_id = $1 LIMIT 1"
        try:
            async with self.pool.acquire() as conn:
                record = await conn.fetchrow(query, telegram_user_id)
            if record and record['preferred_campus']:
                return record['preferred_campus']
            return None
        except Exception as e:
            logger.error(f"Error getting preferred campus for user {telegram_user_id}: {e}")
            return None

    async def set_user_preferred_campus(self, telegram_user_id: int, campus_name: str) -> bool:
        """Lưu campus ưu tiên cho người dùng."""
        query = "UPDATE users SET preferred_campus = $1 WHERE telegram_user_id = $2"
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, campus_name, telegram_user_id)
            logger.info(f"Preferred campus '{campus_name}' saved for user {telegram_user_id}")
            return True
        except Exception as e:
            logger.error(f"Error setting preferred campus for user {telegram_user_id}: {e}")
            return False

    async def delete_user_preferred_campus(self, telegram_user_id: int) -> bool:
        """Xóa campus ưu tiên của người dùng."""
        query = "UPDATE users SET preferred_campus = NULL WHERE telegram_user_id = $1"
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, telegram_user_id)
            logger.info(f"Preferred campus deleted for user {telegram_user_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting preferred campus for user {telegram_user_id}: {e}")
            return False
