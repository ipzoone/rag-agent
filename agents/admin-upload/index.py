"""POST /admin-upload — write a knowledge-base document.

Body: { token, filename, data }  where `data` is base64-encoded file content.
Only PDF / DOCX / XLSX / PPTX are accepted.
"""

import base64
from typing import Any

from .._admin_auth import (
    UPLOAD_DIR,
    parse_body,
    require_admin,
    safe_filename,
    sanitize_ext,
)
from .._logger import create_logger

logger = create_logger("admin-upload")


async def handler(context: Any):
    body, err = require_admin(context)
    if err:
        return err

    raw_name = body.get("filename", "")
    name = safe_filename(raw_name)
    if not name:
        return {"ok": False, "error": "missing_filename"}

    ext = sanitize_ext(name)
    if not ext:
        return {"ok": False, "error": "unsupported_type", "filename": name}

    data = body.get("data", "")
    if not data:
        return {"ok": False, "error": "missing_data"}

    try:
        if isinstance(data, str) and "," in data:
            # Allow data URLs: "data:application/pdf;base64,...."
            data = data.split(",", 1)[1]
        content = base64.b64decode(data)
    except Exception as e:
        return {"ok": False, "error": "bad_base64", "detail": str(e)}

    if not content:
        return {"ok": False, "error": "empty_file"}

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / name
    try:
        dest.write_bytes(content)
    except Exception as e:
        logger.error(f"Failed to write {name}: {e}")
        return {"ok": False, "error": "write_failed", "detail": str(e)}

    logger.log(f"Uploaded {name} ({len(content)} bytes)")
    return {"ok": True, "filename": name, "size": len(content)}
