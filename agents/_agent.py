"""Agent definition: RAG Assistant."""

from agents import Agent
from agents.model_settings import ModelSettings

from ._loader import get_document_meta, list_documents
from ._logger import create_logger
from ._model import llm_model
from ._tools import RAG_TOOLS

logger = create_logger("agent")


def _build_document_catalog() -> str:
    """Render the knowledge base inventory into the system prompt.

    Inlining the catalog lets the model skip the `search_document(doc_id="")`
    discovery round, which used to be a mandatory first LLM turn before any
    real retrieval could happen — the slowest part of first-token latency.

    The catalog is built once at module load. If `_data/` is regenerated at
    runtime the process must restart for the change to be picked up; this is
    consistent with the existing one-shot prepare-rag pipeline and keeps the
    hot path out of disk I/O.
    """
    docs = list_documents()
    if not docs:
        logger.warn("Knowledge base is empty; agent prompt will say so.")
        return (
            "Available documents: (the knowledge base is currently empty — "
            "tell the user to run `npm run prepare-rag` and try again)."
        )

    lines = ["Available documents in the knowledge base:"]
    for d in docs:
        doc_id = d.get("docId", "")
        meta = get_document_meta(doc_id) or {}
        name = meta.get("doc_name") or doc_id
        desc = meta.get("doc_description") or ""
        page_count = meta.get("page_count")
        page_hint = f", {page_count} pages" if isinstance(page_count, int) else ""
        desc_part = f" — {desc}" if desc else ""
        lines.append(f"- doc_id={doc_id!r}: {name}{page_hint}{desc_part}")
    return "\n".join(lines)


def _build_instructions(context=None, agent=None) -> str:
    """Build system prompt with a fresh document catalog each run."""
    catalog = _build_document_catalog()
    return (
        "You are an enterprise knowledge base assistant. "
        "Answer questions using only retrieved knowledge base content.\n\n"
        f"{catalog}\n\n"
        "Retrieval workflow:\n"
        "1. Pick the doc_id whose name / description in the catalog above best matches the user's question. "
        "Do NOT call search_document with an empty doc_id — the catalog already lists every document. "
        "Retrieval is semantic, so you do NOT need exact keywords; paraphrases, synonyms, and minor typos still match.\n"
        "2. Call search_document(doc_id=<id>, query=<user's question>) to get the most relevant chunks "
        "(ranked by similarity, lower score = more similar). These chunks already contain the answer passages — "
        "cite them by document name + page.\n"
        "3. If you need more surrounding context, call fetch_pages(doc_id, pages=<page number>) to read the "
        "full page text for any chunk's page.\n"
        "4. If the picked document turns out to be wrong, switch to another candidate from the catalog "
        "rather than giving up. You may consult multiple documents when relevant.\n"
        "5. Base the final answer strictly on retrieved chunk/page content, not prior knowledge or assumptions.\n\n"
        "Answering rules:\n"
        "- Respond in the same language as the user's question.\n"
        "- Do NOT add inline citations such as [DocumentName, p.3] in the answer text. "
        "The platform renders source cards separately from the fetched pages, so duplicating them in prose is noise.\n"
        "- If sources conflict, state the conflict in plain language.\n"
        "- If after checking all relevant documents the content is genuinely insufficient, clearly say so. "
        "Never claim a topic is missing without first considering the catalog above.\n"
        "- Never invent document names, page numbers, citations, or facts.\n"
        "- If a tool call fails, explain the failure briefly and ask the user to retry or narrow the question."
    )


rag_agent = Agent(
    name="RAG Assistant",
    instructions=_build_instructions,
    tools=RAG_TOOLS,
    model=llm_model,
    model_settings=ModelSettings(parallel_tool_calls=False),
)
