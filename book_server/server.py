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
    Tool(
        name="sync_from_keep",
        description=(
            "[EXPERIMENTAL] Sync new notes from Google Keep into the knowledge base via gkeepapi. "
            "May fail due to Google API restrictions. Use 'import_from_takeout' as a reliable alternative."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "description": "Keep label to filter notes (default: value of KEEP_LABEL in .env, usually 'book-note')",
                },
            },
        },
    ),
    Tool(
        name="import_from_takeout",
        description=(
            "Import Keep notes from a Google Takeout export into the knowledge base. "
            "More reliable than sync_from_keep. "
            "Steps: go to takeout.google.com → select only Keep → download zip → extract → "
            "call this tool with the path to the 'Keep' folder inside the extracted archive. "
            "Already-processed notes are skipped automatically."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "takeout_dir": {
                    "type": "string",
                    "description": "Absolute path to the 'Takeout/Keep' folder from the extracted Google Takeout archive",
                },
                "label": {
                    "type": "string",
                    "description": "Only import notes with this label (default: 'book-note'). Pass empty string to import all notes.",
                    "default": "book-note",
                },
            },
            "required": ["takeout_dir"],
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

    # ── sync_from_keep ────────────────────────────────────────────────────
    elif name == "sync_from_keep":
        from book_server.keep_client import fetch_unsynced_notes, mark_synced

        label = args.get("label")  # None → uses KEEP_LABEL from .env
        unsynced = fetch_unsynced_notes(label)

        if not unsynced:
            return {
                "message": "No new Keep notes to sync.",
                "synced_count": 0,
                "notes": [],
            }

        synced_notes = []
        errors = []

        for keep_note in unsynced:
            try:
                # Full pipeline
                processed = _process_note(keep_note["text"])
                note_id = db.insert_note(
                    raw_text=keep_note["text"],
                    source="keep",
                    book_title=processed.get("book_title"),
                    summary=processed.get("summary"),
                    ideas=processed.get("ideas"),
                    tags=processed.get("tags"),
                    actions=processed.get("actions"),
                )
                embed_text = processed["summary"] + " " + " ".join(processed.get("ideas", []))
                embed_and_store(note_id, embed_text)
                note_data = {**processed, "raw_text": keep_note["text"], "source": "keep"}
                filesystem.save_note(note_id, note_data)
                mark_synced(keep_note["keep_id"], note_id)

                synced_notes.append({
                    "keep_id": keep_note["keep_id"],
                    "note_id": note_id,
                    "book_title": processed.get("book_title"),
                    "tags": processed.get("tags"),
                })
            except Exception as exc:
                errors.append({"keep_id": keep_note["keep_id"], "error": str(exc)})

        return {
            "synced_count": len(synced_notes),
            "notes": synced_notes,
            "errors": errors,
        }

    # ── import_from_takeout ─────────────────────────────────────────────────
    elif name == "import_from_takeout":
        from book_server.takeout_client import load_notes_from_takeout

        takeout_dir = args["takeout_dir"]
        label = args.get("label", "book-note") or None  # empty string → None (all notes)

        raw_notes = load_notes_from_takeout(takeout_dir, label_filter=label)

        if not raw_notes:
            return {
                "message": f"No notes found in {takeout_dir} with label '{label}'.",
                "imported_count": 0,
                "notes": [],
            }

        # Deduplicate against already-processed source files via keep_synced table
        # (we use source_file as the keep_note_id for Takeout imports)
        from book_server.keep_client import mark_synced
        from storage.db import _client as db_client

        existing = (
            db_client().table("keep_synced")
            .select("keep_note_id")
            .in_("keep_note_id", [n["source_file"] for n in raw_notes])
            .execute()
        )
        already_done = {row["keep_note_id"] for row in (existing.data or [])}
        to_import = [n for n in raw_notes if n["source_file"] not in already_done]

        if not to_import:
            return {
                "message": "All notes in this Takeout export have already been imported.",
                "imported_count": 0,
                "skipped_count": len(raw_notes),
                "notes": [],
            }

        imported_notes = []
        errors = []

        for note in to_import:
            try:
                processed = _process_note(note["text"])
                note_id = db.insert_note(
                    raw_text=note["text"],
                    source="keep-takeout",
                    book_title=processed.get("book_title"),
                    summary=processed.get("summary"),
                    ideas=processed.get("ideas"),
                    tags=processed.get("tags"),
                    actions=processed.get("actions"),
                )
                embed_text = processed["summary"] + " " + " ".join(processed.get("ideas", []))
                embed_and_store(note_id, embed_text)
                note_data = {**processed, "raw_text": note["text"], "source": "keep-takeout"}
                filesystem.save_note(note_id, note_data)
                mark_synced(note["source_file"], note_id)  # track by filename

                imported_notes.append({
                    "source_file": note["source_file"],
                    "note_id": note_id,
                    "book_title": processed.get("book_title"),
                    "tags": processed.get("tags"),
                })
            except Exception as exc:
                errors.append({"source_file": note["source_file"], "error": str(exc)})

        return {
            "imported_count": len(imported_notes),
            "skipped_count": len(raw_notes) - len(to_import),
            "notes": imported_notes,
            "errors": errors,
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
