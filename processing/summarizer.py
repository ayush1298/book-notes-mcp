"""
LLM-powered summarizer using LiteLLM.

Supports any provider via LLM_MODEL in .env:
  gemini/gemini-2.5-flash, openai/gpt-4o-mini, anthropic/claude-3-haiku-..., ollama/llama3
"""
from __future__ import annotations

import json
import re

import litellm
from tenacity import retry, stop_after_attempt, wait_exponential

import config

# ── Prompt ─────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a knowledge extraction assistant for personal book notes.
You receive raw text captured from a physical book (via photo OCR or voice transcription).
Your job is to extract structured knowledge from it.
Always reply with ONLY valid JSON — no markdown fences, no prose."""

USER_PROMPT_TEMPLATE = """\
Extract knowledge from this book note:

---
{text}
---

Return a JSON object with exactly these keys:
{{
  "book_title": "<inferred title or null if unclear>",
  "summary": "<3-5 bullet points joined by newlines, each starting with •>",
  "ideas": ["<key idea 1>", "<key idea 2>", ...],
  "tags": ["<tag1>", "<tag2>", ...],
  "actions": ["<actionable insight 1>", ...]
}}

Rules:
- summary: 3-5 concise bullets
- ideas: the most important conceptual insights (3-8 items)
- tags: 3-7 lowercase single-word or hyphenated tags (e.g. "decision-making", "habits")
- actions: concrete things the reader could do or apply (0-5 items)
- Return ONLY the JSON object, nothing else."""


# ── Core function ──────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def process_note(raw_text: str) -> dict:
    """
    Run the full LLM extraction on raw note text.

    Returns a dict with keys: book_title, summary, ideas, tags, actions.
    Raises ValueError if the LLM returns malformed JSON after retries.
    """
    response = litellm.completion(
        model=config.LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT_TEMPLATE.format(text=raw_text)},
        ],
        temperature=0.2,
    )

    raw_output = response.choices[0].message.content.strip()

    # Strip markdown fences if the model returns them anyway
    raw_output = re.sub(r"^```(?:json)?\s*", "", raw_output)
    raw_output = re.sub(r"\s*```$", "", raw_output)

    try:
        result = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"LLM returned non-JSON output:\n{raw_output}"
        ) from exc

    # Ensure all expected keys exist with sane defaults
    return {
        "book_title": result.get("book_title"),
        "summary": result.get("summary", ""),
        "ideas": result.get("ideas") or [],
        "tags": [t.lower().strip() for t in (result.get("tags") or [])],
        "actions": result.get("actions") or [],
    }
