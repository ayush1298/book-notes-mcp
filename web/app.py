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
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/process_media")
async def process_media(
    file: UploadFile = File(...),
    text: str = Form(""),
    source: str = Form("manual")
):
    """Fallback endpoint for handling direct multimodal uploads (images/audio) from the PWA."""
    try:
        from processing.media import extract_text_from_media
        
        media_bytes = await file.read()
        extracted_text = extract_text_from_media(media_bytes, file.content_type)
        
        # Combine any typed notes with the extracted media text
        final_text = text.strip()
        if final_text:
            final_text += f"\n\n--- Extracted from {file.filename} ---\n\n{extracted_text}"
        else:
            final_text = extracted_text
            
        return ingest_note(
            raw_text=final_text,
            source=source,
        )
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

@app.get("/api/notes/{note_id}/link")
def link_notes(note_id: str, limit: int = 5):
    """Find notes conceptually related to a given note."""
    from storage.db import link_notes as _link
    try:
        return {"related": _link(note_id, limit=limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
