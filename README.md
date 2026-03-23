# book-notes-mcp

`book-notes-mcp` is a personal reading system for turning messy capture into usable notes.

The input can be rough: something typed quickly on your phone, an OCR scrape from a page, a voice transcript, or a note pulled in from Google Keep. The app processes that raw text once, stores the result in Supabase, generates embeddings, and makes it available through semantic search, RAG-style Q&A, and a small web interface.

It is built for one practical problem: reading produces a lot of fragments, but the value only shows up later when those fragments are easy to retrieve and connect.

## What the project does

- Processes raw notes into a structured shape: `book_title`, `summary`, `ideas`, `tags`, `actions`
- Stores both the raw capture and the processed note
- Builds embeddings for retrieval across your reading history
- Exposes the knowledge base through MCP tools, a web API, and a browser UI
- Syncs notes from Google Keep using `gkeepapi`

## Core tools

| Tool | Purpose |
| --- | --- |
| `process_note` | Turn one raw note into a stored note with metadata and embeddings |
| `search_notes` | Semantic search across the library |
| `ask_knowledge_base` | Answer a question using retrieved notes as context |
| `get_note` | Fetch one note by id |
| `list_notes` | Browse recent notes, optionally by tag |
| `link_notes` | Find related notes based on shared concepts |
| `sync_from_keep` | Poll the configured Google Keep label and import or update notes |

## How it is meant to be used

1. Capture notes wherever it is easiest.
   Google Keep is the intended inbox for phone capture because it handles typing, OCR, and voice well.
2. Let this project do the organizing.
   Raw text is processed into something cleaner and easier to search.
3. Retrieve later by concept, not by memory of exact wording.
   That is what the embeddings and Q&A layer are for.

## Stack

- FastAPI web app for the browser UI and HTTP endpoints
- Supabase for note storage and vector search
- LiteLLM for model routing
- MCP server for Claude Desktop / Cursor workflows
- `gkeepapi` for scheduled Google Keep sync

## Setup

### 1. Clone and install

```bash
git clone <your-repo>
cd book-notes-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Create `.env`

At minimum:

```bash
GEMINI_API_KEY=<your key>
SUPABASE_URL=<your project url>
SUPABASE_SERVICE_KEY=<your service role key>
```

Optional model configuration:

```bash
LLM_MODEL=gemini/gemini-2.5-flash
EMBEDDING_MODEL=gemini/text-embedding-004
VECTOR_DIM=768
```

Optional Keep sync configuration:

```bash
GOOGLE_EMAIL=<your google account email>
GOOGLE_APP_PASSWORD=<16-character app password>
KEEP_LABEL=book-note
KEEP_TOKEN_FILE=.keep_token
KEEP_SYNC_INTERVAL_MINUTES=5
```

### 3. Set up Supabase

Run [`schema.sql`](./schema.sql) in the Supabase SQL editor.

Note on vector size:

- Gemini `text-embedding-004`: use `vector(768)`
- OpenAI `text-embedding-3-small`: use `vector(1536)`
- If you change embedding dimensions, update both the schema and `VECTOR_DIM`

### 4. Connect the MCP server

Add this to Claude Desktop:

```json
{
  "mcpServers": {
    "book-notes": {
      "command": "/path/to/book-notes-mcp/.venv/bin/python",
      "args": ["/path/to/book-notes-mcp/book_server/server.py"],
      "env": {
        "PYTHONPATH": "/path/to/book-notes-mcp"
      }
    }
  }
}
```

## Running the app

Start the web app locally:

```bash
python web/app.py
```

Open:

- `http://localhost:8080` on the same machine
- `http://<your-local-ip>:8080` from your phone on the same network

## Google Keep sync

The intended setup is a dedicated Google account used only for capture. The server polls that account through `gkeepapi` and imports notes matching the configured Keep label.

### Authentication

1. Turn on 2-step verification for the Google account
2. Create a Google App Password
3. Put `GOOGLE_EMAIL` and `GOOGLE_APP_PASSWORD` in `.env`
4. Optionally set `KEEP_LABEL` if you do not want to use the default `book-note`

The first successful sync caches a Keep token in `KEEP_TOKEN_FILE`.

### Run one sync pass

```bash
book-notes-keep-sync
```

The sync behavior is:

- new Keep note with the configured label -> create a new note in the library
- changed Keep note -> update the existing mapped note and refresh its embedding
- unchanged Keep note -> skip
- deleted or missing Keep note -> no automatic deletion in the app

### Schedule it

Run the sync command every 5 minutes on the deployed server.

Example cron entry:

```bash
*/5 * * * * cd /path/to/book-notes-mcp && /path/to/.venv/bin/book-notes-keep-sync >> keep-sync.log 2>&1
```

## API surface

Web endpoints in [`web/app.py`](./web/app.py):

- `POST /api/process`
- `POST /api/ask`
- `POST /api/search`
- `GET /api/notes`
- `GET /api/notes/{id}`
- `GET /api/notes/{id}/link`
- `POST /api/webhook/keep`

## Development

Run tests:

```bash
pytest tests/ -v
```

The current test suite focuses on processing logic and Keep sync behavior with mocked external services.

## Project layout

```text
book-notes-mcp/
├── agent/                  RAG query logic
├── book_server/            MCP server, Keep sync, ingestion services
├── embeddings/             embedding generation and storage helpers
├── processing/             note extraction and summarization
├── storage/                Supabase and filesystem persistence
├── tests/                  unit tests
├── web/                    FastAPI app and frontend
├── config.py               environment-driven config
├── pyproject.toml          package metadata and scripts
└── schema.sql              database schema
```

## What is intentionally not here yet

- Delete propagation from Keep into the library
- Book-level rollups
- Graph-style visualization
- A polished mobile capture app of its own

That is deliberate. The project is currently optimized around capture, storage, and retrieval rather than around building a full reading platform.
