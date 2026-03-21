"""
RAG-based query/recall agent.

Usage:
    answer = answer_query("What have I read about habits?")
"""
from __future__ import annotations

import litellm

import config
from embeddings.embed import get_embedding
from storage.db import search_similar

SYSTEM_PROMPT = """\
You are a personal knowledge assistant. The user has been reading physical books and capturing notes.
You are given relevant excerpts from their personal note database.
Answer their question using ONLY the provided notes. Be specific and cite ideas from the notes.
If the notes don't contain enough information to answer, say so honestly."""


def answer_query(
    question: str,
    threshold: float = 0.4,
    top_k: int = 5,
) -> dict:
    """
    Full RAG pipeline:
    1. Embed the question
    2. Find top-k similar notes in Supabase
    3. Build context from retrieved notes
    4. Ask the LLM to synthesize an answer

    Returns:
        {
          "answer": str,
          "sources": [{"note_id": ..., "book_title": ..., "similarity": ...}, ...]
        }
    """
    # Step 1: embed question
    query_embedding = get_embedding(question)

    # Step 2: retrieve similar notes
    similar_notes = search_similar(query_embedding, threshold=threshold, limit=top_k)

    if not similar_notes:
        return {
            "answer": "I couldn't find any relevant notes on this topic yet. Try adding more notes!",
            "sources": [],
        }

    # Step 3: build context block
    context_parts = []
    for i, note in enumerate(similar_notes, 1):
        book = note.get("book_title") or "Unknown book"
        summary = note.get("summary") or ""
        ideas = "\n".join(f"  - {idea}" for idea in (note.get("ideas") or []))
        actions = "\n".join(f"  - {a}" for a in (note.get("actions") or []))
        sim = note.get("similarity", 0)
        context_parts.append(
            f"[Note {i} | {book} | similarity: {sim:.2f}]\n"
            f"Summary:\n{summary}\n"
            f"Key Ideas:\n{ideas}\n"
            f"Actions:\n{actions}"
        )

    context = "\n\n---\n\n".join(context_parts)

    # Step 4: synthesize with LLM
    response = litellm.completion(
        model=config.LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"My notes:\n\n{context}\n\n"
                    f"My question: {question}"
                ),
            },
        ],
        temperature=0.3,
    )

    answer = response.choices[0].message.content.strip()

    sources = [
        {
            "note_id": n.get("note_id"),
            "book_title": n.get("book_title"),
            "similarity": round(n.get("similarity", 0), 3),
        }
        for n in similar_notes
    ]

    return {"answer": answer, "sources": sources}
