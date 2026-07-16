-- Adds updated_at to candidates so the site can tell "this scope was just
-- re-ranked/re-run" apart from "this scope was created a while ago" -- a
-- re-run that finds 0 new companies (already at target) still touches
-- updated_at via _persist_ranks(), even though created_at stays put.
-- Run once in the Supabase SQL editor. Safe to re-run.

alter table public.candidates add column if not exists updated_at timestamptz;
update public.candidates set updated_at = created_at where updated_at is null;
alter table public.candidates alter column updated_at set default now();
