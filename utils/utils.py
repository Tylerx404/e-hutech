#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Hàm tiện ích dùng chung cho bot.
"""

import logging
import uuid

logger = logging.getLogger(__name__)


def generate_uuid() -> str:
    """Sinh UUID v4 uppercase. Dùng làm device UUID cho mỗi tài khoản HUTECH."""
    return str(uuid.uuid4()).upper()
