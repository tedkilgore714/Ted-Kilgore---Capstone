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

## v1 scope (Friday-shippable slice)

1. **Input**: resume pasted as text (textarea, no file upload/parsing) + preferences captured via a structured form (roles, location ranking, company-fit signals — see Targeting criteria below).
2. **Recommendation**: Claude generates 30 target companies using the targeting criteria below.
3. **Curation**: user adds/removes companies from the recommended list.

Explicitly out of v1: career-page monitoring, digest generation, alerting, Kanban tracking, resume file upload/parsing.

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

## Out of scope for v1 (planned for v2+)

- Daily career-page monitoring and digest.
- Configurable alerting (channels, schedule).
- Kanban pipeline tracking.
- Resume tailoring, cover letter generation, editable .DOCX output.
- Resume file upload (PDF/DOCX) with parsing — v1 uses paste-as-text only.

## Success metrics

**Open — not yet defined for this scope.** The metrics previously discussed (listing-research time, % validated listings/day, search-to-career-page time) were built for the earlier job-scraping concept and don't map cleanly to a company-recommendation-and-curation v1. Needs a fresh pass: e.g., quality of the 30 recommended companies (how many Ted keeps vs. removes), time to complete curation, or a qualitative "would you actually apply to these" check.

## Stack

HTML/CSS/JS, Supabase, Vercel, GitHub.

## Open questions

- Success metrics for v1 (see above).
- Fully verified company data pipeline (paid provider) — deferred to v2+; v1 uses best-effort live search (see Recommendation approach above).
