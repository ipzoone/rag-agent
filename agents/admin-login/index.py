"""POST /admin-login — verify password and issue an admin token."""

import json
from typing import Any

from .._admin_auth import check_password, issue_token, parse_body
from .._logger import create_logger

logger = create_logger("admin-login")


async def handler(context: Any):
    body = parse_body(context)
    password = body.get("password", "")

    if not check_password(password):
        return {"ok": False, "authenticated": False, "error": "invalid_password"}

    token = issue_token()
    logger.log("Admin login succeeded")
    return {"ok": True, "authenticated": True, "token": token}
