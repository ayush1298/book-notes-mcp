"""
Google Takeout Keep import — parses the JSON export format from Google Takeout.

Usage:
  1. Go to takeout.google.com
  2. Deselect all → select only "Keep"
  3. Download the zip
  4. Extract it → you'll have a folder like "Takeout/Keep/"
  5. In Antigravity: "Import my Keep takeout from /path/to/Takeout/Keep"

Why Takeout instead of gkeepapi:
  Google has heavily restricted the Android auth API that gkeepapi uses.
  Takeout is the official, always-reliable export path.
  It includes OCR text from photos and voice note transcripts.

Takeout JSON format (one file per note):
  {
    "title": "...",
    "textContent": "...",      ← text notes
    "listContent": [...],      ← checklist notes
    "annotations": [...],      ← web clips
    "attachments": [           ← images/audio with transcripts
      { "filePath": "...", "mimetype": "..." }
    ],
    "labels": [{"name": "book-note"}],
    "isTrashed": false,
    "isArchived": false,
    "createdTimestampUsec": 1234567890000000,
    "userEditedTimestampUsec": 1234567890000000
  }
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _extract_text_from_note_json(note: dict) -> str:
    """Extract all readable text from a Takeout Keep note JSON object."""
    parts: list[str] = []

    if note.get("title"):
        parts.append(note["title"])

    # Plain text note
    if note.get("textContent"):
        parts.append(note["textContent"])

    # Checklist note
    for item in note.get("listContent", []):
        checked = "✓" if item.get("isChecked") else "•"
        parts.append(f"{checked} {item.get('text', '')}")

    # Attachments (images have OCR text in a .txt sidecar with the same base name)
    for att in note.get("annotations", []):
        if att.get("description"):
            parts.append(f"[annotation]: {att['description']}")
        if att.get("title"):
            parts.append(f"[link]: {att['title']}")

    return "\n".join(p for p in parts if p.strip()).strip()


def _load_ocr_sidecar(json_path: Path, attachment: dict) -> str | None:
    """Try to load OCR sidecar text file that Keep exports alongside image attachments."""
    file_path = attachment.get("filePath", "")
    if not file_path:
        return None
    # Keep Takeout puts image OCR in a .txt file with same name as image
    base = Path(file_path).stem
    for ext in [".txt"]:
        sidecar = json_path.parent / (base + ext)
        if sidecar.exists():
            return sidecar.read_text(encoding="utf-8").strip()
    return None


def load_notes_from_takeout(
    takeout_keep_dir: str | Path,
    label_filter: str | None = "book-note",
    skip_trashed: bool = True,
    skip_archived: bool = False,
) -> list[dict[str, Any]]:
    """
    Parse all Keep JSON files from a Google Takeout Keep directory.

    Args:
        takeout_keep_dir: Path to the "Takeout/Keep" folder
        label_filter: Only return notes with this label (None = all notes)
        skip_trashed: Skip trashed notes (default True)
        skip_archived: Skip archived notes (default False)

    Returns:
        List of dicts: { title, text, labels, created_at, source_file }
    """
    keep_dir = Path(takeout_keep_dir)
    if not keep_dir.exists():
        raise FileNotFoundError(f"Takeout Keep directory not found: {keep_dir}")

    json_files = list(keep_dir.glob("*.json"))
    if not json_files:
        raise FileNotFoundError(
            f"No JSON files found in {keep_dir}. "
            "Make sure you're pointing at the 'Takeout/Keep' folder, not the zip file."
        )

    results = []
    for json_path in sorted(json_files):
        try:
            note = json.loads(json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        if skip_trashed and note.get("isTrashed"):
            continue
        if skip_archived and note.get("isArchived"):
            continue

        # Label filter
        labels = [lb.get("name", "") for lb in note.get("labels", [])]
        if label_filter and label_filter not in labels:
            continue

        text = _extract_text_from_note_json(note)

        # Try to append OCR text from image attachments
        for att in note.get("attachments", []):
            ocr = _load_ocr_sidecar(json_path, att)
            if ocr:
                text += f"\n[image text]: {ocr}"

        if not text.strip():
            continue

        created_us = note.get("createdTimestampUsec", 0)
        created_at = None
        if created_us:
            from datetime import datetime, timezone
            created_at = datetime.fromtimestamp(
                created_us / 1_000_000, tz=timezone.utc
            ).isoformat()

        results.append({
            "title": note.get("title", ""),
            "text": text.strip(),
            "labels": labels,
            "source_file": json_path.name,
            "created_at": created_at,
        })

    return results
