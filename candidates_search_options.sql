-- Customizable search criteria (see .claude/plans -- "Customizable search
-- criteria (radius, growth, leadership stability)"). Lets each user tune
-- three previously-fixed judgment calls per search: local radius, growth
-- emphasis, and leadership-stability emphasis.
--
-- Defaults (25 / true / true) exactly match the old hardcoded behavior in
-- company_recommender.py, so existing rows backfill correctly via the
-- column default alone -- no manual `update` needed.
--
-- radius_miles is a NOT NULL integer with a sentinel (0 = "no distance
-- constraint"), not a nullable column -- a unique index can't reliably
-- dedupe on NULL (NULL != NULL), and these three columns join the existing
-- scope-key index below. Mirrors the ANY_COMPANY_SIZE string-sentinel
-- pattern already used for company_size in company_recommender.py.
--
-- Run once in the Supabase SQL editor. Safe to re-run.

alter table public.candidates add column if not exists radius_miles integer not null default 25;
alter table public.candidates add column if not exists prioritize_growth boolean not null default true;
alter table public.candidates add column if not exists prioritize_stability boolean not null default true;

-- Rebuild the scope-key unique index to include the three new columns --
-- otherwise two searches that differ only in radius/growth/stability but
-- share role/location/company_size/include_remote would incorrectly
-- collide. Safe: the new index is a superset of the already-unique legacy
-- key plus three columns that are uniformly defaulted across every
-- existing row, so no new duplicates are introduced by widening it.
drop index if exists candidates_search_company_key;
create unique index if not exists candidates_search_company_key
  on public.candidates (user_id, role, location, company_size, include_remote,
                         radius_miles, prioritize_growth, prioritize_stability,
                         lower(company_name));
