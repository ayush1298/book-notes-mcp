"""Supabase storage layer — notes table + vector similarity search."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from supabase import Client, create_client

import config


def _client() -> Client:
    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)


# ── Write ──────────────────────────────────────────────────────────────────

def insert_note(
    raw_text: str,
    source: str = "manual",
    book_title: str | None = None,
    summary: str | None = None,
    ideas: list[str] | None = None,
    tags: list[str] | None = None,
    actions: list[str] | None = None,
) -> str:
    """Insert a note and return its UUID string."""
    row = {
        "raw_text": raw_text,
        "source": source,
        "book_title": book_title,
        "summary": summary,
        "ideas": ideas or [],
        "tags": tags or [],
        "actions": actions or [],
    }
    result = _client().table("notes").insert(row).execute()
    return result.data[0]["id"]


def store_embedding(note_id: str, embedding: list[float]) -> None:
    """Store an embedding vector for a note."""
    _client().table("note_embeddings").insert(
        {"note_id": note_id, "embedding": embedding}
    ).execute()


def update_note(note_id: str, **fields: Any) -> None:
    """Patch arbitrary fields on an existing note."""
    _client().table("notes").update(fields).eq("id", note_id).execute()


# ── Read ───────────────────────────────────────────────────────────────────

def get_note(note_id: str) -> dict[str, Any] | None:
    result = _client().table("notes").select("*").eq("id", note_id).execute()
    return result.data[0] if result.data else None


def list_notes(
    limit: int = 20,
    offset: int = 0,
    tag: str | None = None,
) -> list[dict[str, Any]]:
    q = _client().table("notes").select("id,book_title,summary,tags,created_at")
    if tag:
        q = q.contains("tags", [tag])
    return q.order("created_at", desc=True).range(offset, offset + limit - 1).execute().data


def search_similar(
    query_embedding: list[float],
    threshold: float = 0.5,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Run pgvector similarity search via the match_notes RPC function."""
    result = _client().rpc(
        "match_notes",
        {
            "query_embedding": query_embedding,
            "match_threshold": threshold,
            "match_count": limit,
        },
    ).execute()
    return result.data or []
