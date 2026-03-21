"""
Embedding layer using LiteLLM.

Supports any embedding provider via EMBEDDING_MODEL in .env:
  gemini/text-embedding-004  (768-dim, free)
  openai/text-embedding-3-small  (1536-dim)
  ollama/nomic-embed-text  (768-dim, local)
"""
from __future__ import annotations

import litellm
from tenacity import retry, stop_after_attempt, wait_exponential

import config


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def get_embedding(text: str) -> list[float]:
    """Return the embedding vector for the given text."""
    response = litellm.embedding(
        model=config.EMBEDDING_MODEL,
        input=[text],
    )
    return response.data[0]["embedding"]


def embed_and_store(note_id: str, text: str) -> list[float]:
    """
    Generate an embedding for text and persist it to Supabase.
    Returns the embedding vector (useful for immediate similarity search).
    """
    from storage.db import store_embedding  # lazy import to avoid circular deps

    embedding = get_embedding(text)
    store_embedding(note_id, embedding)
    return embedding
