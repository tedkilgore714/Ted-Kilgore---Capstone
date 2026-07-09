# PRD: AI Job Scout

## Problem

Ted spends 5 hours every weekday researching job openings — time that should go toward networking and skills growth. The core issue isn't a lack of listings; it's finding fresh, relevant openings from companies worth working for, without wading through stale reposts and job-board noise.

## Product concept

Target-company monitoring, not job-board scraping. Instead of searching job boards, the tool watches a curated list of target companies' own career pages and surfaces new openings directly from the source.

## Differentiation ("why not just use LinkedIn Jobs?")

This monitors target companies' official career pages directly, so every listing is live and real — not a stale repost — and it keeps working off the curated list after the initial recommendation, not just a one-time search.

## Users

Ted Kilgore (v1, personal use only). Potential expansion to other job seekers is a post-v1 consideration, not a v1 design constraint.

## Full vision (multi-version)

1. User uploads resume + preferences.
2. Claude recommends 30 target companies matched to background.
3. User curates the list (add/remove).
4. Tool checks each target company's career page daily for new roles.
5. Delivers a daily digest of ranked opportunities.
6. User applies and tracks the pipeline via Kanban.

## v1 scope (Friday-shippable slice) — SHIPPED

1. **Input**: resume pasted as text (textarea, no file upload/parsing) + preferences captured via a structured form (roles, location ranking, company-fit signals — see Targeting criteria below).
2. **Recommendation**: Claude generates 30 target companies using the targeting criteria below.
3. **Curation**: user adds/removes companies from the recommended list.

Explicitly out of v1: career-page monitoring, digest generation, alerting, Kanban tracking, resume file upload/parsing.

v1 is complete and live. Work is now on v2 (see below).

## v2 scope (in progress)

Everything previously deferred as "v2+" is now in scope together, built on top of the
v1 company shortlist:

1. **Daily career-page monitoring**: for each company in the curated v1 shortlist,
   check its own career page daily for new postings.
2. **Ranked digest**: surface new, matching openings ranked by fit, with a direct
   link, company context, and the reasoning behind the match.
3. **Configurable alerting**: user-configurable notification channel and schedule
   (starting with email).
4. **Kanban pipeline tracking**: track each opening's status (e.g., identified →
   applied → interviewing → closed) through the application process.
5. **Resume tailoring + cover letters**: generate a tailored resume and cover
   letter draft per opening, delivered as an editable .DOCX.
6. **Resume file upload with parsing**: accept PDF/DOCX upload and parse it,
   instead of the v1 paste-as-text-only flow.

This is a substantially bigger scope than v1's slice — flagged as a risk to revisit
if it starts blocking shippable progress.

## Targeting criteria (drives the 30-company recommendation)

| Criterion | Value |
|---|---|
| Roles | Director of Professional Services, Sr. Manager of Professional Services, VP of Professional Services, Director of Customer Success, and similar director/leadership titles in professional services |
| Location (ranked) | 1. Austin hybrid  2. Austin on-site  3. National remote (lowest priority, still in scope) |
| Company size | Soft preference for <1500 employees (not a hard filter) |
| Growth signal | Headcount increasing YoY for the past 3 years (public hiring/headcount data — revenue growth not used, unreliable for private companies) |
| Hard exclude | Company has had CEO turnover more than twice in the past 10 years |

## Recommendation approach

Claude generates candidate companies from its own knowledge, then performs a live web search pass per candidate to spot-check headcount growth, company size, and CEO/leadership turnover, citing sources. This is **best-effort verification, not guaranteed-accurate structured data** — the UI/demo should present it as such (e.g., "AI-researched, spot-checked" rather than "verified"). A fully verified pipeline backed by a paid data provider (Crunchbase, Owler, etc.) is a v2+ consideration, not v1.

## Data model (Supabase)

**v1 (shipped):**

- `target_companies` — the 30 recommended companies plus curation state
  (`status`: recommended / kept / removed), match rationale, and research
  sources from the live web-search spot-check pass.
- `job_searches` — the resume text and preferences (target roles, location
  preference) submitted for a recommendation run.

**v2 (in progress):**

- `openings` — individual job postings discovered via career-page monitoring,
  linked to the `target_companies` row they came from (via `company_id`, not
  a free-text company name), with `title`, `url`, `location`, `posted_at`,
  `match_score`, `match_reasons`, `status` (Kanban stage), `notes`, and an
  `updated_at` timestamp to track pipeline movement over time.

**Known gap to fix before this goes further:** the `anon` Supabase role
currently has open `insert`/`update` RLS policies (`using (true)` /
`with check (true)`) with no ownership check. Since the anon key ships in
client-side JS on the public site, this needs to move behind Supabase Auth
(`auth.uid() = owner_id`) or a server-side function with the service role
key before real data lives in these tables.

## Success metrics

**Still open for v1** — never defined after the shift away from the earlier
job-scraping concept. Candidates: quality of the 30 recommended companies (how
many Ted keeps vs. removes), time to complete curation, or a qualitative "would
you actually apply to these" check.

**Not yet defined for v2** — candidates once monitoring/digest is live: time-to-alert
on a new posting, % of alerted openings actually applied to, or how far
opportunities move through the Kanban pipeline.

## Stack

HTML/CSS/JS, Supabase, Vercel, GitHub.

## Open questions

- Success metrics for v1 and v2 (see above).
- Fully verified company data pipeline (paid provider) — still deferred beyond
  v2; both v1 and v2 use best-effort live search (see Recommendation approach
  above).
- RLS/auth model for `openings` and future write paths (see Data model above)
  — needs to be resolved before v2 goes further.
- v2 bundles six features together (see v2 scope above) — revisit whether to
  split into shippable slices if progress stalls.
