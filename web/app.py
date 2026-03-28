"""
Book Notes Web API — FastAPI server wrapping the core pipeline.

Endpoints:
  POST /api/process        — process a raw note
  POST /api/ask            — RAG question answering
  POST /api/search         — semantic search
  GET  /api/notes          — list notes (optional ?tag= & ?limit=)
  GET  /api/notes/{id}     — get a single note by ID
  POST /api/webhook/keep   — IFTTT auto-sync from Google Keep
  GET  /                   — serves the web dashboard SPA

Run locally:
  python web/app.py
  Open http://localhost:8080

Phone on same WiFi:
  Open http://<your-mac-ip>:8080

Heroku:
  Procfile: web: uvicorn web.app:app --host 0.0.0.0 --port $PORT
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on path so pipeline modules resolve
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, Form, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config  # noqa — ensures NOTES_DIR created on startup
from book_server.ingestion import ingest_note

app = FastAPI(title="Book Notes", docs_url="/api/docs")

# Allow browser requests from any origin (important for development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (frontend)
_static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


# ── Request / Response models ───────────────────────────────────────────────

class ProcessRequest(BaseModel):
    raw_text: str
    source: str = "manual"
    book_title: str | None = None
    chapter: str | None = None
    title: str | None = None

class AskRequest(BaseModel):
    question: str

class SearchRequest(BaseModel):
    query: str
    limit: int = 5
    threshold: float = 0.4

class KeepWebhookRequest(BaseModel):
    title: str = ""
    content: str = ""


# ── Routes ─────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return FileResponse(str(_static_dir / "index.html"))


@app.post("/api/process")
def process_note(req: ProcessRequest):
    """Run a raw note through the full pipeline: summarise → store → embed."""
    try:
        return ingest_note(
            raw_text=req.raw_text,
            source=req.source,
            book_title=req.book_title,
            chapter=req.chapter,
            title=req.title,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/process_media")
@app.post("/api/extract_raw")
async def extract_raw(files: List[UploadFile] = File(...)):
    """Extract raw text from a list of media files, returning it as a string without saving to DB."""
    try:
        from processing.media import extract_text_from_media
        result = []
        for file in files:
            media_bytes = await file.read()
            extracted_text = extract_text_from_media(media_bytes, file.content_type)
            result.append(extracted_text)
        return {"extracted_text": "\n\n".join(result)}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
@app.post("/api/ask")
def ask(req: AskRequest):
    """RAG: embed question → retrieve similar notes → synthesise answer."""
    from agent.query_agent import answer_query
    try:
        return answer_query(req.question)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/search")
def search(req: SearchRequest):
    """Semantic search across all notes."""
    from embeddings.embed import get_embedding
    from storage.db import search_similar
    try:
        embedding = get_embedding(req.query)
        results = search_similar(embedding, threshold=req.threshold, limit=req.limit)
        return {"query": req.query, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/notes")
def list_notes(tag: str | None = None, limit: int = 20):
    """List notes, optionally filtered by tag."""
    from storage.db import list_notes as _list
    try:
        return {"notes": _list(limit=limit, tag=tag or None)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/notes/{note_id}")
def get_note(note_id: str):
    """Get a single note by ID."""
    from storage.db import get_note as _get
    try:
        note = _get(note_id)
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        return note
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class EditRequest(BaseModel):
    book_title: str | None = None
    chapter: str | None = None
    title: str | None = None
    summary: str | None = None
    ideas: list[str] | None = None
    tags: list[str] | None = None
    actions: list[str] | None = None

@app.put("/api/notes/{note_id}")
def edit_note(note_id: str, req: EditRequest):
    """Update textual fields of a note."""
    from storage.db import update_note, get_note as _get
    try:
        note = _get(note_id)
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
            
        update_note(
            note_id,
            book_title=req.book_title,
            chapter=req.chapter,
            title=req.title,
            summary=req.summary,
            ideas=req.ideas,
            tags=req.tags,
            actions=req.actions
        )
        return {"status": "success", "note_id": note_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/notes/{note_id}")
def delete_note(note_id: str):
    """Delete a note."""
    from storage.db import delete_note as _del
    try:
        _del(note_id)
        return {"status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/folders")
def list_folders():
    """Retrieve unique book_title and chapter combinations."""
    from storage.db import list_folders as _lf
    try:
        return {"folders": _lf()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/notes/by_path")
def resolve_note_path(book: str, chapter: str, title: str):
    """Find a note's ID given its structured semantic path."""
    from storage.db import get_note_by_path
    try:
        note = get_note_by_path(book, chapter, title)
        if not note:
            # Check without implicit nulls just in case they used actual text "General"
            from storage.db import _client
            res = _client().table("notes").select("id").eq("book_title", book).eq("chapter", chapter).eq("title", title).limit(1).execute()
            if res.data:
                return res.data[0]
            raise HTTPException(status_code=404, detail="Note not found")
        return note
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/notes/{note_id}/link")
def link_notes(note_id: str, limit: int = 5):
    """Find notes conceptually related to a given note."""
    from storage.db import link_notes as _link
    try:
        return {"links": _link(note_id, limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/{book}/{chapter}/{title}")
def serve_shared_route(book: str, chapter: str, title: str):
    """Catch-all for semantic URLs like /Atomic Habits/Chapter 1/My Insight"""
    return FileResponse(str(_static_dir / "index.html"))


@app.post("/api/webhook/keep")
def keep_webhook(req: KeepWebhookRequest, background_tasks: BackgroundTasks):
    """
    IFTTT webhook: called automatically when a Keep note is labelled 'book-note'.
    Processes the note in the background so IFTTT gets an immediate 200 response.
    """
    text = f"{req.title}\n{req.content}".strip() if req.title else req.content.strip()
    if not text:
        return {"status": "skipped", "reason": "empty note"}

    def _process_in_background(raw_text: str):
        ingest_note(raw_text=raw_text, source="keep")

    background_tasks.add_task(_process_in_background, text)
    return {"status": "queued"}


# ── Dev server entry point ──────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    import socket

    # Print local IP for easy phone access
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    print(f"\n🚀 Book Notes running at:")
    print(f"   Local:   http://localhost:8080")
    print(f"   Network: http://{local_ip}:8080  ← open this on your phone\n")

    uvicorn.run("web.app:app", host="0.0.0.0", port=8080, reload=True)
