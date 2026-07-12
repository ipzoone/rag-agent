"""RAG tool definitions for OpenAI Agents SDK (Python).

2 tools: search_document, fetch_pages
"""

import json
from typing import Annotated

from agents import function_tool

from ._loader import (
    list_documents,
    get_document_meta,
    get_page_content,
    parse_page_range,
)
from ._vector import semantic_search
from ._logger import create_logger

logger = create_logger("tools")


@function_tool
def search_document(
    query: Annotated[str, "User's search query"],
    doc_id: Annotated[str, "Document ID. Pass empty string only as a fallback to re-list documents — the system prompt already includes the catalog."] = "",
) -> str:
    """Inspect a single document's metadata + structure to plan a fetch_pages call.

    The system prompt already lists every available document, so the normal
    flow is: pick a doc_id from that catalog → optionally call this tool to
    inspect the structure → call fetch_pages. Calling this with an empty
    doc_id is allowed as a recovery path (e.g. the catalog looks stale), but
    it is not required for the common path and adds a wasted LLM round-trip.
    """

    logger.log(f"searchDocument called: query=\"{query}\", doc_id=\"{doc_id}\"")

    # Fallback path: re-emit the document list. The system prompt already
    # contains it, but we still support this for resiliency in case the model
    # decides to verify the catalog or the prompt was truncated.
    if not doc_id:
        docs = list_documents()
        logger.log(f"listDocuments returned {len(docs)} docs (fallback path)")
        if not docs:
            return json.dumps({
                "error": "Knowledge base is empty. Please run prepare_rag_data.py first.",
            }, ensure_ascii=False)

        return json.dumps({
            "query": query,
            "documentCount": len(docs),
            "documents": [
                {
                    "docId": d.get("docId", ""),
                    "meta": d.get("meta", {}),
                    "pages": d.get("pages", 0),
                    "hasStructure": d.get("hasStructure", False),
                }
                for d in docs
            ],
            "instruction": (
                "Pick a doc_id from the list above and call fetch_pages directly. "
                "For small documents (≤20 pages), pages=\"1-N\" is fine; "
                "for larger documents, optionally call search_document with a specific doc_id "
                "to inspect its structure first."
            ),
        }, ensure_ascii=False)

    meta = get_document_meta(doc_id)
    if not meta:
        return json.dumps({
            "error": f"Document '{doc_id}' not found.",
        }, ensure_ascii=False)

    # Semantic retrieval: find the most relevant chunks for the query.
    results = semantic_search(query, doc_id=doc_id, top_k=8)
    if not results:
        return json.dumps({
            "error": (
                f"No relevant chunks found in '{doc_id}'. The vector store may be empty — "
                "run `npm run prepare-rag` to rebuild it, or pick another document."
            ),
        }, ensure_ascii=False)

    doc_name = meta.get("doc_name", doc_id)
    return json.dumps({
        "docId": doc_id,
        "query": query,
        "instruction": (
            "The chunks below are the most semantically relevant passages to the user's question "
            "(ranked by similarity, lower score = more similar). Base your answer on these chunks and "
            "cite them by document name + page. If a chunk is insufficient, you may also call "
            "fetch_pages with its page number to read the full page text."
        ),
        "chunks": [
            {
                "page": r["page"],
                "chunkIndex": r["chunk_index"],
                "score": r["score"],
                "text": r["text"],
            }
            for r in results
        ],
    }, ensure_ascii=False)


@function_tool
def fetch_pages(
    doc_id: Annotated[str, "Document ID"],
    pages: Annotated[str, "Page range, e.g. '5-7,12,15-16'. Max 20 pages per call."],
) -> str:
    """Fetch specific pages from a document. Use after searchDocument to retrieve actual content."""

    logger.log(f"fetchPages called: doc_id=\"{doc_id}\", pages=\"{pages}\"")

    page_list = parse_page_range(pages)
    if not page_list:
        return json.dumps({"error": "Invalid page range"}, ensure_ascii=False)

    content = get_page_content(doc_id, page_list)
    if not content:
        return json.dumps({"error": "No pages found"}, ensure_ascii=False)

    # Get document name for citation
    meta = get_document_meta(doc_id)
    doc_name = meta.get("doc_name", doc_id) if meta else doc_id

    total_chars = sum(len(p["content"]) for p in content)

    return json.dumps({
        "type": "citation_pages",
        "docId": doc_id,
        "docName": doc_name,
        "pages": pages,
        "pageCount": len(content),
        "totalChars": total_chars,
        "content": [
            {"page": p["page"], "content": p["content"], "preview": p["content"][:400]}
            for p in content
        ],
    }, ensure_ascii=False)


# Tool collection for RAG agent
RAG_TOOLS = [search_document, fetch_pages]
