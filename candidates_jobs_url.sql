-- Adds jobs_url to candidates: the company's actual jobs/careers listing
-- page, researched by CompanyRecommender (best-effort, not live-verified --
-- that's still company_matcher.py's job). Lays groundwork for a future
-- cron job that visits these pages to check for new postings.
-- Run once in the Supabase SQL editor. Safe to re-run.

alter table public.candidates add column if not exists jobs_url text;
