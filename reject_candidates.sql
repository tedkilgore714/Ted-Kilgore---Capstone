-- Adds rejection tracking and per-row resume storage to public.candidates,
-- needed so a client can reject a company from their shortlist (free tier:
-- capped at 5 rejections per search scope) and the backend can run a
-- same-scope 1-company replacement search without the client re-pasting
-- their resume.
--
-- resume is denormalized onto every row (same value repeated across a
-- scope's ~10 rows) rather than pulled into a separate table -- this
-- matches how role/location/company_size/include_remote are already
-- stored per-row rather than normalized out.
--
-- Run once in the Supabase SQL editor. Safe to re-run.

alter table public.candidates
  add column if not exists rejected boolean not null default false,
  add column if not exists rejected_at timestamptz,
  add column if not exists resume text;
