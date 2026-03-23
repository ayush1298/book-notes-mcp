from __future__ import annotations

from pathlib import Path

import pytest

from book_server.ingestion import ingest_note


PROCESSED_NOTE = {
    "book_title": "Atomic Habits",
    "summary": "• Systems matter more than goals",
    "ideas": ["Systems beat goals", "Environment shapes behavior"],
    "tags": ["habits", "systems"],
    "actions": ["Design a better cue"],
}


def test_ingest_note_creates_new_note(monkeypatch):
    calls: dict[str, object] = {}

    monkeypatch.setattr("book_server.ingestion.summarize_note", lambda raw_text: dict(PROCESSED_NOTE))

    def fake_insert_note(**kwargs):
        calls["insert_note"] = kwargs
        return "note-new"

    def fake_replace_embedding(note_id, text):
        calls["replace_embedding"] = (note_id, text)

    def fake_save_note(note_id, data):
        calls["save_note"] = (note_id, data)
        return Path("/tmp/note-new.md")

    monkeypatch.setattr("book_server.ingestion.db.insert_note", fake_insert_note)
    monkeypatch.setattr("book_server.ingestion.replace_embedding", fake_replace_embedding)
    monkeypatch.setattr("book_server.ingestion.filesystem.save_note", fake_save_note)

    result = ingest_note(raw_text="raw capture", source="manual")

    assert result["note_id"] == "note-new"
    assert result["updated"] is False
    assert calls["insert_note"] == {
        "raw_text": "raw capture",
        "source": "manual",
        "book_title": "Atomic Habits",
        "summary": "• Systems matter more than goals",
        "ideas": ["Systems beat goals", "Environment shapes behavior"],
        "tags": ["habits", "systems"],
        "actions": ["Design a better cue"],
    }
    assert calls["replace_embedding"] == (
        "note-new",
        "• Systems matter more than goals Systems beat goals Environment shapes behavior",
    )
    saved_note_id, saved_payload = calls["save_note"]
    assert saved_note_id == "note-new"
    assert saved_payload["raw_text"] == "raw capture"
    assert saved_payload["source"] == "manual"


def test_ingest_note_updates_existing_note(monkeypatch):
    calls: dict[str, object] = {}

    monkeypatch.setattr("book_server.ingestion.summarize_note", lambda raw_text: dict(PROCESSED_NOTE))
    monkeypatch.setattr(
        "book_server.ingestion.db.get_note",
        lambda note_id: {"id": note_id, "created_at": "2026-03-24T00:00:00Z"},
    )

    def fake_update_note(note_id, **kwargs):
        calls["update_note"] = (note_id, kwargs)

    def fake_replace_embedding(note_id, text):
        calls["replace_embedding"] = (note_id, text)

    def fake_save_note(note_id, data):
        calls["save_note"] = (note_id, data)
        return Path("/tmp/note-existing.md")

    monkeypatch.setattr("book_server.ingestion.db.update_note", fake_update_note)
    monkeypatch.setattr("book_server.ingestion.replace_embedding", fake_replace_embedding)
    monkeypatch.setattr("book_server.ingestion.filesystem.save_note", fake_save_note)

    result = ingest_note(raw_text="updated capture", source="keep", existing_note_id="note-123")

    assert result["note_id"] == "note-123"
    assert result["updated"] is True
    assert calls["update_note"] == (
        "note-123",
        {
            "raw_text": "updated capture",
            "source": "keep",
            "book_title": "Atomic Habits",
            "summary": "• Systems matter more than goals",
            "ideas": ["Systems beat goals", "Environment shapes behavior"],
            "tags": ["habits", "systems"],
            "actions": ["Design a better cue"],
        },
    )
    assert calls["replace_embedding"][0] == "note-123"
    saved_note_id, saved_payload = calls["save_note"]
    assert saved_note_id == "note-123"
    assert saved_payload["created_at"] == "2026-03-24T00:00:00Z"


def test_ingest_note_uses_explicit_book_title(monkeypatch):
    monkeypatch.setattr("book_server.ingestion.summarize_note", lambda raw_text: dict(PROCESSED_NOTE))
    monkeypatch.setattr("book_server.ingestion.db.insert_note", lambda **kwargs: "note-title")
    monkeypatch.setattr("book_server.ingestion.replace_embedding", lambda note_id, text: None)
    monkeypatch.setattr("book_server.ingestion.filesystem.save_note", lambda note_id, data: Path("/tmp/title.md"))

    result = ingest_note(raw_text="raw capture", source="manual", book_title="Manual Override")

    assert result["book_title"] == "Manual Override"


def test_ingest_note_raises_when_existing_note_missing(monkeypatch):
    monkeypatch.setattr("book_server.ingestion.summarize_note", lambda raw_text: dict(PROCESSED_NOTE))
    monkeypatch.setattr("book_server.ingestion.db.get_note", lambda note_id: None)

    with pytest.raises(ValueError, match="Existing note note-missing not found"):
        ingest_note(raw_text="raw capture", source="keep", existing_note_id="note-missing")
