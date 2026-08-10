-- Phase A of the Openings automation: let the backend add openings it found
-- on a company's ATS board, distinguishable from the ones a user typed in by
-- hand, and make rescans idempotent so re-running a scan never duplicates a
-- card. See openings.sql for the base table and openings_scout.py for the
-- writer. Run once in the Supabase SQL editor. Safe to re-run.

-- 'manual' = user added it via the My Openings form (the existing behavior,
-- and the default so every pre-existing row backfills correctly); 'scout' =
-- inserted by openings_scout.scan_openings_for_user().
alter table public.openings
  add column if not exists source text not null default 'manual';

-- When the scanner found each auto-added row (null for manual rows).
alter table public.openings
  add column if not exists found_at timestamptz;

-- Idempotent rescans: a given posting URL can exist at most once per user, so
-- scan_openings_for_user() can re-run freely and only ever add new postings.
-- Partial (url is not null) because manually-added rows are allowed to have
-- no URL, and a unique index would otherwise collapse all of those into one.
--
-- Pre-check for existing dupes before creating the index (should return zero
-- rows; if not, dedupe them first, as a unique index won't build over dupes):
--   select user_id, lower(url), count(*)
--   from public.openings
--   where url is not null
--   group by user_id, lower(url)
--   having count(*) > 1;
create unique index if not exists openings_user_url_key
  on public.openings (user_id, lower(url))
  where url is not null;
