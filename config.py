"""
Centralised config — reads from .env and exposes typed settings.
Every module imports from here instead of reading os.environ directly.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(
            f"Missing required environment variable: {key}\n"
            f"Copy .env.example to .env and fill in the values."
        )
    return val


# ── LLM / Embedding ────────────────────────────────────────────────────────
LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini/gemini-2.5-flash")
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "gemini/gemini-embedding-001")
VECTOR_DIM: int = int(os.getenv("VECTOR_DIM", "768"))

# ── Supabase ───────────────────────────────────────────────────────────────
SUPABASE_URL: str = _require("SUPABASE_URL")
SUPABASE_SERVICE_KEY: str = _require("SUPABASE_SERVICE_KEY")

# ── Filesystem ─────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).parent
_notes_raw = os.getenv("NOTES_DIR", "./notes")
NOTES_DIR: Path = (
    Path(_notes_raw)
    if Path(_notes_raw).is_absolute()
    else (_PROJECT_ROOT / _notes_raw)
).resolve()
NOTES_DIR.mkdir(parents=True, exist_ok=True)
