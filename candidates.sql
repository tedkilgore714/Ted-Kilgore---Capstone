-- Create the candidates table used by shortlist_agent.py.
-- Run this once in the Supabase SQL editor (Dashboard -> SQL Editor -> New query).
-- Safe to re-run.

-- Sourced from company_recommender.py (fit-matched, best-effort research,
-- no live job-posting verification — job_title/hiring_signal stay null).
create table if not exists public.candidates (
  id uuid primary key default gen_random_uuid(),
  company_name text not null,
  job_title text,
  size_estimate text,
  location_match text,
  growth_note text,
  hiring_signal text,
  fit_rationale text,
  rank int,
  created_at timestamptz not null default now()
);

-- Scope candidates to the search that found them (role/location/size/remote),
-- so re-running the agent with different inputs doesn't wrongly dedupe
-- against — or mix results with — an unrelated earlier search.
alter table public.candidates add column if not exists role text;
alter table public.candidates add column if not exists location text;
alter table public.candidates add column if not exists company_size text;
alter table public.candidates add column if not exists include_remote boolean;

-- Backfill rows inserted before these columns existed, using the sample
-- search shortlist_agent.py's __main__ ran with. Only touches rows that
-- predate this migration (role is null).
update public.candidates
set role = 'Director of Professional Services',
    location = 'Austin, TX',
    company_size = 'Mid-size (201-1,000 employees)',
    include_remote = true
where role is null;

-- Dedupe is now per-search, not global — the same company can legitimately
-- appear in two different searches (different role/location/etc).
drop index if exists candidates_company_name_key;
create unique index if not exists candidates_search_company_key
  on public.candidates (role, location, company_size, include_remote, lower(company_name));

-- This table is written and read only by shortlist_agent.py and main.py's
-- /candidates endpoint, both via the service_role key, which bypasses RLS.
-- No anon/authenticated grants — unlike target_companies.sql and
-- seed-companies.sql, nothing here is meant to be publicly readable
-- directly from Supabase (main.py's server-side code reads it instead).
alter table public.candidates enable row level security;

-- service_role bypasses RLS but still needs Postgres table GRANTs, and in
-- this project service_role does NOT have the usual default grants
-- (verified: the secret key gets "42501 permission denied" on existing
-- tables without this). Without this line, inserts/updates/selects 403
-- even though the table exists and RLS is bypassed.
grant all on public.candidates to service_role;
