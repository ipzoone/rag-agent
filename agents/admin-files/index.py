"""POST /admin-files — list uploaded source files and the built index.

Requires a valid admin token in the request body.
"""

import json
from typing import Any

from .._admin_auth import (
    PROJECT_ROOT,
    PUBLIC_FILES_DIR,
    UPLOAD_DIR,
    parse_body,
    require_admin,
)
from .._logger import create_logger

logger = create_logger("admin-files")


def _read_index() -> dict:
    idx_path = PROJECT_ROOT / "agents" / "_data" / "index.json"
    if not idx_path.exists():
        return {}
    try:
        with open(idx_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read index.json: {e}")
        return {}


def _list_dir(directory, source):
    out = []
    if not directory or not directory.exists():
        return out
    for p in sorted(directory.iterdir()):
        if p.is_file():
            try:
                size = p.stat().st_size
            except Exception:
                size = 0
            out.append({"name": p.name, "size": size, "source": source})
    return out


async def handler(context: Any):
    _, err = require_admin(context)
    if err:
        return err

    # Panel uploads live in agents/_uploads/; pre-existing docs may live in
    # public/prepare-rag/files/ (local full builds). Both get rebuilt.
    files = _list_dir(UPLOAD_DIR, "upload") + _list_dir(PUBLIC_FILES_DIR, "public")

    index = _read_index()
    documents = index.get("documents", [])
    generated_at = index.get("generated_at")

    return {
        "ok": True,
        "files": files,
        "documents": documents,
        "generated_at": generated_at,
        "allowed_ext": sorted({".pdf", ".docx", ".xlsx", ".pptx"}),
    }
