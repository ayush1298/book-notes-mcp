"""Scheduled Google Keep sync job using gkeepapi."""
from __future__ import annotations

import json
from typing import Any

from book_server.ingestion import ingest_note
from book_server.keep_client import list_notes
from storage import db


def sync_once(label_name: str | None = None) -> dict[str, Any]:
    notes = list_notes(label_name)
    sync_state = db.list_keep_syncs([note["keep_id"] for note in notes])

    imported: list[dict[str, Any]] = []
    updated: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for keep_note in notes:
        keep_note_id = keep_note["keep_id"]
        keep_updated_at = keep_note.get("updated_at")
        text = keep_note["text"]
        prior = sync_state.get(keep_note_id)

        if not text:
            skipped.append({"keep_note_id": keep_note_id, "reason": "empty note"})
            continue

        content_hash = db.content_hash(text)

        if prior and prior.get("keep_updated_at") == keep_updated_at and prior.get("content_hash") == content_hash:
            skipped.append({"keep_note_id": keep_note_id, "reason": "unchanged"})
            continue

        try:
            result = ingest_note(
                raw_text=text,
                source="keep",
                book_title=keep_note.get("title") or None,
                existing_note_id=prior.get("note_id") if prior else None,
            )
            db.upsert_keep_sync(
                keep_note_id=keep_note_id,
                note_id=result["note_id"],
                keep_updated_at=keep_updated_at,
                content_hash=content_hash,
            )

            item = {
                "keep_note_id": keep_note_id,
                "note_id": result["note_id"],
                "book_title": result.get("book_title"),
            }
            if prior:
                updated.append(item)
            else:
                imported.append(item)
        except Exception as exc:
            errors.append({"keep_note_id": keep_note_id, "error": str(exc)})

    return {
        "imported_count": len(imported),
        "updated_count": len(updated),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
    }


def entrypoint() -> None:
    print(json.dumps(sync_once(), indent=2))


if __name__ == "__main__":
    entrypoint()
