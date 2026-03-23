from __future__ import annotations

from pathlib import Path

from book_server.ingestion import ingest_note


PROCESSED = {
    "book_title": "Atomic Habits",
    "summary": "• Build systems",
    "ideas": ["Systems beat goals"],
    "tags": ["habits"],
    "actions": ["Track one habit"],
}


def test_ingest_note_creates_new_note(monkeypatch):
    calls: dict[str, object] = {}

    monkeypatch.setattr("book_server.ingestion.summarize_note", lambda raw_text: PROCESSED)
    def fake_insert_note(**kwargs):
        calls["insert"] = kwargs
        return "note-123"

    def fake_save_note(note_id, data):
        calls["save"] = (note_id, data)
        return Path("/tmp/note-123.md")

    monkeypatch.setattr("book_server.ingestion.db.insert_note", fake_insert_note)
    monkeypatch.setattr(
        "book_server.ingestion.replace_embedding",
        lambda note_id, text: calls.setdefault("embedding", (note_id, text)),
    )
    monkeypatch.setattr("book_server.ingestion.filesystem.save_note", fake_save_note)

    result = ingest_note(raw_text="raw note", source="manual")

    assert calls["insert"]["raw_text"] == "raw note"
    assert result["updated"] is False
    assert result["book_title"] == "Atomic Habits"


def test_ingest_note_updates_existing_note(monkeypatch):
    calls: dict[str, object] = {}

    monkeypatch.setattr("book_server.ingestion.summarize_note", lambda raw_text: PROCESSED)
    monkeypatch.setattr(
        "book_server.ingestion.db.get_note",
        lambda note_id: {"id": note_id, "created_at": "2026-03-24T00:00:00Z"},
    )
    monkeypatch.setattr(
        "book_server.ingestion.db.update_note",
        lambda note_id, **kwargs: calls.setdefault("update", (note_id, kwargs)),
    )
    monkeypatch.setattr(
        "book_server.ingestion.replace_embedding",
        lambda note_id, text: calls.setdefault("embedding", (note_id, text)),
    )
    def fake_save_note(note_id, data):
        calls["save"] = (note_id, data)
        return Path("/tmp/existing.md")

    monkeypatch.setattr("book_server.ingestion.filesystem.save_note", fake_save_note)

    result = ingest_note(raw_text="changed note", source="keep", existing_note_id="note-123")

    note_id, fields = calls["update"]
    assert note_id == "note-123"
    assert fields["raw_text"] == "changed note"
    assert result["updated"] is True
    assert result["note_id"] == "note-123"
