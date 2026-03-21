"""
Book Notes MCP Server

Exposes these tools to Claude Desktop / Cursor:
  • process_note      — run raw text through the full pipeline
  • search_notes      — semantic search across your knowledge base
  • ask_knowledge_base — full RAG: question → answer with sources
  • get_note          — retrieve a note by ID
  • list_notes        — list all notes (optionally filtered by tag)
  • link_notes        — find notes sharing related tags/ideas

Setup (Claude Desktop):  see README.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure project root is on the path so submodules resolve correctly
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

import config  # noqa: F401 — triggers NOTES_DIR creation on import
from agent.query_agent import answer_query
from embeddings.embed import embed_and_store
from processing.summarizer import process_note as _process_note
from storage import db, filesystem

# ── Server setup ───────────────────────────────────────────────────────────

app = Server("book-notes-mcp")

# ── Tool definitions ───────────────────────────────────────────────────────

TOOLS = [
    Tool(
        name="process_note",
        description=(
            "Process a raw book note through the full AI pipeline: "
            "summarize, extract ideas/tags/actions, store in DB, create embedding. "
            "Use this when you have new text from a book (typed, pasted, or OCR'd)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "raw_text": {
                    "type": "string",
                    "description": "The raw text from the book note",
                },
                "source": {
                    "type": "string",
                    "description": "Where the note came from: 'manual', 'keep', 'voice'",
                    "default": "manual",
                },
                "book_title": {
                    "type": "string",
                    "description": "Optional: book title if known (LLM will infer if omitted)",
                },
            },
            "required": ["raw_text"],
        },
    ),
    Tool(
        name="search_notes",
        description=(
            "Semantic search across your personal book note knowledge base. "
            "Returns the most relevant notes for a query."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for, e.g. 'decision making under uncertainty'",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of results to return (default 5)",
                    "default": 5,
                },
                "threshold": {
                    "type": "number",
                    "description": "Minimum similarity score 0-1 (default 0.4)",
                    "default": 0.4,
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="ask_knowledge_base",
        description=(
            "Ask a question and get a synthesized answer from your book notes. "
            "Uses RAG: finds relevant notes, then generates a coherent answer with citations."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Your question, e.g. 'What have I read about building habits?'",
                },
            },
            "required": ["question"],
        },
    ),
    Tool(
        name="get_note",
        description="Retrieve the full details of a specific note by its ID.",
        inputSchema={
            "type": "object",
            "properties": {
                "note_id": {
                    "type": "string",
                    "description": "The UUID of the note",
                },
            },
            "required": ["note_id"],
        },
    ),
    Tool(
        name="list_notes",
        description=(
            "List your book notes, most recent first. "
            "Optionally filter by tag."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max number of notes to return (default 10)",
                    "default": 10,
                },
                "tag": {
                    "type": "string",
                    "description": "Optional: filter by tag, e.g. 'habits'",
                },
            },
        },
    ),
    Tool(
        name="link_notes",
        description=(
            "Find notes that are conceptually related to a given note based on shared tags and ideas. "
            "Useful for discovering connections across books."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "note_id": {
                    "type": "string",
                    "description": "UUID of the source note",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max related notes to return (default 5)",
                    "default": 5,
                },
            },
            "required": ["note_id"],
        },
    ),
]


# ── Tool registry ──────────────────────────────────────────────────────────

@app.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


# ── Tool handlers ──────────────────────────────────────────────────────────

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        result = await _dispatch(name, arguments)
    except Exception as exc:
        result = {"error": str(exc)}
    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


async def _dispatch(name: str, args: dict) -> dict:
    # ── process_note ──────────────────────────────────────────────────────
    if name == "process_note":
        raw_text = args["raw_text"]
        source = args.get("source", "manual")
        provided_title = args.get("book_title")

        # LLM extraction
        processed = _process_note(raw_text)

        # Prefer caller-supplied title over LLM-inferred
        if provided_title:
            processed["book_title"] = provided_title

        # Persist to Supabase
        note_id = db.insert_note(
            raw_text=raw_text,
            source=source,
            book_title=processed.get("book_title"),
            summary=processed.get("summary"),
            ideas=processed.get("ideas"),
            tags=processed.get("tags"),
            actions=processed.get("actions"),
        )

        # Embed summary (most information-dense text)
        embed_text = processed["summary"] + " " + " ".join(processed.get("ideas", []))
        embed_and_store(note_id, embed_text)

        # Save markdown backup
        note_data = {**processed, "raw_text": raw_text, "source": source}
        md_path = filesystem.save_note(note_id, note_data)

        return {
            "note_id": note_id,
            "book_title": processed.get("book_title"),
            "summary": processed.get("summary"),
            "ideas": processed.get("ideas"),
            "tags": processed.get("tags"),
            "actions": processed.get("actions"),
            "markdown_saved_to": str(md_path),
        }

    # ── search_notes ──────────────────────────────────────────────────────
    elif name == "search_notes":
        from embeddings.embed import get_embedding

        query = args["query"]
        limit = int(args.get("limit", 5))
        threshold = float(args.get("threshold", 0.4))

        query_embedding = get_embedding(query)
        notes = db.search_similar(query_embedding, threshold=threshold, limit=limit)

        return {
            "query": query,
            "results_count": len(notes),
            "results": notes,
        }

    # ── ask_knowledge_base ────────────────────────────────────────────────
    elif name == "ask_knowledge_base":
        question = args["question"]
        return answer_query(question)

    # ── get_note ──────────────────────────────────────────────────────────
    elif name == "get_note":
        note = db.get_note(args["note_id"])
        if not note:
            return {"error": f"Note {args['note_id']} not found"}
        return note

    # ── list_notes ────────────────────────────────────────────────────────
    elif name == "list_notes":
        limit = int(args.get("limit", 10))
        tag = args.get("tag")
        notes = db.list_notes(limit=limit, tag=tag)
        return {"count": len(notes), "notes": notes}

    # ── link_notes ────────────────────────────────────────────────────────
    elif name == "link_notes":
        note = db.get_note(args["note_id"])
        if not note:
            return {"error": f"Note {args['note_id']} not found"}

        limit = int(args.get("limit", 5))
        tags = note.get("tags") or []

        # Find notes sharing at least one tag
        linked: list[dict] = []
        seen: set[str] = {args["note_id"]}
        for tag in tags:
            for candidate in db.list_notes(limit=20, tag=tag):
                cid = candidate["id"]
                if cid not in seen:
                    candidate["matched_tag"] = tag
                    linked.append(candidate)
                    seen.add(cid)
            if len(linked) >= limit:
                break

        return {
            "source_note_id": args["note_id"],
            "source_tags": tags,
            "linked_notes": linked[:limit],
        }

    else:
        return {"error": f"Unknown tool: {name}"}


# ── Entry point ────────────────────────────────────────────────────────────

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def entrypoint():
    import asyncio
    asyncio.run(main())


if __name__ == "__main__":
    entrypoint()
