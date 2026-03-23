"""Supabase storage layer — notes table + vector similarity search."""
from __future__ import annotations

from hashlib import sha256
from typing import Any

try:
    from supabase import Client, create_client
except ImportError:  # pragma: no cover - exercised only in minimal test envs
    Client = Any  # type: ignore[misc,assignment]
    create_client = None

import config


def _client() -> Client:
    if create_client is None:
        raise ModuleNotFoundError(
            "supabase is not installed. Install project dependencies before using storage.db."
        )
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


def delete_embeddings(note_id: str) -> None:
    """Delete all stored embeddings for a note before re-embedding updated content."""
    _client().table("note_embeddings").delete().eq("note_id", note_id).execute()


def update_note(note_id: str, **fields: Any) -> None:
    """Patch arbitrary fields on an existing note."""
    _client().table("notes").update(fields).eq("id", note_id).execute()


def get_keep_sync(keep_note_id: str) -> dict[str, Any] | None:
    result = (
        _client()
        .table("keep_synced")
        .select("*")
        .eq("keep_note_id", keep_note_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def list_keep_syncs(keep_note_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not keep_note_ids:
        return {}
    result = (
        _client()
        .table("keep_synced")
        .select("*")
        .in_("keep_note_id", keep_note_ids)
        .execute()
    )
    return {row["keep_note_id"]: row for row in (result.data or [])}


def upsert_keep_sync(
    keep_note_id: str,
    note_id: str | None,
    keep_updated_at: str | None,
    content_hash: str | None = None,
) -> None:
    _client().table("keep_synced").upsert(
        {
            "keep_note_id": keep_note_id,
            "note_id": note_id,
            "keep_updated_at": keep_updated_at,
            "content_hash": content_hash,
        },
        on_conflict="keep_note_id",
    ).execute()


def content_hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


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


def link_notes(note_id: str, limit: int = 5) -> list[dict[str, Any]]:
    """Find notes conceptually related to a given note based on shared tags."""
    note = get_note(note_id)
    if not note:
        return []

    tags = note.get("tags") or []
    linked: list[dict[str, Any]] = []
    seen: set[str] = {note_id}
    
    for tag in tags:
        for candidate in list_notes(limit=20, tag=tag):
            cid = candidate["id"]
            if cid not in seen:
                candidate["similarity"] = 0.85  # mock similarity for UI display if tag matched 
                linked.append(candidate)
                seen.add(cid)
        if len(linked) >= limit:
            break

    return linked[:limit]


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
