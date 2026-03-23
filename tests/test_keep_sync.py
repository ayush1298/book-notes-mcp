from __future__ import annotations

from book_server.keep_sync import sync_once


def test_sync_once_imports_updates_and_skips(monkeypatch):
    upserts: list[dict] = []
    ingest_calls: list[dict] = []

    notes = [
        {"keep_id": "keep-1", "title": "New", "text": "new text", "updated_at": "2026-03-24T11:00:00Z"},
        {"keep_id": "keep-2", "title": "Same", "text": "same text", "updated_at": "2026-03-24T10:00:00Z"},
        {"keep_id": "keep-3", "title": "Updated", "text": "changed text", "updated_at": "2026-03-24T11:30:00Z"},
    ]
    sync_state = {
        "keep-2": {
            "keep_note_id": "keep-2",
            "note_id": "app-2",
            "keep_updated_at": "2026-03-24T10:00:00Z",
            "content_hash": "hash-same",
        },
        "keep-3": {
            "keep_note_id": "keep-3",
            "note_id": "app-3",
            "keep_updated_at": "2026-03-24T09:00:00Z",
            "content_hash": "hash-old",
        },
    }
    hashes = {
        "new text": "hash-new",
        "same text": "hash-same",
        "changed text": "hash-newer",
    }

    monkeypatch.setattr("book_server.keep_sync.list_notes", lambda label_name=None: notes)
    monkeypatch.setattr("book_server.keep_sync.db.list_keep_syncs", lambda keep_note_ids: sync_state)
    monkeypatch.setattr("book_server.keep_sync.db.content_hash", lambda text: hashes[text])
    monkeypatch.setattr(
        "book_server.keep_sync.ingest_note",
        lambda **kwargs: ingest_calls.append(kwargs) or {
            "note_id": f"stored-{len(ingest_calls)}",
            "book_title": "Atomic Habits",
        },
    )
    monkeypatch.setattr(
        "book_server.keep_sync.db.upsert_keep_sync",
        lambda **kwargs: upserts.append(kwargs),
    )

    result = sync_once()

    assert result["imported_count"] == 1
    assert result["updated_count"] == 1
    assert result["skipped_count"] == 1
    assert result["error_count"] == 0
    assert ingest_calls[0]["existing_note_id"] is None
    assert ingest_calls[1]["existing_note_id"] == "app-3"
    assert ingest_calls[0]["book_title"] == "New"
    assert upserts[0]["keep_note_id"] == "keep-1"
    assert upserts[1]["keep_note_id"] == "keep-3"


def test_sync_once_skips_empty_notes(monkeypatch):
    monkeypatch.setattr(
        "book_server.keep_sync.list_notes",
        lambda label_name=None: [{"keep_id": "keep-1", "text": "", "updated_at": "2026-03-24T11:00:00Z"}],
    )
    monkeypatch.setattr("book_server.keep_sync.db.list_keep_syncs", lambda keep_note_ids: {})

    result = sync_once()

    assert result["imported_count"] == 0
    assert result["updated_count"] == 0
    assert result["skipped_count"] == 1
