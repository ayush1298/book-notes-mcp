"""Filesystem backup layer — saves/loads notes as Markdown with YAML frontmatter."""
from __future__ import annotations

import json
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import config


def _note_path(note_id: str) -> Path:
    return config.NOTES_DIR / f"{note_id}.md"


def save_note(note_id: str, data: dict) -> Path:
    """
    Write a note to disk as a Markdown file with YAML frontmatter.
    Returns the path written to.
    """
    path = _note_path(note_id)
    tags_str = ", ".join(data.get("tags") or [])
    ideas_md = "\n".join(f"- {i}" for i in (data.get("ideas") or []))
    actions_md = "\n".join(f"- [ ] {a}" for a in (data.get("actions") or []))
    created = data.get("created_at") or datetime.now(timezone.utc).isoformat()

    content = textwrap.dedent(f"""\
        ---
        id: {note_id}
        book_title: {data.get('book_title') or 'Unknown'}
        tags: [{tags_str}]
        source: {data.get('source', 'manual')}
        created_at: {created}
        ---

        # {data.get('book_title') or 'Note'}

        ## Summary
        {data.get('summary') or '_No summary yet._'}

        ## Key Ideas
        {ideas_md or '_None extracted._'}

        ## Actions
        {actions_md or '_None extracted._'}

        ## Raw Text
        {data.get('raw_text', '')}
        """)

    path.write_text(content, encoding="utf-8")
    return path


def load_note(note_id: str) -> str | None:
    """Return the raw markdown content of a saved note, or None if not found."""
    path = _note_path(note_id)
    return path.read_text(encoding="utf-8") if path.exists() else None


def list_note_files() -> list[Path]:
    return sorted(config.NOTES_DIR.glob("*.md"))
