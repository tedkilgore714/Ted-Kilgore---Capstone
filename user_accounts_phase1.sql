-- Phase 1 of the real-per-user-accounts rollout (see
-- .claude/plans -- "Real per-user accounts (Supabase Auth) for AI Job
-- Scout"). Purely additive -- nothing reads or writes user_id yet, so this
-- is safe to run against the live site with zero behavior change.
--
-- Run once in the Supabase SQL editor. Safe to re-run.

alter table public.candidates add column if not exists user_id uuid references auth.users(id) on delete cascade;
alter table public.openings   add column if not exists user_id uuid references auth.users(id) on delete cascade;

create index if not exists candidates_user_id_idx on public.candidates(user_id);
create index if not exists openings_user_id_idx   on public.openings(user_id);

-- openings is written directly from the browser using the signed-in
-- user's own client, so a column default lets Postgres stamp user_id from
-- the request's JWT automatically -- board.js's insert payload needs no
-- changes for this. candidates is only ever written from main.py via the
-- service_role key, which carries no user JWT context (auth.uid() would
-- just be null there), so main.py sets user_id explicitly on every insert
-- instead -- no default added on candidates for that reason.
alter table public.openings alter column user_id set default auth.uid();
