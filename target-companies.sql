-- Create and seed the target_companies table (curated target-company list).
-- Run this once in the Supabase SQL editor (Dashboard -> SQL Editor -> New query).
-- Safe to re-run: existing rows with the same name are skipped.

create table if not exists public.target_companies (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  careers_page_url text,
  notes text,
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create unique index if not exists target_companies_name_key on public.target_companies (name);

alter table public.target_companies enable row level security;
grant select on public.target_companies to anon;
grant select on public.target_companies to authenticated;
drop policy if exists "public read" on public.target_companies;
create policy "public read" on public.target_companies for select using (true);

insert into public.target_companies (name, careers_page_url, notes, active) values
  ('ActiveProspect', 'https://activeprospect.com/careers/', 'Consent-based marketing SaaS with a growing customer org; Austin HQ.', true),
  ('AffiniPay', 'https://affinipay.com/careers/', 'Payments platform for professional associations; strong PS/CS leadership presence in Austin.', true),
  ('AlertMedia', 'https://www.alertmedia.com/careers/', 'Emergency communication SaaS with a customer-heavy org; Austin HQ.', true),
  ('Billd', 'https://billd.com/careers/', 'Construction fintech scaling customer operations from Austin.', true),
  ('findhelp', 'https://company.findhelp.com/careers/', 'Social-care network; mission-driven implementation services; Austin HQ.', true),
  ('Iodine Software', 'https://iodinesoftware.com/careers/', 'Healthcare AI with a clinical implementation services org; Austin HQ.', true),
  ('Jungle Scout', 'https://www.junglescout.com/careers/', 'Ecommerce intelligence platform scaling its customer org; Austin HQ.', true),
  ('Living Security', 'https://www.livingsecurity.com/careers', 'Human-risk management startup with services-led delivery; Austin HQ.', true),
  ('Ontic', 'https://ontic.co/careers/', 'Protective intelligence SaaS with a fast-growing services org; Austin HQ.', true),
  ('Osano', 'https://www.osano.com/company/careers', 'Data privacy platform building out its customer org; Austin HQ.', true)
on conflict (name) do nothing;
