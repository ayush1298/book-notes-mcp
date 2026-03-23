# 📚 Book Notes MCP

A personal AI knowledge system for physical book reading.

Capture book notes (typed, pasted, or OCR'd), have them automatically summarized & tagged, stored with vector embeddings, and recall them semantically — all from inside Claude Desktop or Cursor.

---

## ✨ Features

| Tool | What it does |
|------|-------------|
| `process_note` | Paste any book text → LLM extracts summary, ideas, tags, actions → stored + embedded |
| `search_notes` | Semantic search across everything you've read |
| `ask_knowledge_base` | Ask a question → RAG answer synthesized from your notes |
| `get_note` | Retrieve a specific note by ID |
| `list_notes` | Browse notes, filter by tag |
| `link_notes` | Discover connections between notes across different books |
| `sync_from_keep_api` | Poll a dedicated Google Keep account via the official Keep API and import/update notes |

---

## 🚀 Setup

### 1. Clone & install

```bash
git clone <your-repo>
cd book-notes-mcp
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in your values
```

**Minimum required in `.env`:**
```
GEMINI_API_KEY=<your key from aistudio.google.com>
SUPABASE_URL=<your project URL>
SUPABASE_SERVICE_KEY=<your service_role key>
```

**For official Google Keep sync, also add:**
```
KEEP_CLIENT_ID=<oauth client id>
KEEP_CLIENT_SECRET=<oauth client secret>
KEEP_TOKEN_FILE=.keep_oauth_token.json
KEEP_SYNC_INTERVAL_MINUTES=5
```

### 3. Set up Supabase

1. Create a free project at [supabase.com](https://supabase.com)
2. Go to **Dashboard → SQL Editor → New query**
3. Paste the contents of [`schema.sql`](./schema.sql) and click **Run**

> **Note:** The schema defaults to `vector(768)` for Gemini/Ollama embeddings. If you switch to OpenAI (`text-embedding-3-small`), change `vector(768)` → `vector(1536)` and set `VECTOR_DIM=1536` in `.env`.

### 4. Connect to Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "book-notes": {
      "command": "/path/to/book-notes-mcp/.venv/bin/python",
      "args": ["/path/to/book-notes-mcp/mcp/server.py"],
      "env": {
        "PYTHONPATH": "/path/to/book-notes-mcp"
      }
    }
  }
}
```

Restart Claude Desktop. You should see a 🔌 icon in the chat input.

---

## 💡 Usage (in Claude)

**Add a new note:**
> *"Process this note: In Thinking Fast and Slow, Kahneman explains that System 1 operates automatically and quickly, with little or no effort..."*

**Search your notes:**
> *"Search my notes for cognitive bias"*

**Ask a question:**
> *"What have I read about building better habits?"*

**Browse notes:**
> *"List my notes tagged habits"*

**Find connections:**
> *"Find notes related to note ID abc-123"*

---

## 🔄 Switching LLM Providers

Edit `.env` — zero code changes needed:

```bash
# Gemini (default, free)
LLM_MODEL=gemini/gemini-2.5-flash
EMBEDDING_MODEL=gemini/text-embedding-004
VECTOR_DIM=768

# OpenAI
LLM_MODEL=openai/gpt-4o-mini
EMBEDDING_MODEL=openai/text-embedding-3-small
VECTOR_DIM=1536

# Ollama (local, free, no key)
LLM_MODEL=ollama/llama3
EMBEDDING_MODEL=ollama/nomic-embed-text
VECTOR_DIM=768

# Anthropic (no embedding support — pair with another embedding model)
LLM_MODEL=anthropic/claude-3-haiku-20240307
EMBEDDING_MODEL=gemini/text-embedding-004
VECTOR_DIM=768
```

> ⚠️ If you change `VECTOR_DIM`, you must recreate the Supabase `note_embeddings` table with the new vector size.

---

## 🧪 Running Tests

```bash
# Unit tests only (no API key needed — LLM is mocked)
pytest tests/test_processing.py -v

# All tests
pytest tests/ -v
```

## Google Keep Sync

Recommended setup: use a dedicated Google account for book capture in Google Keep, then poll that account from the server.

### 1. Enable Keep API + create OAuth credentials

1. In Google Cloud Console, enable the Google Keep API
2. Create an OAuth Client ID for a desktop app
3. Put `KEEP_CLIENT_ID` and `KEEP_CLIENT_SECRET` in `.env`

### 2. Bootstrap the token once

Run locally on a machine with a browser:

```bash
book-notes-keep-auth
```

This writes the refreshable OAuth token to `KEEP_TOKEN_FILE`. Deploy that token file securely with your server.

### 3. Run a sync pass manually

```bash
book-notes-keep-sync
```

The sync job:
- imports new Keep notes
- updates previously imported notes when the Keep note changed
- skips unchanged notes
- does not delete app notes if a Keep note is later removed

### 4. Schedule it on the deployed server

Run the sync command every 5 minutes using your hosting scheduler or cron.

Example cron:

```bash
*/5 * * * * cd /path/to/book-notes-mcp && /path/to/.venv/bin/book-notes-keep-sync >> keep-sync.log 2>&1
```

---

## 📁 Project Structure

```
book-notes-mcp/
├── mcp/
│   └── server.py          ← MCP server (main entrypoint)
├── processing/
│   └── summarizer.py      ← LLM extraction
├── storage/
│   ├── db.py              ← Supabase client
│   └── filesystem.py      ← Markdown backup
├── embeddings/
│   └── embed.py           ← LiteLLM embeddings
├── agent/
│   └── query_agent.py     ← RAG query agent
├── tests/
│   └── test_processing.py
├── notes/                 ← Auto-created, git-ignored
├── schema.sql             ← Run this in Supabase SQL Editor
├── config.py              ← Centralised settings
├── .env.example
└── pyproject.toml
```

---

## 🗺️ Roadmap

- [x] Core pipeline (process → store → embed → search)
- [x] MCP server with 6 tools
- [x] RAG query agent
- [x] Google Keep automatic import (official API poller)
- [ ] Knowledge graph visualisation
- [ ] Book-level summaries
