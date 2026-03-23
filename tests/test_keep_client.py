from __future__ import annotations

from types import SimpleNamespace

from book_server.keep_client import _extract_text, _timestamps


def test_extract_text_includes_title_text_and_blob_text():
    note = SimpleNamespace(
        title="Atomic Habits",
        text="Make the cue obvious.",
        blobs=[SimpleNamespace(text="OCR text"), SimpleNamespace(text="")],
    )

    assert _extract_text(note) == "Atomic Habits\nMake the cue obvious.\n[OCR/Transcript]: OCR text"


def test_timestamps_handles_missing_values():
    note = SimpleNamespace(
        timestamps=SimpleNamespace(created=None, updated=None),
    )

    created_at, updated_at = _timestamps(note)

    assert created_at is None
    assert updated_at is None
