"""POST /admin-rebuild — regenerate the RAG knowledge base in-process.

Calls the canonical builder in agents/_prepare_rag.py directly (same process,
same sandbox filesystem), scanning agents/_uploads/ plus public/prepare-rag/
files/ (if present). This avoids depending on files outside the deployed
agents/ directory and on spawning a subprocess.

Returns a summary of the build.
"""

import gc
from typing import Any

from .._admin_auth import (
    AGENTS_DATA_DIR,
    prepare_source_dirs,
    require_admin,
)
from .._logger import create_logger
from .._vector import _dispose

logger = create_logger("admin-rebuild")


async def handler(context: Any):
    _, err = require_admin(context)
    if err:
        return err

    # Release the parent process's open Chroma handles so the pipeline can
    # safely wipe agents/_data (rmtree would otherwise fail on Windows).
    try:
        _dispose()
    except Exception:
        pass
    gc.collect()

    try:
        from .._prepare_rag import build
    except Exception as e:
        logger.error(f"Failed to import prepare pipeline: {e}")
        return {"ok": False, "error": "import_failed", "detail": str(e)}

    try:
        summary = build(prepare_source_dirs(), AGENTS_DATA_DIR)
    except Exception as e:
        logger.error(f"Build failed: {e}")
        return {"ok": False, "error": "build_failed", "detail": str(e)}

    logger.log(f"Rebuild complete: {summary}")
    return {"ok": True, "summary": summary}
