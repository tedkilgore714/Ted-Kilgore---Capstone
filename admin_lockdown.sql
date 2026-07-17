-- Locks down /admin.html's data to real logged-in users only. Previously
-- both leads (contact submissions) and site_checklist were readable by
-- anyone with the public anon key -- the page had no login, and even a
-- client-side password prompt wouldn't have helped since anyone could
-- just query the Supabase REST API directly with the anon key, bypassing
-- the page entirely. Real fix has to happen at the RLS/grant level.
--
-- leads INSERT stays public -- the Contact form must keep working for
-- anonymous visitors submitting a message. Only SELECT (reading existing
-- submissions) now requires authentication.
--
-- Run once in the Supabase SQL editor. Safe to re-run.

drop policy if exists "Allow public read leads" on public.leads;
create policy "authenticated read leads" on public.leads
  for select to authenticated using (true);
revoke select on public.leads from anon;
grant select on public.leads to authenticated;

drop policy if exists "public read" on public.site_checklist;
drop policy if exists "public write" on public.site_checklist;
create policy "authenticated all site_checklist" on public.site_checklist
  for all to authenticated using (true) with check (true);
revoke select, insert, update, delete on public.site_checklist from anon;
grant select, insert, update, delete on public.site_checklist to authenticated;
