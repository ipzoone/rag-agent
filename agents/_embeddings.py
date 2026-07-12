"""Local embedding backend for semantic retrieval (free, offline).

Uses `fastembed` with a multilingual model so the knowledge base can be
embedded and queried without any external API or paid service. The model is
downloaded once and cached locally; subsequent runs work fully offline.

Provider abstraction is kept minimal: local is the only required backend, but
`tencent` (Hunyuan) / `openai` stubs are reserved for optional remote upgrades.
"""

import os
from typing import List

from ._logger import create_logger

logger = create_logger("embeddings")

# ── Configuration ────────────────────────────────────────────────────────────

# Default: lightweight multilingual model (~470 MB) that handles zh + id + en
# well and runs comfortably on a standard laptop CPU (no torch dependency).
EMBED_PROVIDER = os.getenv("EMBED_PROVIDER", "local").lower()
LOCAL_EMBED_MODEL = os.getenv("LOCAL_EMBED_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

_embedder = None
_embed_dim = None


def _get_model():
    """Lazily load the fastembed model (downloads once, then cached)."""
    global _embedder, _embed_dim
    if _embedder is None:
        logger.log(f"Loading local embedding model: {LOCAL_EMBED_MODEL}")
        try:
            from fastembed import TextEmbedding
        except ImportError:
            logger.error("fastembed not installed. Run: pip install -r requirements.txt")
            raise
        _embedder = TextEmbedding(model_name=LOCAL_EMBED_MODEL)
        _embed_dim = _embedder.dim
        logger.log(f"Embedding model ready (dim={_embed_dim})")
    return _embedder


def embed_dim() -> int:
    """Return the vector dimension of the active model."""
    if _embed_dim is None:
        _get_model()
    return _embed_dim


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed a list of documents into vectors (batch)."""
    model = _get_model()
    vectors = list(model.embed(texts, batch_size=256, parallel=0))
    return [v.tolist() for v in vectors]


def embed_query(text: str) -> List[float]:
    """Embed a single query string into a vector."""
    model = _get_model()
    # fastembed's .embed returns a generator; a length-1 list yields one vector.
    vector = list(model.embed([text], batch_size=1, parallel=0))[0]
    return vector.tolist()
