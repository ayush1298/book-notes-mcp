"""Shared note ingestion flow used by web, MCP, and sync jobs."""
from __future__ import annotations

from typing import Any

from embeddings.embed import replace_embedding
from processing.summarizer import process_note as summarize_note
from storage import db, filesystem


def ingest_note(
    raw_text: str,
    source: str,
    book_title: str | None = None,
    existing_note_id: str | None = None,
) -> dict[str, Any]:
    """
    Process raw text and either create a new note or update an existing one.

    Returns the persisted note id plus extracted fields.
    """
    processed = summarize_note(raw_text)
    if book_title:
        processed["book_title"] = book_title

    if existing_note_id:
        existing_note = db.get_note(existing_note_id)
        if not existing_note:
            raise ValueError(f"Existing note {existing_note_id} not found")

        db.update_note(
            existing_note_id,
            raw_text=raw_text,
            source=source,
            book_title=processed.get("book_title"),
            summary=processed.get("summary"),
            ideas=processed.get("ideas"),
            tags=processed.get("tags"),
            actions=processed.get("actions"),
        )
        note_id = existing_note_id
        created_at = existing_note.get("created_at")
    else:
        note_id = db.insert_note(
            raw_text=raw_text,
            source=source,
            book_title=processed.get("book_title"),
            summary=processed.get("summary"),
            ideas=processed.get("ideas"),
            tags=processed.get("tags"),
            actions=processed.get("actions"),
        )
        created_at = None

    embed_text = _embedding_text(processed)
    replace_embedding(note_id, embed_text)

    note_data = {
        **processed,
        "raw_text": raw_text,
        "source": source,
        "created_at": created_at,
    }
    md_path = filesystem.save_note(note_id, note_data)

    return {
        "note_id": note_id,
        "book_title": processed.get("book_title"),
        "summary": processed.get("summary"),
        "ideas": processed.get("ideas"),
        "tags": processed.get("tags"),
        "actions": processed.get("actions"),
        "markdown_saved_to": str(md_path),
        "updated": existing_note_id is not None,
    }


def _embedding_text(processed: dict[str, Any]) -> str:
    summary = processed.get("summary") or ""
    ideas = " ".join(processed.get("ideas") or [])
    return f"{summary} {ideas}".strip()
