"""Semantic retrieval layer backed by a local Chroma vector store.

Chroma runs embedded (PersistentClient) — no external server or database
service is required. Vectors are produced by the local embedding backend in
`_embeddings.py`, so the whole retrieval pipeline is free and offline.

Collection layout (`agents/_data/chroma/`):
  collection: "rag_chunks"
  record per chunk:
    id         : "{doc_id}__p{page}__c{chunk_index}"
    document   : chunk text
    embedding  : vector (local model)
    metadata   : {doc_id, doc_name, page, chunk_index}
"""

from pathlib import Path
from typing import Any, List

from ._embeddings import embed_dim, embed_query
from ._logger import create_logger

logger = create_logger("vector")

# _vector.py lives in agents/, _data/ is a sibling directory
RAG_ROOT = Path(__file__).parent / "_data"
CHROMA_DIR = RAG_ROOT / "chroma"
COLLECTION = "rag_chunks"

_client = None
_collection = None


def _get_collection():
    """Lazily open (or create) the embedded Chroma collection."""
    global _client, _collection
    if _collection is None:
        try:
            import chromadb
        except ImportError:
            logger.error("chromadb not installed. Run: pip install -r requirements.txt")
            raise
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        _collection = _client.get_or_create_collection(
            name=COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        logger.log(f"Chroma collection '{COLLECTION}' opened (dim={embed_dim()})")
    return _collection


def semantic_search(query: str, doc_id: str = "", top_k: int = 8) -> List[dict]:
    """Return the most similar chunks to `query` via cosine similarity.

    If `doc_id` is provided, results are filtered to that document.
    Each returned item: {doc_id, doc_name, page, chunk_index, text, score}.
    `score` is the cosine distance (lower = more similar).
    """
    collection = _get_collection()
    if collection.count() == 0:
        logger.warn("semantic_search called but vector store is empty")
        return []

    vector = embed_query(query)
    where = {"doc_id": doc_id} if doc_id else None
    try:
        res = collection.query(
            query_embeddings=[vector],
            n_results=min(top_k, collection.count()),
            where=where,
        )
    except Exception as e:  # e.g. dimension mismatch on first run
        logger.error(f"Chroma query failed: {e}")
        return []

    ids = res.get("ids", [[]])[0]
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    dists = res.get("distances", [[]])[0]

    results: List[dict] = []
    for i in range(len(ids)):
        meta = metas[i] or {}
        results.append({
            "doc_id": meta.get("doc_id", ""),
            "doc_name": meta.get("doc_name", ""),
            "page": meta.get("page", 0),
            "chunk_index": meta.get("chunk_index", 0),
            "text": docs[i],
            "score": dists[i] if i < len(dists) else None,
        })
    return results


def index_chunks(chunks: List[dict]) -> int:
    """Persist pre-built chunks into Chroma.

    `chunks` items: {id, text, doc_id, doc_name, page, chunk_index}.
    Embeddings are computed locally here. Returns the number of chunks added.
    """
    if not chunks:
        logger.warn("index_chunks called with empty chunk list")
        return 0
    collection = _get_collection()

    texts = [c["text"] for c in chunks]
    try:
        from ._embeddings import embed_texts
        embeddings = embed_texts(texts)
    except Exception as e:
        logger.error(f"Embedding failed during indexing: {e}")
        raise

    ids = [c["id"] for c in chunks]
    metadatas = [
        {
            "doc_id": c["doc_id"],
            "doc_name": c.get("doc_name", ""),
            "page": c["page"],
            "chunk_index": c["chunk_index"],
        }
        for c in chunks
    ]
    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
    )
    logger.log(f"Indexed {len(chunks)} chunks into Chroma")
    return len(chunks)
