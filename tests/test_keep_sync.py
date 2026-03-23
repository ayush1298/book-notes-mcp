from __future__ import annotations

from book_server.keep_sync import sync_once


def test_sync_once_imports_updates_and_skips(monkeypatch):
    ingest_calls: list[dict] = []
    sync_updates: list[dict] = []

    notes = [
        {
            "keep_id": "keep-new",
            "title": "New Note",
            "text": "new text",
            "updated_at": "2026-03-24T11:00:00Z",
        },
        {
            "keep_id": "keep-same",
            "title": "Same Note",
            "text": "same text",
            "updated_at": "2026-03-24T10:00:00Z",
        },
        {
            "keep_id": "keep-updated",
            "title": "Updated Note",
            "text": "changed text",
            "updated_at": "2026-03-24T11:30:00Z",
        },
    ]

    sync_state = {
        "keep-same": {
            "keep_note_id": "keep-same",
            "note_id": "app-2",
            "keep_updated_at": "2026-03-24T10:00:00Z",
            "content_hash": "hash-same",
        },
        "keep-updated": {
            "keep_note_id": "keep-updated",
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
            "book_title": kwargs.get("book_title"),
        },
    )
    monkeypatch.setattr(
        "book_server.keep_sync.db.upsert_keep_sync",
        lambda **kwargs: sync_updates.append(kwargs),
    )

    result = sync_once()

    assert result["imported_count"] == 1
    assert result["updated_count"] == 1
    assert result["skipped_count"] == 1
    assert result["error_count"] == 0

    assert ingest_calls == [
        {
            "raw_text": "new text",
            "source": "keep",
            "book_title": "New Note",
            "existing_note_id": None,
        },
        {
            "raw_text": "changed text",
            "source": "keep",
            "book_title": "Updated Note",
            "existing_note_id": "app-3",
        },
    ]

    assert sync_updates == [
        {
            "keep_note_id": "keep-new",
            "note_id": "stored-1",
            "keep_updated_at": "2026-03-24T11:00:00Z",
            "content_hash": "hash-new",
        },
        {
            "keep_note_id": "keep-updated",
            "note_id": "stored-2",
            "keep_updated_at": "2026-03-24T11:30:00Z",
            "content_hash": "hash-newer",
        },
    ]


def test_sync_once_skips_empty_notes(monkeypatch):
    monkeypatch.setattr(
        "book_server.keep_sync.list_notes",
        lambda label_name=None: [{"keep_id": "keep-empty", "text": "", "updated_at": "2026-03-24T11:00:00Z"}],
    )
    monkeypatch.setattr("book_server.keep_sync.db.list_keep_syncs", lambda keep_note_ids: {})

    result = sync_once()

    assert result["imported_count"] == 0
    assert result["updated_count"] == 0
    assert result["skipped_count"] == 1
    assert result["skipped"][0] == {"keep_note_id": "keep-empty", "reason": "empty note"}


def test_sync_once_continues_when_one_note_fails(monkeypatch):
    sync_updates: list[dict] = []

    notes = [
        {
            "keep_id": "keep-bad",
            "title": "Bad Note",
            "text": "bad text",
            "updated_at": "2026-03-24T10:00:00Z",
        },
        {
            "keep_id": "keep-good",
            "title": "Good Note",
            "text": "good text",
            "updated_at": "2026-03-24T10:05:00Z",
        },
    ]

    monkeypatch.setattr("book_server.keep_sync.list_notes", lambda label_name=None: notes)
    monkeypatch.setattr("book_server.keep_sync.db.list_keep_syncs", lambda keep_note_ids: {})
    monkeypatch.setattr("book_server.keep_sync.db.content_hash", lambda text: f"hash-{text}")

    def fake_ingest_note(**kwargs):
        if kwargs["raw_text"] == "bad text":
            raise RuntimeError("LLM failure")
        return {"note_id": "stored-good", "book_title": kwargs.get("book_title")}

    monkeypatch.setattr("book_server.keep_sync.ingest_note", fake_ingest_note)
    monkeypatch.setattr(
        "book_server.keep_sync.db.upsert_keep_sync",
        lambda **kwargs: sync_updates.append(kwargs),
    )

    result = sync_once()

    assert result["imported_count"] == 1
    assert result["updated_count"] == 0
    assert result["error_count"] == 1
    assert result["errors"][0] == {"keep_note_id": "keep-bad", "error": "LLM failure"}
    assert sync_updates == [
        {
            "keep_note_id": "keep-good",
            "note_id": "stored-good",
            "keep_updated_at": "2026-03-24T10:05:00Z",
            "content_hash": "hash-good text",
        }
    ]
