-- Seed the companies table for the Companies page.
-- Run this once in the Supabase SQL editor (Dashboard -> SQL Editor -> New query).
-- Safe to re-run: existing rows with the same name are skipped.

-- Make sure the columns the site reads exist (no-ops if already present).
alter table public.companies add column if not exists company_name text;
alter table public.companies add column if not exists location text;
alter table public.companies add column if not exists employees int;
alter table public.companies add column if not exists growth text;
alter table public.companies add column if not exists why text;
alter table public.companies add column if not exists url text;
alter table public.companies add column if not exists created_at timestamptz default now();

-- Let the site (anon key) read the list. Read-only: no public insert/update/delete.
grant select on public.companies to anon;
grant select on public.companies to authenticated;
alter table public.companies enable row level security;
drop policy if exists "public read" on public.companies;
create policy "public read" on public.companies for select using (true);

-- One row per company name.
create unique index if not exists companies_name_key on public.companies (company_name);

insert into public.companies (company_name, location, employees, growth, why, url) values
  ('ActiveProspect', 'Austin hybrid', '250', 'Headcount +12% YoY', 'Consent-based marketing SaaS with a growing customer org; Austin HQ.', 'https://activeprospect.com/careers/'),
  ('AffiniPay', 'Austin hybrid', '700', 'Headcount +15% YoY', 'Payments platform for professional associations; strong PS/CS leadership presence in Austin.', 'https://affinipay.com/careers/'),
  ('AlertMedia', 'Austin hybrid', '500', 'Headcount +20% YoY', 'Emergency communication SaaS with a customer-heavy org; Austin HQ.', 'https://www.alertmedia.com/careers/'),
  ('BigCommerce', 'Austin hybrid', '1200', 'Steady, enterprise push', 'Ecommerce platform with services and partner orgs; Austin HQ.', 'https://careers.bigcommerce.com/'),
  ('Billd', 'Austin on-site', '200', 'Headcount +25% YoY', 'Construction fintech scaling customer operations from Austin.', 'https://billd.com/careers/'),
  ('Bloomerang', 'Remote (national)', '500', 'Growing via acquisitions', 'Nonprofit CRM consolidating its market; building out services leadership.', 'https://bloomerang.co/careers/'),
  ('CrowdStreet', 'Austin hybrid', '200', 'Rebuilding under new leadership', 'Commercial real estate investing platform relocated to Austin; investor-services org.', 'https://www.crowdstreet.com/careers'),
  ('Degreed', 'Remote (national)', '700', 'Stable to growing', 'Workforce upskilling platform with an enterprise CS/PS org.', 'https://degreed.com/about/careers'),
  ('Dialpad', 'Remote (national)', '1300', 'Headcount +10% YoY', 'AI communications platform with a sizable professional services team.', 'https://www.dialpad.com/careers'),
  ('findhelp', 'Austin hybrid', '300', 'Headcount +10% YoY', 'Social-care network; mission-driven implementation services; Austin HQ.', 'https://company.findhelp.com/careers/'),
  ('Gong', 'Remote / hybrid hubs', '1400', 'Headcount +8% YoY', 'Revenue AI leader with mature PS and CS organizations.', 'https://www.gong.io/careers/'),
  ('Guru', 'Remote (national)', '200', 'Lean, profitable growth', 'Knowledge-management SaaS with senior CS leadership scope.', 'https://www.getguru.com/careers'),
  ('Iodine Software', 'Austin hybrid', '600', 'Headcount +15% YoY', 'Healthcare AI with a clinical implementation services org; Austin HQ.', 'https://iodinesoftware.com/careers/'),
  ('Jungle Scout', 'Austin hybrid', '300', 'Steady', 'Ecommerce intelligence platform scaling its customer org; Austin HQ.', 'https://www.junglescout.com/careers/'),
  ('Kajabi', 'Remote (national)', '400', 'Headcount +12% YoY', 'Creator-economy platform investing in customer success.', 'https://kajabi.com/careers'),
  ('Lattice', 'Remote (national)', '700', 'Recovering growth', 'HR tech with an established PS and onboarding practice.', 'https://lattice.com/careers'),
  ('Living Security', 'Austin hybrid', '100', 'Headcount +20% YoY', 'Human-risk management startup with services-led delivery; Austin HQ.', 'https://www.livingsecurity.com/careers'),
  ('LogicMonitor', 'Austin hybrid', '1000', 'Headcount +10% YoY', 'Observability platform with a large Austin office and PS org.', 'https://www.logicmonitor.com/careers'),
  ('Olo', 'Remote (national)', '700', 'Steady growth', 'Restaurant SaaS with deployment and professional services teams.', 'https://www.olo.com/careers'),
  ('Ontic', 'Austin hybrid', '500', 'Headcount +25% YoY', 'Protective intelligence SaaS with a fast-growing services org; Austin HQ.', 'https://ontic.co/careers/'),
  ('Osano', 'Austin hybrid', '150', 'Headcount +15% YoY', 'Data privacy platform building out its customer org; Austin HQ.', 'https://www.osano.com/company/careers'),
  ('Postscript', 'Remote (national)', '250', 'Headcount +20% YoY', 'SMS marketing for Shopify brands; scaling customer success.', 'https://postscript.io/careers'),
  ('Qualia', 'Austin hybrid', '400', 'Steady growth', 'Real-estate closing platform with implementation services; Austin office.', 'https://www.qualia.com/careers/'),
  ('Rev.com', 'Austin hybrid', '400', 'Growing on AI pivot', 'Speech AI company expanding enterprise services; Austin HQ.', 'https://www.rev.com/careers'),
  ('Self Financial', 'Austin hybrid', '300', 'Headcount +10% YoY', 'Credit-building fintech with customer operations leadership; Austin HQ.', 'https://www.self.inc/careers'),
  ('Shipwell', 'Austin hybrid', '200', 'Steady', 'Freight TMS with implementation and CS orgs; Austin HQ.', 'https://shipwell.com/careers/'),
  ('Vanta', 'Remote (national)', '700', 'Headcount +30% YoY', 'Trust management leader rapidly scaling its post-sales org.', 'https://www.vanta.com/careers'),
  ('Workrise', 'Austin hybrid', '600', 'Refocused, growing', 'Energy workforce platform; Austin HQ.', 'https://www.workrise.com/careers'),
  ('WP Engine', 'Austin hybrid', '1100', 'Steady', 'Managed WordPress host with a large customer experience org; Austin HQ.', 'https://wpengine.careers/'),
  ('Zello', 'Austin hybrid', '100', 'Profitable, growing', 'Push-to-talk leader with a lean customer team and leadership need; Austin HQ.', 'https://zello.com/careers/')
on conflict (company_name) do nothing;
