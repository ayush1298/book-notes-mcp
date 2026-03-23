"""
Google Keep client — fetches unprocessed notes from Keep using gkeepapi.

Authentication:
  Uses a Google App Password (NOT your main Google password).
  Generate one at: myaccount.google.com/security → App Passwords
  Add to .env: GOOGLE_EMAIL and GOOGLE_APP_PASSWORD

Workflow:
  1. Notes on phone are labelled 'book-note' (configurable via KEEP_LABEL)
  2. call fetch_unsynced_notes() → returns text content of all unseen notes
  3. After processing, call mark_synced() to record in Supabase

Note types handled:
  - Text notes       → note.text
  - Photo notes      → Keep auto-OCRs images, we read that text
  - Voice notes      → Keep saves a transcript blob text
  - Checklist notes  → items joined as text
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import gkeepapi
    _HAS_GKEEPAPI = True
except ImportError:  # pragma: no cover - exercised only in minimal test envs
    gkeepapi = Any  # type: ignore[assignment]
    _HAS_GKEEPAPI = False

import config


# ── Auth ────────────────────────────────────────────────────────────────────

def _get_keep(email: str, app_password: str, token_file: Path) -> gkeepapi.Keep:
    """Return an authenticated gkeepapi.Keep instance, caching the token."""
    if not _HAS_GKEEPAPI:
        raise ModuleNotFoundError(
            "gkeepapi is not installed. Install project dependencies before using Keep sync."
        )
    import uuid
    import gpsoauth

    # App passwords are displayed with spaces (xxxx xxxx xxxx xxxx) — strip them
    app_password = app_password.replace(" ", "")

    keep = gkeepapi.Keep()

    if token_file.exists():
        # Resume session from cached master token
        master_token = token_file.read_text().strip()
        try:
            keep.authenticate(email, master_token)
            return keep
        except Exception:
            # Token expired — fall through to fresh login
            token_file.unlink(missing_ok=True)

    # Fresh login: use gpsoauth to exchange app password for a master token
    device_id = uuid.uuid4().hex
    res = gpsoauth.perform_master_login(email, app_password, device_id)
    master_token = res.get("Token")
    if not master_token:
        error = res.get("Error", "unknown error")
        raise RuntimeError(
            f"Google auth failed: {error}\n"
            "Check that GOOGLE_EMAIL and GOOGLE_APP_PASSWORD are correct.\n"
            "App password should be the 16-char code from myaccount.google.com → App Passwords."
        )

    keep.authenticate(email, master_token)
    # Cache master token for next call (avoids re-login each time)
    token_file.write_text(master_token)
    return keep


def connect() -> gkeepapi.Keep:
    if not config.GOOGLE_EMAIL or not config.GOOGLE_APP_PASSWORD:
        raise EnvironmentError(
            "Missing GOOGLE_EMAIL or GOOGLE_APP_PASSWORD in .env\n"
            "Generate an App Password at: myaccount.google.com/security → App Passwords"
        )

    return _get_keep(config.GOOGLE_EMAIL, config.GOOGLE_APP_PASSWORD, config.KEEP_TOKEN_FILE)


# ── Fetch ────────────────────────────────────────────────────────────────────

def _extract_text(note: gkeepapi.node.TopLevelNode) -> str:
    """Extract all readable text from any Keep note type."""
    parts: list[str] = []

    if note.title:
        parts.append(note.title)

    # Plain text or checklist
    text = note.text
    if text:
        parts.append(text)

    # Blobs (images with OCR text, voice transcripts)
    if hasattr(note, "blobs"):
        for blob in note.blobs:
            if hasattr(blob, "text") and blob.text:
                parts.append(f"[OCR/Transcript]: {blob.text}")

    return "\n".join(parts).strip()


def _timestamps(note: gkeepapi.node.TopLevelNode) -> tuple[str | None, str | None]:
    created = note.timestamps.created.isoformat() if note.timestamps.created else None
    updated = note.timestamps.updated.isoformat() if note.timestamps.updated else None
    return created, updated


def list_notes(label_name: str | None = None) -> list[dict[str, Any]]:
    """
    Return all non-trashed, non-archived Keep notes for the configured label.

    Each item:
        { keep_id, title, text, created_at, updated_at }
    """
    label_name = label_name or config.KEEP_LABEL
    keep = connect()

    # Find the label object
    label = keep.findLabel(label_name)
    if label is None:
        return []

    # Get all non-trashed notes with this label
    all_notes = list(keep.find(labels=[label], trashed=False, archived=False))

    if not all_notes:
        return []

    results = []
    for note in all_notes:
        nid = str(note.id)

        text = _extract_text(note)
        if not text:
            continue  # Skip empty notes

        created_at, updated_at = _timestamps(note)
        results.append({
            "keep_id": nid,
            "title": note.title or "",
            "text": text,
            "created_at": created_at,
            "updated_at": updated_at,
        })

    return results


def fetch_unsynced_notes(label_name: str | None = None) -> list[dict[str, Any]]:
    """Backward-compatible helper used by older callers."""
    from storage import db

    notes = list_notes(label_name)
    existing = db.list_keep_syncs([note["keep_id"] for note in notes])
    return [note for note in notes if note["keep_id"] not in existing]
