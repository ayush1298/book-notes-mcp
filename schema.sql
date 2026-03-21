-- ============================================================
-- Book Notes MCP — Supabase Schema
-- Run this in: Supabase Dashboard → SQL Editor → New Query
-- ============================================================

-- Enable pgvector extension (only needed once per project)
create extension if not exists vector;

-- ── Notes ────────────────────────────────────────────────────
create table if not exists notes (
  id          uuid primary key default gen_random_uuid(),
  source      text not null default 'manual',   -- 'manual', 'keep', etc.
  book_title  text,
  raw_text    text not null,
  summary     text,
  ideas       text[],
  tags        text[],
  actions     text[],
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

-- ── Embeddings ───────────────────────────────────────────────
-- IMPORTANT: Change vector(3072) to vector(1536) if using OpenAI embeddings, or vector(768) for Ollama.
-- The dimension must match the VECTOR_DIM value in your .env file.
create table if not exists note_embeddings (
  id          uuid primary key default gen_random_uuid(),
  note_id     uuid not null references notes(id) on delete cascade,
  embedding   vector(3072),  -- 3072 for Gemini (gemini-embedding-001), 1536 for OpenAI, 768 for Ollama
  created_at  timestamptz not null default now()
);

create index if not exists note_embeddings_note_id_idx
  on note_embeddings(note_id);

-- ── Similarity search function ───────────────────────────────
-- Called by the search layer for semantic retrieval.
create or replace function match_notes(
  query_embedding  vector,          -- must match embedding column dimension
  match_threshold  float default 0.5,
  match_count      int   default 5
)
returns table (
  note_id    uuid,
  book_title text,
  summary    text,
  tags       text[],
  ideas      text[],
  actions    text[],
  created_at timestamptz,
  similarity float
)
language sql stable
as $$
  select
    n.id          as note_id,
    n.book_title,
    n.summary,
    n.tags,
    n.ideas,
    n.actions,
    n.created_at,
    1 - (e.embedding <=> query_embedding) as similarity
  from note_embeddings e
  join notes n on n.id = e.note_id
  where 1 - (e.embedding <=> query_embedding) > match_threshold
  order by similarity desc
  limit match_count;
$$;

-- ── Auto-update updated_at ───────────────────────────────────
create or replace function update_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger notes_updated_at
  before update on notes
  for each row execute function update_updated_at();
