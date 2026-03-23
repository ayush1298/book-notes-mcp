from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from book_server.keep_client import _extract_text, _timestamps


def test_extract_text_combines_title_body_and_blob_text():
    note = SimpleNamespace(
        title="Atomic Habits",
        text="Make the cue obvious.",
        blobs=[
            SimpleNamespace(text="OCR on page"),
            SimpleNamespace(text="Voice transcript"),
        ],
    )

    assert _extract_text(note) == (
        "Atomic Habits\n"
        "Make the cue obvious.\n"
        "[OCR/Transcript]: OCR on page\n"
        "[OCR/Transcript]: Voice transcript"
    )


def test_extract_text_skips_empty_parts():
    note = SimpleNamespace(
        title="",
        text="",
        blobs=[SimpleNamespace(text=""), SimpleNamespace()],
    )

    assert _extract_text(note) == ""


def test_timestamps_returns_iso_strings():
    created = datetime(2026, 3, 24, 10, 15, tzinfo=timezone.utc)
    updated = datetime(2026, 3, 24, 12, 45, tzinfo=timezone.utc)
    note = SimpleNamespace(
        timestamps=SimpleNamespace(created=created, updated=updated),
    )

    created_at, updated_at = _timestamps(note)

    assert created_at == "2026-03-24T10:15:00+00:00"
    assert updated_at == "2026-03-24T12:45:00+00:00"


def test_timestamps_handles_missing_values():
    note = SimpleNamespace(
        timestamps=SimpleNamespace(created=None, updated=None),
    )

    created_at, updated_at = _timestamps(note)

    assert created_at is None
    assert updated_at is None
