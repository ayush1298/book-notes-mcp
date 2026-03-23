from __future__ import annotations

from book_server.keep_sync import sync_once


def test_sync_once_imports_updates_and_skips(monkeypatch):
    upserts: list[dict] = []
    ingest_calls: list[dict] = []

    notes = [
        {"name": "notes/1", "title": "New"},
        {"name": "notes/2", "title": "Same"},
        {"name": "notes/3", "title": "Updated"},
    ]
    sync_state = {
        "notes/2": {
            "keep_note_id": "notes/2",
            "note_id": "app-2",
            "keep_updated_at": "2026-03-24T10:00:00Z",
            "content_hash": "hash-same",
        },
        "notes/3": {
            "keep_note_id": "notes/3",
            "note_id": "app-3",
            "keep_updated_at": "2026-03-24T09:00:00Z",
            "content_hash": "hash-old",
        },
    }
    texts = {
        "notes/1": "new text",
        "notes/2": "same text",
        "notes/3": "changed text",
    }
    updated_times = {
        "notes/1": "2026-03-24T11:00:00Z",
        "notes/2": "2026-03-24T10:00:00Z",
        "notes/3": "2026-03-24T11:30:00Z",
    }
    hashes = {
        "new text": "hash-new",
        "same text": "hash-same",
        "changed text": "hash-newer",
    }

    monkeypatch.setattr("book_server.keep_sync.connect", lambda: object())
    monkeypatch.setattr("book_server.keep_sync.iter_notes", lambda service: iter(notes))
    monkeypatch.setattr("book_server.keep_sync.extract_text", lambda note: texts[note["name"]])
    monkeypatch.setattr("book_server.keep_sync.modified_time", lambda note: updated_times[note["name"]])
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
    assert upserts[0]["keep_note_id"] == "notes/1"
    assert upserts[1]["keep_note_id"] == "notes/3"


def test_sync_once_skips_empty_notes(monkeypatch):
    monkeypatch.setattr("book_server.keep_sync.connect", lambda: object())
    monkeypatch.setattr("book_server.keep_sync.iter_notes", lambda service: iter([{"name": "notes/1"}]))
    monkeypatch.setattr("book_server.keep_sync.extract_text", lambda note: "")
    monkeypatch.setattr("book_server.keep_sync.modified_time", lambda note: "2026-03-24T11:00:00Z")
    monkeypatch.setattr("book_server.keep_sync.db.list_keep_syncs", lambda keep_note_ids: {})
    monkeypatch.setattr("book_server.keep_sync.db.content_hash", lambda text: "hash")

    result = sync_once()

    assert result["imported_count"] == 0
    assert result["updated_count"] == 0
    assert result["skipped_count"] == 1
