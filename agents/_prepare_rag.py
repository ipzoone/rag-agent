# -*- coding: utf-8 -*-
"""
_prepare_rag.py — Canonical RAG knowledge-base builder, runnable INSIDE the
agent sandbox (EdgeOne Makers only deploys the agents/ directory, not public/).

It scans one or more source directories for .pdf/.docx/.xlsx/.pptx, extracts
text, chunks it (tiktoken), embeds locally with fastembed, and persists the
vectors + manifest into agents/_data/ (Chroma store + index.json).

Exposed API:
    build(files_dirs: list[Path], out_dir: Path) -> dict   # returns a summary
    main()                                                  # CLI entrypoint

The legacy public/prepare-rag/prepare_rag_data.py is now a thin shim that calls
build() so `npm run prepare-rag` (local full build) still works without
duplicating this logic.
"""

import gc
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List

# Reconfigure stdout/stderr to UTF-8 so box-drawing output never crashes on
# consoles with a non-UTF-8 encoding (e.g. Windows cp1252).
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ── Configuration ────────────────────────────────────────────────────────────

CHUNK_TOKENS = int(os.getenv("RAG_CHUNK_TOKENS", "500"))
OVERLAP_TOKENS = int(os.getenv("RAG_OVERLAP_TOKENS", "50"))
LOCAL_EMBED_MODEL = os.getenv(
    "LOCAL_EMBED_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)
CHROMA_COLLECTION = "rag_chunks"

ALLOWED_EXT = {".pdf", ".docx", ".xlsx", ".pptx"}


# ── Text Extraction (PDF / DOCX / XLSX / PPTX) ───────────────────────────────

def load_pdf_reader():
    try:
        from pypdf import PdfReader
        return PdfReader
    except ImportError:
        pass
    try:
        from PyPDF2 import PdfReader
        return PdfReader
    except ImportError:
        raise RuntimeError(
            "Missing PDF dependency (pypdf). Run: pip install -r requirements.txt"
        )


def extract_pdf(pdf_path: Path) -> tuple[dict[int, str], int]:
    PdfReader = load_pdf_reader()
    reader = PdfReader(str(pdf_path))
    pages: dict[int, str] = {}
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception as e:
            print(f"    [WARN] Page {i + 1} extraction failed: {e}", file=sys.stderr)
            text = ""
        pages[i + 1] = text.strip()
    return pages, len(reader.pages)


def _split_text_to_pages(text: str, size: int = 1800) -> dict[int, str]:
    text = (text or "").strip()
    if not text:
        return {}
    pages: dict[int, str] = {}
    n = 0
    for i in range(0, len(text), size):
        n += 1
        pages[n] = text[i:i + size].strip()
    return pages


def extract_docx(file_path: Path) -> tuple[dict[int, str], int]:
    from docx import Document
    doc = Document(str(file_path))
    blocks: list[str] = []
    for p in doc.paragraphs:
        t = p.text.strip()
        if t:
            blocks.append(t)
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            line = " | ".join(cells)
            if line.strip():
                blocks.append(line)
    pages = _split_text_to_pages("\n\n".join(blocks), size=1800)
    return pages, len(pages)


def extract_xlsx(file_path: Path) -> tuple[dict[int, str], int]:
    import openpyxl
    wb = openpyxl.load_workbook(str(file_path), read_only=True, data_only=True)
    pages: dict[int, str] = {}
    n = 0
    for ws in wb.worksheets:
        rows = []
        for r in ws.iter_rows(values_only=True):
            cells = ["" if c is None else str(c) for c in r]
            line = "\t".join(cells).strip()
            if line:
                rows.append(line)
        text = f"Sheet: {ws.title}\n" + "\n".join(rows)
        if text.strip():
            n += 1
            pages[n] = text
    return pages, n


def extract_pptx(file_path: Path) -> tuple[dict[int, str], int]:
    from pptx import Presentation
    prs = Presentation(str(file_path))
    pages: dict[int, str] = {}
    n = 0
    for slide in prs.slides:
        texts: list[str] = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    t = para.text.strip()
                    if t:
                        texts.append(t)
            if shape.has_table:
                for row in shape.table.rows:
                    cells = [c.text.strip() for c in row.cells]
                    line = " | ".join(cells)
                    if line.strip():
                        texts.append(line)
        text = "\n".join(texts)
        if text.strip():
            n += 1
            pages[n] = text
    return pages, n


def extract_document(file_path: Path) -> tuple[dict[int, str], int]:
    ext = file_path.suffix.lower()
    if ext == ".pdf":
        return extract_pdf(file_path)
    if ext == ".docx":
        return extract_docx(file_path)
    if ext == ".xlsx":
        return extract_xlsx(file_path)
    if ext == ".pptx":
        return extract_pptx(file_path)
    raise ValueError(f"Unsupported file type: {ext}")


def sanitize_doc_id(name: str) -> str:
    s = name.strip()
    s = re.sub(r"[\s.]+", "_", s)
    s = re.sub(r"[^\w\-]", "", s)
    s = s.strip("_")
    return s or "doc"


# ── Text Chunking ─────────────────────────────────────────────────────────────

_tok_enc = None


def _token_encoder():
    global _tok_enc
    if _tok_enc is None:
        import tiktoken
        _tok_enc = tiktoken.get_encoding("cl100k_base")
    return _tok_enc


def chunk_page(text: str, doc_id: str, page_num: int, doc_name: str) -> List[dict]:
    enc = _token_encoder()
    tokens = enc.encode(text)
    chunks: List[dict] = []
    n = len(tokens)
    if n == 0:
        return chunks
    start = 0
    idx = 0
    while start < n:
        end = min(start + CHUNK_TOKENS, n)
        piece = enc.decode(tokens[start:end]).strip()
        if piece:
            chunks.append({
                "id": f"{doc_id}__p{page_num}__c{idx}",
                "text": piece,
                "doc_id": doc_id,
                "doc_name": doc_name,
                "page": page_num,
                "chunk_index": idx,
            })
        idx += 1
        if end == n:
            break
        start = end - OVERLAP_TOKENS
    return chunks


# ── Vector Store Build (Chroma, embedded, local embeddings) ──────────────────

def build_vector_store(all_chunks: List[dict], out_dir: Path) -> int:
    if not all_chunks:
        print("    [VEC] No chunks to embed, skipping vector store.")
        return 0

    print(f"\n  [VEC] Embedding {len(all_chunks)} chunks with model {LOCAL_EMBED_MODEL} ...")
    from fastembed import TextEmbedding
    import chromadb

    model = TextEmbedding(model_name=LOCAL_EMBED_MODEL)
    texts = [c["text"] for c in all_chunks]
    embeddings = [v.tolist() for v in model.embed(texts, batch_size=256, parallel=0)]

    chroma_path = out_dir / "chroma"
    client = chromadb.PersistentClient(path=str(chroma_path))
    collection = client.get_or_create_collection(
        name=CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )
    collection.add(
        ids=[c["id"] for c in all_chunks],
        embeddings=embeddings,
        documents=texts,
        metadatas=[
            {
                "doc_id": c["doc_id"],
                "doc_name": c.get("doc_name", ""),
                "page": c["page"],
                "chunk_index": c["chunk_index"],
            }
            for c in all_chunks
        ],
    )
    print(f"  [VEC] Stored {len(all_chunks)} chunks in Chroma @ {chroma_path}")
    return len(all_chunks)


def write_document(src_path: Path, doc_id: str, out_dir: Path) -> tuple[dict, dict[int, str], str]:
    print(f"\n  [FILE] {src_path.name}  ->  doc_id: {doc_id}")

    pages, page_count = extract_document(src_path)
    text_pages = sum(1 for t in pages.values() if t)
    print(f"     Total {page_count} pages, {text_pages} pages with text")

    index_path = src_path.with_suffix(".json")
    index_data: dict = {}
    if index_path.exists():
        with open(index_path, "r", encoding="utf-8") as f:
            index_data = json.load(f)
        print(f"     Index: {index_path.name}  root: «{index_data.get('title', 'Untitled')}»")
    else:
        print(f"     Index: {index_path.name} not found, skipping structure.json")

    doc_name = index_data.get("title") or src_path.stem

    doc_dir = out_dir / doc_id
    pages_dir = doc_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    meta_payload = {
        "doc_name": doc_name,
        "doc_description": index_data.get("summary", ""),
        "type": src_path.suffix.lower().lstrip("."),
        "page_count": page_count,
        "status": "completed",
        "created": datetime.now(timezone.utc).isoformat(),
    }
    meta_path = doc_dir / "meta.json"
    meta_text = json.dumps(meta_payload, ensure_ascii=False, indent=2)
    meta_path.write_text(meta_text, encoding="utf-8")
    meta_bytes = len(meta_text.encode("utf-8"))

    structure_bytes = 0
    has_structure = bool(index_data)
    if has_structure:
        structure_text = json.dumps(index_data, ensure_ascii=False, indent=2)
        (doc_dir / "structure.json").write_text(structure_text, encoding="utf-8")
        structure_bytes = len(structure_text.encode("utf-8"))

    page_bytes = 0
    written_pages = 0
    skipped = 0
    for page_num, text in pages.items():
        if not text:
            skipped += 1
            continue
        page_file = pages_dir / f"{page_num}.txt"
        page_file.write_text(text, encoding="utf-8")
        page_bytes += len(text.encode("utf-8"))
        written_pages += 1

    if skipped:
        print(f"     Skipped {skipped} empty pages (image-only pages)")

    total_bytes = meta_bytes + structure_bytes + page_bytes
    print(
        f"     Written: 1 meta + {'1' if has_structure else '0'} structure + "
        f"{written_pages} pages  ({total_bytes / 1024:.1f} KB)"
    )

    return {
        "docId": doc_id,
        "meta": meta_payload,
        "hasStructure": has_structure,
        "pages": written_pages,
        "metaBytes": meta_bytes,
        "structureBytes": structure_bytes,
        "pageBytes": page_bytes,
        "totalBytes": total_bytes,
    }, pages, doc_name


# ── Build orchestration ──────────────────────────────────────────────────────

def build(files_dirs: List[Path], out_dir: Path) -> dict:
    """Scan every dir in `files_dirs`, build the KB into `out_dir`.

    Returns a summary dict (documents, chunks, total bytes, generated_at).
    """
    print("=" * 60)
    print("  RAG Data Generator  —  PageIndex (agent sandbox)")
    print("=" * 60)

    doc_files: List[Path] = []
    for d in files_dirs:
        if not d or not d.exists():
            continue
        found = sorted(
            p for p in d.iterdir()
            if p.is_file() and p.suffix.lower() in ALLOWED_EXT
        )
        if found:
            print(f"\n[DIR] {d}  ({len(found)} file(s))")
            for p in found:
                print(f"  · {p.name}")
            doc_files.extend(found)

    if not doc_files:
        print("[WARN] No supported files found in any source directory.")
        # Still (re)write an empty manifest so the UI reflects the empty state.
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.json").write_text(
            json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "documents": []},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {"documents": [], "chunks": 0, "totalBytes": 0,
                "generated_at": datetime.now(timezone.utc).isoformat()}

    if out_dir.exists():
        print(f"\n[CLEAN] Clearing old directory: {out_dir}")
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    index_entries: List[dict] = []
    used_ids: List[str] = []
    all_chunks: List[dict] = []
    skipped: List[str] = []

    for src_path in doc_files:
        doc_id = sanitize_doc_id(src_path.stem)
        if doc_id in used_ids:
            doc_id = f"{doc_id}_{len(used_ids)}"
        used_ids.append(doc_id)

        try:
            entry, pages, doc_name = write_document(src_path, doc_id, out_dir)
        except Exception as e:
            print(f"    [WARN] Skipping {src_path.name}: {e}")
            skipped.append(src_path.name)
            continue

        index_entries.append(entry)

        doc_chunks = []
        for page_num, text in pages.items():
            doc_chunks.extend(chunk_page(text, doc_id, page_num, doc_name))
        all_chunks.extend(doc_chunks)
        print(f"     Chunks: {len(doc_chunks)} (from {len([t for t in pages.values() if t])} text pages)")

    if skipped:
        print(f"\n[SKIP] {len(skipped)} file(s) skipped (missing dependency?): {', '.join(skipped)}")

    total_chunks = build_vector_store(all_chunks, out_dir)

    chunk_counts: dict[str, int] = {}
    for c in all_chunks:
        chunk_counts[c["doc_id"]] = chunk_counts.get(c["doc_id"], 0) + 1
    for e in index_entries:
        e["chunks"] = chunk_counts.get(e["docId"], 0)

    total_bytes = sum(e["totalBytes"] for e in index_entries)

    index_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "documents": index_entries,
    }
    (out_dir / "index.json").write_text(
        json.dumps(index_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n── Summary " + "─" * 48)
    print(f"   Documents:    {len(doc_files)}")
    print(f"   Chunks:       {total_chunks}  (embedded locally, stored in Chroma)")
    print(f"   Total size:   {total_bytes / 1024:.1f} KB")
    print("\n" + "=" * 60)
    print("  [DONE] RAG data generation complete!")
    print("=" * 60)

    return {
        "documents": len(doc_files),
        "chunks": total_chunks,
        "totalBytes": total_bytes,
        "generated_at": index_payload["generated_at"],
    }


def main() -> None:
    """CLI entrypoint: scan agents/_uploads/ (+ public/ files if present)."""
    here = Path(__file__).resolve().parent          # agents/
    root = here.parent                               # project root
    uploads = here / "_uploads"
    public_files = root / "public" / "prepare-rag" / "files"
    out_dir = here / "_data"
    build([uploads, public_files], out_dir)


if __name__ == "__main__":
    main()
