"""Shared helpers for the admin panel agent functions.

Endpoints:
  agents/admin-login/index.py    POST /admin-login    password -> token
  agents/admin-files/index.py    POST /admin-files    list KB files + index
  agents/admin-upload/index.py   POST /admin-upload   write a doc (base64)
  agents/admin-delete/index.py   POST /admin-delete   remove a doc
  agents/admin-rebuild/index.py  POST /admin-rebuild  run prepare_rag_data.py

Auth is a simple shared-secret gate: ADMIN_PASSWORD is verified on login and a
token (HMAC of the password under ADMIN_SECRET) is issued. Protected endpoints
re-validate that token. This is intentionally lightweight — there is no built-in
user system in the EdgeOne Makers runtime, so this keeps the dashboard usable
without standing up an identity provider.

All paths are resolved from this file so the handlers work regardless of the
process working directory.
"""

import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any

# agents/ is one level below the project root.
# In local dev, Makers runs a copy under .edgeone/ — we must walk back to the
# real project tree so uploads survive restarts.
_current = Path(__file__).resolve()
if ".edgeone" in str(_current):
    PROJECT_ROOT = _current.parents[3]  # .edgeone/agent-python/pages_agents/ → project root
else:
    PROJECT_ROOT = _current.parent.parent  # production / other layouts

AGENTS_DIR = PROJECT_ROOT / "agents"

# Uploads from the admin panel land in a sandbox-local folder (the Makers
# agent runtime only deploys agents/, not public/), so they must live here to
# be visible to the in-process prepare pipeline and the chat agent.
UPLOAD_DIR = AGENTS_DIR / "_uploads"

# Best-effort: local full builds also include public/prepare-rag/files/. This
# directory typically does NOT exist inside the Makers sandbox, so it is simply
# skipped there.
PUBLIC_FILES_DIR = PROJECT_ROOT / "public" / "prepare-rag" / "files"

# Where the vector store + manifest are written (read by the chat agent).
AGENTS_DATA_DIR = AGENTS_DIR / "_data"

# Document types the prepare pipeline accepts.
ALLOWED_EXT = {".pdf", ".docx", ".xlsx", ".pptx"}


def prepare_source_dirs():
    """Directories scanned by the prepare pipeline (existing first, then uploads)."""
    return [PUBLIC_FILES_DIR, UPLOAD_DIR]

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "rag-admin-change-me")


def parse_body(context: Any) -> dict:
    """Extract the request body as a dict (mirrors agents/chat/_stream._parse_body)."""
    body = getattr(getattr(context, "request", None), "body", None)
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            body = {}
    return body if isinstance(body, dict) else {}


def check_password(password: str) -> bool:
    if not ADMIN_PASSWORD:
        # Admin is disabled until ADMIN_PASSWORD is configured.
        return False
    return hmac.compare_digest(password, ADMIN_PASSWORD)


def issue_token() -> str:
    return hmac.new(
        ADMIN_SECRET.encode("utf-8"),
        ADMIN_PASSWORD.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def validate_token(token: Any) -> bool:
    if not ADMIN_PASSWORD or not token:
        return False
    return hmac.compare_digest(str(token), issue_token())


def require_admin(context: Any) -> tuple[dict, dict | None]:
    """Return (body, None) if authorized, else (body, error_response)."""
    body = parse_body(context)
    if not validate_token(body.get("token")):
        return body, {"ok": False, "authenticated": False, "error": "unauthorized"}
    return body, None


def safe_filename(name: str) -> str:
    """Keep only the basename and strip path-traversal characters."""
    name = os.path.basename(name or "")
    name = name.replace("\\", "").replace("/", "")
    return name.strip()


def sanitize_ext(name: str) -> str:
    ext = Path(name).suffix.lower()
    return ext if ext in ALLOWED_EXT else ""
