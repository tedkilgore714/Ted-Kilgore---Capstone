-- Create the candidates table used by shortlist_agent.py.
-- Run this once in the Supabase SQL editor (Dashboard -> SQL Editor -> New query).

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

-- Case-insensitive so "SailPoint" and "sailpoint" dedupe as the same company.
create unique index if not exists candidates_company_name_key on public.candidates (lower(company_name));

-- This table is written and read only by shortlist_agent.py via the
-- service_role key, which bypasses RLS. No anon/authenticated grants —
-- unlike target_companies.sql and seed-companies.sql, nothing here is
-- meant to be publicly readable.
alter table public.candidates enable row level security;

-- NOTE: service_role bypasses RLS but still needs Postgres table GRANTs,
-- and in this project service_role does NOT have the usual default grants
-- (verified: the secret key gets "42501 permission denied" on existing
-- tables). Without this line, shortlist_agent.py's inserts/updates 403
-- even though the table exists and RLS is bypassed.
grant all on public.candidates to service_role;
