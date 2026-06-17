#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Database backend dùng Postgres (asyncpg).

Phù hợp production: hỗ trợ nhiều instance, lock phân tán qua advisory lock.
Sử dụng cú pháp Postgres-native: placeholder `$1`, JSONB, ON CONFLICT … EXCLUDED.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import asyncpg

from config.config import Config
from database.base import BaseDatabase

logger = logging.getLogger(__name__)


class PostgresBackend(BaseDatabase):
    """Backend Postgres cho bot. Pool asyncpg 5–20 connection."""

    def __init__(self):
        self.config = Config()
        self.pool: Optional[asyncpg.Pool] = None
        # Connection đang giữ advisory lock cho bot instance
        self._bot_lock_conn: Optional[asyncpg.Connection] = None
        self._bot_lock_key: Optional[int] = None

    # ==================== Lifecycle ====================

    async def connect(self):
        """Tạo connection pool và khởi tạo schema (idempotent)."""
        if not self.pool:
            try:
                self.pool = await asyncpg.create_pool(
                    dsn=self.config.POSTGRES_URL,
                    min_size=5,
                    max_size=20,
                )
                logger.info("Đã kết nối thành công đến PostgreSQL và tạo connection pool.")
                await self._init_database()
            except Exception as e:
                logger.error("Lỗi không thể kết nối đến PostgreSQL: %s", e)
                raise

    async def close(self):
        """Nhả advisory lock và đóng connection pool."""
        await self.release_bot_instance_lock()
        if self.pool:
            await self.pool.close()
            logger.info("Đã đóng connection pool của PostgreSQL.")

    # ==================== Instance lock ====================

    async def acquire_bot_instance_lock(self, lock_key: int) -> bool:
        """Lấy `pg_try_advisory_lock`. Session-level, lock sống đến khi connection đóng.
        Trả về False nếu instance khác đang giữ."""
        if not self.pool:
            raise RuntimeError("Database pool chưa được khởi tạo.")
        if self._bot_lock_conn is not None:
            return True

        conn = await self.pool.acquire()
        try:
            acquired = await conn.fetchval("SELECT pg_try_advisory_lock($1::bigint)", lock_key)
        except Exception:
            await self.pool.release(conn)
            raise

        if acquired:
            self._bot_lock_conn = conn
            self._bot_lock_key = lock_key
            logger.info("Đã lấy bot instance lock với key=%s", lock_key)
            return True

        await self.pool.release(conn)
        logger.warning("Không thể lấy bot instance lock với key=%s", lock_key)
        return False

    async def release_bot_instance_lock(self) -> None:
        """Nhả `pg_advisory_unlock` nếu đang giữ."""
        if not self._bot_lock_conn:
            return

        conn = self._bot_lock_conn
        lock_key = self._bot_lock_key
        self._bot_lock_conn = None
        self._bot_lock_key = None

        try:
            if lock_key is not None:
                await conn.execute("SELECT pg_advisory_unlock($1::bigint)", lock_key)
                logger.info("Đã nhả bot instance lock với key=%s", lock_key)
        except Exception as e:
            logger.warning("Không thể nhả bot instance lock: %s", e)
        finally:
            if self.pool:
                await self.pool.release(conn)

    # ==================== Schema ====================

    async def _init_database(self) -> None:
        """Tạo 3 bảng chính (idempotent): users, login_responses, user_consents."""
        async with self.pool.acquire() as conn:
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
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_consents (
                    id SERIAL PRIMARY KEY,
                    telegram_user_id BIGINT NOT NULL UNIQUE,
                    accepted BOOLEAN NOT NULL DEFAULT FALSE,
                    accepted_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            logger.info("Database initialized successfully")

    # ==================== Users ====================

    async def save_user(
        self, telegram_user_id: int, username: str, password: str, device_uuid: str
    ) -> bool:
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
            logger.info("User %s/%s saved successfully", telegram_user_id, username)
            return True
        except Exception as e:
            logger.error("Error saving user %s/%s: %s", telegram_user_id, username, e)
            return False

    async def save_login_response(
        self,
        telegram_user_id: int,
        username: str,
        response_data: Dict[str, Any],
        ho_ten: Optional[str] = None,
    ) -> bool:
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
                await conn.execute(
                    query, telegram_user_id, username, json.dumps(response_data), ho_ten
                )
            logger.info("Login response for user %s/%s saved successfully", telegram_user_id, username)
            return True
        except Exception as e:
            logger.error("Error saving login response for user %s/%s: %s", telegram_user_id, username, e)
            return False

    async def get_user_accounts(
        self, telegram_user_id: int, order_by_login_time: bool = False
    ) -> List[Dict[str, Any]]:
        if order_by_login_time:
            query = '''
                SELECT u.telegram_user_id, u.username, u.device_uuid, u.is_active, u.created_at,
                       lr.ho_ten
                FROM users u
                LEFT JOIN login_responses lr ON u.telegram_user_id = lr.telegram_user_id AND u.username = lr.username
                WHERE u.telegram_user_id = $1
                ORDER BY u.created_at ASC
            '''
        else:
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
            logger.error("Error getting accounts for user %s: %s", telegram_user_id, e)
            return []

    async def add_account(
        self,
        telegram_user_id: int,
        username: str,
        password: str,
        device_uuid: str,
        response_data: Dict[str, Any],
        ho_ten: Optional[str] = None,
    ) -> bool:
        async with self.pool.acquire() as conn:
            try:
                await conn.execute(
                    "UPDATE users SET is_active = FALSE WHERE telegram_user_id = $1",
                    telegram_user_id,
                )
                await conn.execute(
                    '''INSERT INTO users (telegram_user_id, username, password, device_uuid, is_active, updated_at)
                       VALUES ($1, $2, $3, $4, TRUE, CURRENT_TIMESTAMP)
                       ON CONFLICT (telegram_user_id, username) DO UPDATE SET
                           password = EXCLUDED.password,
                           device_uuid = EXCLUDED.device_uuid,
                           is_active = TRUE,
                           updated_at = CURRENT_TIMESTAMP''',
                    telegram_user_id, username, password, device_uuid,
                )
                await conn.execute(
                    '''INSERT INTO login_responses (telegram_user_id, username, response_data, ho_ten, created_at)
                       VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
                       ON CONFLICT (telegram_user_id, username) DO UPDATE SET
                           response_data = EXCLUDED.response_data,
                           ho_ten = EXCLUDED.ho_ten,
                           created_at = CURRENT_TIMESTAMP''',
                    telegram_user_id, username, json.dumps(response_data), ho_ten,
                )
                logger.info("Account %s added for user %s, set as active", username, telegram_user_id)
                return True
            except Exception as e:
                logger.error("Error adding account for user %s/%s: %s", telegram_user_id, username, e)
                return False

    async def set_active_account(self, telegram_user_id: int, username: str) -> bool:
        query1 = 'UPDATE users SET is_active = FALSE WHERE telegram_user_id = $1'
        query2 = 'UPDATE users SET is_active = TRUE WHERE telegram_user_id = $1 AND username = $2'
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query1, telegram_user_id)
                await conn.execute(query2, telegram_user_id, username)
            logger.info("Account %s set as active for user %s", username, telegram_user_id)
            return True
        except Exception as e:
            logger.error("Error setting active account for user %s/%s: %s", telegram_user_id, username, e)
            return False

    async def get_active_account(self, telegram_user_id: int) -> Optional[Dict[str, Any]]:
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
            logger.error("Error getting active account for user %s: %s", telegram_user_id, e)
            return None

    async def remove_account(self, telegram_user_id: int, username: str) -> bool:
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "DELETE FROM login_responses WHERE telegram_user_id = $1 AND username = $2",
                        telegram_user_id, username,
                    )
                    await conn.execute(
                        "DELETE FROM users WHERE telegram_user_id = $1 AND username = $2",
                        telegram_user_id, username,
                    )
            logger.info("Account %s removed for user %s", username, telegram_user_id)
            return True
        except Exception as e:
            logger.error("Error removing account %s for user %s: %s", username, telegram_user_id, e)
            return False

    async def delete_all_accounts(self, telegram_user_id: int) -> bool:
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute("DELETE FROM login_responses WHERE telegram_user_id = $1", telegram_user_id)
                    await conn.execute("DELETE FROM users WHERE telegram_user_id = $1", telegram_user_id)
            logger.info("All accounts deleted for user %s", telegram_user_id)
            return True
        except Exception as e:
            logger.error("Error deleting all accounts for user %s: %s", telegram_user_id, e)
            return False

    async def get_user(self, telegram_user_id: int) -> Optional[Dict[str, Any]]:
        active = await self.get_active_account(telegram_user_id)
        if active:
            return {
                "telegram_user_id": active["telegram_user_id"],
                "username": active["username"],
                "device_uuid": active["device_uuid"],
                "is_active": active["is_active"],
            }
        return None

    async def is_user_logged_in(self, telegram_user_id: int) -> bool:
        query = "SELECT 1 FROM users WHERE telegram_user_id = $1 LIMIT 1"
        try:
            async with self.pool.acquire() as conn:
                record = await conn.fetchrow(query, telegram_user_id)
            return record is not None
        except Exception as e:
            logger.error("Error checking login status for user %s: %s", telegram_user_id, e)
            return False

    async def set_user_login_status(self, telegram_user_id: int, is_logged_in: bool) -> bool:
        # Deprecated — giữ để tương thích
        return True

    async def get_user_login_response(self, telegram_user_id: int) -> Optional[Dict[str, Any]]:
        active = await self.get_active_account(telegram_user_id)
        if not active:
            return None
        query = "SELECT response_data FROM login_responses WHERE telegram_user_id = $1 AND username = $2"
        try:
            async with self.pool.acquire() as conn:
                record = await conn.fetchrow(query, telegram_user_id, active["username"])
            if record and record["response_data"]:
                return json.loads(record["response_data"])
            return None
        except Exception as e:
            logger.error("Error getting login response for user %s: %s", telegram_user_id, e)
            return None

    async def get_user_login_response_by_username(
        self, telegram_user_id: int, username: str
    ) -> Optional[Dict[str, Any]]:
        query = "SELECT response_data FROM login_responses WHERE telegram_user_id = $1 AND username = $2"
        try:
            async with self.pool.acquire() as conn:
                record = await conn.fetchrow(query, telegram_user_id, username)
            if record and record["response_data"]:
                return json.loads(record["response_data"])
            return None
        except Exception as e:
            logger.error("Error getting login response for user %s/%s: %s", telegram_user_id, username, e)
            return None

    async def delete_user(self, telegram_user_id: int) -> bool:
        return await self.delete_all_accounts(telegram_user_id)

    async def get_all_logged_in_users(self) -> List[int]:
        query = "SELECT DISTINCT telegram_user_id FROM users"
        try:
            async with self.pool.acquire() as conn:
                records = await conn.fetch(query)
            return [r["telegram_user_id"] for r in records]
        except Exception as e:
            logger.error("Error getting all logged in users: %s", e)
            return []

    async def get_active_user_token(self, telegram_user_id: int) -> Optional[str]:
        active = await self.get_active_account(telegram_user_id)
        if not active:
            return None
        query = "SELECT response_data FROM login_responses WHERE telegram_user_id = $1 AND username = $2"
        try:
            async with self.pool.acquire() as conn:
                record = await conn.fetchrow(query, telegram_user_id, active["username"])
            if record and record["response_data"]:
                response_data = json.loads(record["response_data"])
                return response_data.get("token")
            return None
        except Exception as e:
            logger.error("Error getting token for user %s: %s", telegram_user_id, e)
            return None

    async def get_user_device_uuid_by_username(
        self, telegram_user_id: int, username: str
    ) -> Optional[str]:
        query = "SELECT device_uuid FROM users WHERE telegram_user_id = $1 AND username = $2"
        try:
            async with self.pool.acquire() as conn:
                record = await conn.fetchrow(query, telegram_user_id, username)
            if record:
                return record["device_uuid"]
            return None
        except Exception as e:
            logger.error("Error getting device UUID for user %s/%s: %s", telegram_user_id, username, e)
            return None

    # ==================== Policy / consent ====================

    async def has_accepted_policy(self, telegram_user_id: int) -> bool:
        query = "SELECT accepted FROM user_consents WHERE telegram_user_id = $1 LIMIT 1"
        try:
            async with self.pool.acquire() as conn:
                record = await conn.fetchrow(query, telegram_user_id)
            return bool(record and record["accepted"])
        except Exception as e:
            logger.error("Error checking policy consent for user %s: %s", telegram_user_id, e)
            return False

    async def set_policy_consent(self, telegram_user_id: int, accepted: bool) -> bool:
        query = '''
            INSERT INTO user_consents (telegram_user_id, accepted, accepted_at, updated_at)
            VALUES ($1, $2, CASE WHEN $2 THEN CURRENT_TIMESTAMP ELSE NULL END, CURRENT_TIMESTAMP)
            ON CONFLICT (telegram_user_id) DO UPDATE SET
                accepted = EXCLUDED.accepted,
                accepted_at = EXCLUDED.accepted_at,
                updated_at = CURRENT_TIMESTAMP
        '''
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, telegram_user_id, accepted)
            logger.info("Policy consent updated for user %s: accepted=%s", telegram_user_id, accepted)
            return True
        except Exception as e:
            logger.error("Error updating policy consent for user %s: %s", telegram_user_id, e)
            return False

    # ==================== Preferred campus ====================

    async def get_user_preferred_campus(self, telegram_user_id: int) -> Optional[str]:
        query = "SELECT preferred_campus FROM users WHERE telegram_user_id = $1 LIMIT 1"
        try:
            async with self.pool.acquire() as conn:
                record = await conn.fetchrow(query, telegram_user_id)
            if record and record["preferred_campus"]:
                return record["preferred_campus"]
            return None
        except Exception as e:
            logger.error("Error getting preferred campus for user %s: %s", telegram_user_id, e)
            return None

    async def set_user_preferred_campus(
        self, telegram_user_id: int, campus_name: str
    ) -> bool:
        query = "UPDATE users SET preferred_campus = $1 WHERE telegram_user_id = $2"
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, campus_name, telegram_user_id)
            logger.info("Preferred campus '%s' saved for user %s", campus_name, telegram_user_id)
            return True
        except Exception as e:
            logger.error("Error setting preferred campus for user %s: %s", telegram_user_id, e)
            return False

    async def delete_user_preferred_campus(self, telegram_user_id: int) -> bool:
        query = "UPDATE users SET preferred_campus = NULL WHERE telegram_user_id = $1"
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, telegram_user_id)
            logger.info("Preferred campus deleted for user %s", telegram_user_id)
            return True
        except Exception as e:
            logger.error("Error deleting preferred campus for user %s: %s", telegram_user_id, e)
            return False
