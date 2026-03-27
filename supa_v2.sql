-- Run this in your Supabase Dashboard -> SQL Editor

ALTER TABLE notes ADD COLUMN IF NOT EXISTS chapter text;
ALTER TABLE notes ADD COLUMN IF NOT EXISTS title text;
