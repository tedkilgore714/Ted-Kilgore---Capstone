-- Adds email to the candidates scope key. Without this, two different
-- people searching the same role/location/company_size/include_remote
-- collide -- the second person's request short-circuits on the first
-- person's saved results without ever running their own search.
-- Run once in the Supabase SQL editor. Safe to re-run.

alter table public.candidates add column if not exists email text;

-- Legacy rows predate email collection -- attribute them to the site
-- owner, who ran all of them during testing.
update public.candidates set email = 'tedkilgore714@gmail.com' where email is null;

drop index if exists candidates_search_company_key;
create unique index if not exists candidates_search_company_key
  on public.candidates (email, role, location, company_size, include_remote, lower(company_name));
