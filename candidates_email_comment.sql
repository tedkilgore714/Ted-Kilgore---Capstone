-- Phase 6 cleanup of the real-per-user-accounts rollout. candidates.email
-- predates user_id (see candidates_email_scope.sql) and was the scope key
-- before real auth existed. Since Phase 5 (user_accounts_phase5.sql-
-- equivalent enforcement, applied via the Supabase dashboard), access
-- control and row ownership are entirely user_id/RLS -- email is never
-- checked or trusted for authorization anywhere in main.py or
-- shortlist_agent.py anymore. This comment documents that in the schema
-- itself so it isn't mistaken for an authorization boundary later.
--
-- Run once in the Supabase SQL editor. Safe to re-run.

comment on column public.candidates.email is
  'Cosmetic/audit-only as of the real-per-user-accounts rollout (2026-07) -- '
  'never authoritative for access control. Row ownership and all scoping is '
  'user_id + RLS; see user_accounts_phase1.sql and the Phase 5 enforcement '
  'migration.';
