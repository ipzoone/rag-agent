# RAG Agent

A retrieval-augmented chat agent on EdgeOne Makers — answers questions over a local PDF knowledge base with citation-backed responses, streamed over SSE. Backend uses the OpenAI Agents SDK (Python).

**Framework:** OpenAI Agents SDK · **Category:** File Processing <!-- TODO: confirm --> · **Language:** Python

[![Deploy to EdgeOne Makers](https://cdnstatic.tencentcs.com/edgeone/pages/deploy.svg)](https://edgeone.ai/makers/new?template=rag-agent&from=within&fromAgent=1&agentLang=python)

<!-- ![preview](./assets/preview.png)  TODO: confirm -->

## Overview

A working enterprise-style RAG template: drop documents (PDF, DOCX, XLSX, PPTX) into `public/prepare-rag/files/`, run one script, and the agent answers grounded questions with page-level citations. Retrieval uses a **local Chroma vector store** with **free, offline embeddings** (`fastembed` + `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`) — no external vector DB service and no embedding API key required, so the template stays readable and costs nothing to run. Replace the embedder/store with your own and the rest of the pipeline keeps working.

- **Citation-backed answers** — every claim links back to a specific document + page via `search_document` and `fetch_pages` tools.
- **Streaming + tool visibility** — the UI surfaces `tool-input-available` / `tool-output-available` events so users see which sources the agent reads, in real time.
- **Filesystem knowledge base + local vector store** — `prepare_rag_data.py` extracts PDFs into `agents/_data/{docId}/pages/{n}.txt` **and** embeds them (chunked) into an embedded Chroma collection at `agents/_data/chroma/`. `_vector.py` does cosine-similarity search over those embeddings; `_loader.py` reads raw page text at request time, path-traversal-safe.
- **Sticky session memory** — `context.store.openai_session(conversation_id)` keeps multi-turn context within a conversation; the stateless `/history` cloud function rehydrates the chat after a refresh.
- **Honest stop** — `/stop` calls `context.utils.abort_active_run()` to interrupt the LLM call mid-stream.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AI_GATEWAY_API_KEY` | Yes | Model gateway API key. Use your Makers Models API Key, or any OpenAI-compatible provider key. |
| `AI_GATEWAY_BASE_URL` | Yes | Gateway base URL. For Makers Models, use `https://ai-gateway.edgeone.link/v1`. |
| `AI_GATEWAY_MODEL` | No | Model ID. Defaults to `@makers/deepseek-v4-flash` (a free built-in model). |

This template follows the OpenAI-compatible standard — point these at Makers Models or any compatible provider.

### How to get `AI_GATEWAY_API_KEY`

1. Open the [Makers Console](https://edgeone.ai/makers/new?s_url=https://console.tencentcloud.com/edgeone/makers).
2. Sign in and enable Makers.
3. Go to **Makers → Models → API Key** and create a key.
4. Copy it into `AI_GATEWAY_API_KEY`.

The built-in `@makers/deepseek-v4-flash` model is free with a usage cap and is suitable for prototyping. For production, bind your own paid provider (BYOK).

## Local Development

Prerequisites: Node.js ≥ 18, Python ≥ 3.10, and the EdgeOne CLI (`npm i -g edgeone`).

```bash
npm install
pip install -r agents/requirements.txt
pip install -r public/prepare-rag/requirements.txt
cp .env.example .env       # then fill in AI_GATEWAY_API_KEY / AI_GATEWAY_BASE_URL

# Drop PDFs into public/prepare-rag/files/, then build the knowledge base
npm run prepare-rag

edgeone makers dev
```

Local agent metrics & traces are exposed at `http://localhost:8080/agent-metrics`.

## Project Structure

```text
rag-agent/
├── agents/                          # Stateful EdgeOne Makers Agent Functions (Python)
│   ├── chat/index.py               # POST /chat — streaming RAG chat
│   ├── chat/_stream.py             # SSE streaming utilities (private)
│   ├── stop/index.py               # POST /stop — abort active agent run
│   ├── rag-stats/index.py          # POST /rag-stats — knowledge base stats
│   ├── admin-login/index.py        # POST /admin-login — password → token
│   ├── admin-files/index.py        # POST /admin-files — list KB sources + index
│   ├── admin-upload/index.py       # POST /admin-upload — upload a doc (base64)
│   ├── admin-delete/index.py       # POST /admin-delete — remove a source doc
│   ├── admin-rebuild/index.py      # POST /admin-rebuild — run prepare-rag
│   ├── _admin_auth.py              # Admin auth + path helpers (private)
│   ├── _prepare_rag.py             # Canonical KB builder (private, sandbox-safe)
│   ├── _uploads/                   # Documents uploaded via the admin panel
│   ├── _agent.py                   # RAG Agent definition (private)
│   ├── _tools.py                   # search_document, fetch_pages tools (private)
│   ├── _loader.py                  # Filesystem knowledge base reader (private)
│   ├── _model.py                   # LLM configuration (private)
│   ├── _data/                      # Generated knowledge base (gitignored)
│   └── requirements.txt            # Python agent dependencies
├── cloud-functions/                 # Stateless EdgeOne Makers Python cloud functions
│   ├── history/index.py            # POST /history — load conversation messages
│   └── _logger.py                  # Logger utility
├── public/prepare-rag/              # PDF → structured text pipeline
│   ├── prepare_rag_data.py
│   ├── requirements.txt
│   └── files/                      # Drop your source PDFs here
├── src/                             # React + Vite frontend
│   ├── App.tsx                     # Root component
│   ├── adminApi.ts                 # Admin panel API client
│   ├── pages/Admin.tsx            # Admin dashboard (/#/admin)
│   ├── api.ts                      # SSE stream client
│   └── components/
│       ├── RagChat.tsx             # Chat UI with streaming + tool visibility
│       ├── CitationCard.tsx        # Source citation display
│       └── KnowledgeBaseSummary.tsx
├── package.json
├── edgeone.json                     # framework=openai-agents-sdk, agents.timeout=300, sandbox.timeout=300
└── vite.config.ts
```

> Files prefixed with `_` are private modules — not exposed as public routes.

## How It Works

`agents/` runs in **conversation mode**: requests carrying the same `Markers-Conversation-Id` HTTP header are sticky-routed to the same agent instance, sharing the same in-memory state and the same EdgeOne sandbox. That stickiness is what lets `/chat` (the SSE stream) and `/stop` (the abort) reach the same running task. `/stop` deliberately receives the conversation id in the request body — never in the header — so the cancel signal doesn't collide with the live SSE stream.

End-to-end:

1. **Build the knowledge base (offline)** — `prepare_rag_data.py` reads documents (`.pdf`, `.docx`, `.xlsx`, `.pptx`) from `public/prepare-rag/files/`, writes `agents/_data/{docId}/meta.json` + `pages/{n}.txt`, and chunks + embeds the text into an embedded Chroma collection (`agents/_data/chroma/`) using local `fastembed` embeddings. `agents/_data/index.json` is the document manifest. The embedding model (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, ~470 MB) downloads once and is cached; subsequent runs are fully offline.
2. **Request entry** — `POST /chat` (handled by `agents/chat/index.py`) pulls history via `context.store.openai_session(conversation_id)` and starts an OpenAI Agents SDK run for the `_agent.py` agent definition.
 3. **LLM ↔ tools loop** — the agent has access to two tools defined in `_tools.py`:
    - `search_document(query, doc_id)` — embeds the query locally and returns the most semantically similar chunks (ranked by cosine similarity) from the Chroma vector store for that document
    - `fetch_pages(doc_id, pages)` — reads exact page text for citation/expansion
    The agent runs up to 6 turns; `_loader.py` enforces path-traversal-safe filesystem reads under `Path(__file__).parent / "_data"`.
4. **Streaming** — the handler emits SSE events `start`, `text-start`, `text-delta`, `text-end`, `tool-input-available`, `tool-output-available`, `finish`, `error`. The UI's `useAgentStream` reducer turns those into chat bubbles + citation cards.
5. **Stats / history / stop** — `POST /rag-stats` (in `agents/`) returns knowledge-base metadata; `POST /history` (in `cloud-functions/`) reads `context.agent.store.get_messages()` to rehydrate after a refresh; `POST /stop` cancels the live run.

## Admin Panel (manage the knowledge base from the dashboard)

Open `/#/admin` in the browser. It is a password-gated dashboard that lets you grow the
agent's vector store without touching the build pipeline manually:

- **Login** — `POST /admin-login` verifies `ADMIN_PASSWORD` and returns a token (HMAC of the
  password under `ADMIN_SECRET`). The token is stored in `localStorage` and sent with every
  protected call. If `ADMIN_PASSWORD` is empty, the panel is disabled.
- **Upload** — `POST /admin-upload` accepts a document as base64 (`{token, filename, data}`),
  validates the extension (`.pdf/.docx/.xlsx/.pptx`), strips any path components, and writes it
  into `public/prepare-rag/files/`.
- **List / Delete** — `POST /admin-files` and `POST /admin-delete` show and remove source files.
- **Rebuild** — `POST /admin-rebuild` calls the canonical builder in `agents/_prepare_rag.py`
  **in-process** (no subprocess, no dependency on files outside the deployed `agents/`
  directory). It scans `agents/_uploads/` plus `public/prepare-rag/files/` (if present, i.e. local
  full builds), re-embeds everything locally with `fastembed`, and rewrites `agents/_data`.

After a rebuild, the chat's vector layer auto-reloads (mtime watermark in `agents/_vector.py`) so
new documents are queryable without restarting the agent.

> **Why everything lives in `agents/`:** the EdgeOne Makers agent runtime only deploys the
> `agents/` directory — `public/` is not present in the sandbox. So uploads go to
> `agents/_uploads/`, the builder runs from `agents/_prepare_rag.py`, and vectors are written to
> `agents/_data/` (all inside the sandbox the chat agent already reads). `public/prepare-rag/
> prepare_rag_data.py` is now just a thin shim for the local `npm run prepare-rag` full build.

Sandbox credentials are injected by the runtime — no local sandbox config is needed. Per `edgeone.json`, both the agent and its sandbox have a 300-second timeout (`agents.timeout`, `agents.sandbox.timeout`).

The bundled sample knowledge base includes:

- **EdgeOne-Pages-Platform-Guide.pdf** — platform architecture, `context.store`, SSE streaming, deployment.
- **Building-RAG-Applications.pdf** — RAG patterns, retrieval strategies, citations, evaluation.

## Resources

- [EdgeOne Makers Agents — Documentation](https://pages.edgeone.ai/document/agents)
- [EdgeOne Makers — Quick Start](https://pages.edgeone.ai/document/agents-quick-start)
- [Makers Models](https://pages.edgeone.ai/document/models)

## License

MIT.
