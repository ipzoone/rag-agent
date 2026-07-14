# -*- coding: utf-8 -*-
"""
prepare_rag_data.py — Local full-build entrypoint.

The actual pipeline now lives in agents/_prepare_rag.py (so it can also run
inside the EdgeOne Makers agent sandbox, which only deploys agents/). This file
is a thin shim: it points the builder at public/prepare-rag/files/ and writes
the output into agents/_data/.

Run locally with:  npm run prepare-rag
"""

import sys
from pathlib import Path

# Make the project-root `agents` package importable when run as a script
# (the openai-agents SDK also ships a top-level `agents` package).
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from agents._prepare_rag import build  # noqa: E402

FILES_DIR = Path(__file__).resolve().parent / "files"
OUT_DIR = ROOT / "agents" / "_data"

if __name__ == "__main__":
    build([FILES_DIR], OUT_DIR)
