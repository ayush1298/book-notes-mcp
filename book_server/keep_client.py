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

import os
from pathlib import Path
from typing import Any

import gkeepapi

import config
from storage.db import _client as db_client


# ── Auth ────────────────────────────────────────────────────────────────────

def _get_keep(email: str, app_password: str, token_file: Path) -> gkeepapi.Keep:
    """Return an authenticated gkeepapi.Keep instance, caching the token."""
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
    email = os.environ.get("GOOGLE_EMAIL", "")
    app_password = os.environ.get("GOOGLE_APP_PASSWORD", "")
    token_file = Path(os.environ.get("KEEP_TOKEN_FILE", ".keep_token"))

    if not email or not app_password:
        raise EnvironmentError(
            "Missing GOOGLE_EMAIL or GOOGLE_APP_PASSWORD in .env\n"
            "Generate an App Password at: myaccount.google.com/security → App Passwords"
        )

    return _get_keep(email, app_password, token_file)


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


def _already_synced(keep_note_ids: list[str]) -> set[str]:
    """Return the subset of keep_note_ids that are already in keep_synced."""
    if not keep_note_ids:
        return set()
    result = (
        db_client()
        .table("keep_synced")
        .select("keep_note_id")
        .in_("keep_note_id", keep_note_ids)
        .execute()
    )
    return {row["keep_note_id"] for row in (result.data or [])}


def fetch_unsynced_notes(label_name: str | None = None) -> list[dict[str, Any]]:
    """
    Return Keep notes with the given label that haven't been synced yet.

    Each item:
        { keep_id, title, text, created_at, updated_at }
    """
    label_name = label_name or os.environ.get("KEEP_LABEL", "book-note")
    keep = connect()

    # Find the label object
    label = keep.findLabel(label_name)
    if label is None:
        return []

    # Get all non-trashed notes with this label
    all_notes = list(keep.find(labels=[label], trashed=False, archived=False))

    if not all_notes:
        return []

    # Filter out already-synced ones
    all_ids = [str(note.id) for note in all_notes]
    synced_ids = _already_synced(all_ids)

    results = []
    for note in all_notes:
        nid = str(note.id)
        if nid in synced_ids:
            continue

        text = _extract_text(note)
        if not text:
            continue  # Skip empty notes

        results.append({
            "keep_id": nid,
            "title": note.title or "",
            "text": text,
            "created_at": note.timestamps.created.isoformat() if note.timestamps.created else None,
            "updated_at": note.timestamps.updated.isoformat() if note.timestamps.updated else None,
        })

    return results


# ── Mark synced ──────────────────────────────────────────────────────────────

def mark_synced(keep_note_id: str, note_id: str) -> None:
    """Record that a Keep note has been processed and stored."""
    db_client().table("keep_synced").insert(
        {"keep_note_id": keep_note_id, "note_id": note_id}
    ).execute()
