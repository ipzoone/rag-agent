"""POST /admin-delete — remove a knowledge-base source file.

Body: { token, filename }. Also removes a same-named .json index if present.
After deleting you should call /admin-rebuild to refresh the vector store.
"""

import os
from typing import Any

from .._admin_auth import UPLOAD_DIR, parse_body, require_admin, safe_filename
from .._logger import create_logger

logger = create_logger("admin-delete")


async def handler(context: Any):
    body, err = require_admin(context)
    if err:
        return err

    name = safe_filename(body.get("filename", ""))
    if not name:
        return {"ok": False, "error": "missing_filename"}

    path = UPLOAD_DIR / name
    if not path.exists() or not path.is_file():
        return {"ok": False, "error": "not_found", "filename": name}

    try:
        path.unlink()
        # Drop a matching PageIndex JSON if it exists.
        sibling = path.with_suffix(".json")
        if sibling.exists():
            sibling.unlink()
    except Exception as e:
        logger.error(f"Failed to delete {name}: {e}")
        return {"ok": False, "error": "delete_failed", "detail": str(e)}

    logger.log(f"Deleted {name}")
    return {"ok": True, "filename": name}
