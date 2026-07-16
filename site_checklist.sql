-- Tracked checklist of site features/integrations, shown on the Checklist
-- tab of admin.html. Run this once in the Supabase SQL editor.
-- Safe to re-run: the seed insert below is skipped for items already present
-- (matched by item text).

create table if not exists public.site_checklist (
  id uuid primary key default gen_random_uuid(),
  category text not null,
  item text not null,
  status text not null default 'todo', -- todo | in_progress | done | blocked
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists site_checklist_item_key on public.site_checklist (item);

-- Public site (anon key, no auth) reads and writes this like it does the
-- openings table -- personal capstone project, no multi-tenant boundary.
alter table public.site_checklist enable row level security;
grant select, insert, update, delete on public.site_checklist to anon;
grant select, insert, update, delete on public.site_checklist to authenticated;

drop policy if exists "public read" on public.site_checklist;
create policy "public read" on public.site_checklist for select using (true);

drop policy if exists "public write" on public.site_checklist;
create policy "public write" on public.site_checklist for all using (true) with check (true);

insert into public.site_checklist (category, item, status, notes) values
  ('My Companies', 'Reads real Agent output (candidates table) instead of fake seed data', 'done', 'companies.js now fetches from Render /candidates instead of the static companies table.'),
  ('My Companies', 'Trigger form starts the Shortlist Agent from the real site', 'done', 'POSTs to Render /shortlist directly from companies.html.'),
  ('My Companies', 'Careers-page link on each card', 'blocked', 'CompanyRecommender does not collect a verified posting URL. Currently omitted; toggle CAREERS_LINK_MODE in companies.js to switch to a Google-search fallback.'),
  ('My Openings', 'Kanban board (add/edit/delete/drag, realtime sync)', 'done', 'Fully functional, but 100% manual entry -- nothing auto-populates it yet.'),
  ('My Openings', 'Auto-populate from Matcher-verified postings', 'todo', 'Future enhancement, not urgent -- manual tracking works fine today.'),
  ('Contact', 'Contact form saves to leads table', 'done', 'Verified working.'),
  ('Admin', 'Leads table view', 'done', 'Verified working.'),
  ('Admin', 'Access control on /admin.html', 'blocked', 'No login -- anyone with the URL can view all leads. Not linked from nav, but the URL itself is not secret.'),
  ('AI Matcher', 'POST /matcher and /demo live on Render', 'in_progress', 'Reachable (200 OK) but not functionally re-tested live on Render since the last code change -- deprioritized due to cost.'),
  ('AI Recommender', 'POST /recommend and /recommend-demo live on Render', 'in_progress', 'Reachable (200 OK) but not functionally re-tested live on Render since the last code change.'),
  ('Shortlist Agent', 'Runs end-to-end locally and writes to Supabase', 'done', 'Verified full flow: trigger, search loop, ranking, save, email.'),
  ('Shortlist Agent', 'Digest email actually sends (not just drafts)', 'done', 'Switched from GMAIL_CREATE_EMAIL_DRAFT to GMAIL_SEND_EMAIL, recipient changed to tedkilgore714@gmail.com. Verified delivered.'),
  ('Shortlist Agent', 'Background job survives a real multi-minute run on Render (not just local)', 'todo', 'Not yet proven with fresh (non-duplicate) inputs against the live Render deploy.'),
  ('Data', 'Orphaned companies / target_companies tables', 'todo', 'Static seed data, no write path, no longer read by any page after the My Companies fix. Decide: drop or repurpose.')
on conflict (item) do nothing;
