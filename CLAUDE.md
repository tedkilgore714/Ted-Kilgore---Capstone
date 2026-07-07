# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Who I am

Ted Kilgore, Director of Professional Services. Building this as a capstone project and personal tool.

## Product: AI Job Scout

Target-company monitoring, not job-board scraping. Instead of searching job boards for listings, the tool watches a curated list of target companies' own career pages and surfaces new openings directly from the source — so every listing is live and real, not a stale repost.

## Problem statement

I spend 5 hours every weekday researching job openings — time that should go toward networking and skills growth. The core issue isn't finding *any* listings, it's finding fresh, relevant openings from companies worth working for, without wading through stale reposts and job-board noise.

## Full vision (not all v1 — see scope below)

1. Upload resume + preferences.
2. Claude recommends 30 target companies matched to my background.
3. I curate the list (add/remove).
4. Tool checks each target company's career page daily for new roles.
5. Daily digest of ranked opportunities.
6. I apply and track the pipeline via Kanban.

## v1 scope (Friday-shippable slice)

1. Resume pasted as text (textarea, no file upload/parsing) + preferences via a structured form.
2. Claude recommends 30 target companies using the targeting criteria below.
3. I curate the list (add/remove).

Career-page monitoring, the daily digest, alerting, Kanban tracking, and resume file upload/parsing are NOT in v1.

## Targeting criteria (used to generate the 30-company recommendation)

- **Roles**: Director of Professional Services, Sr. Manager of Professional Services, VP of Professional Services, Director of Customer Success, and similar director/leadership titles in professional services.
- **Location**, ranked: (1) Austin hybrid, (2) Austin on-site, (3) national remote — remote is lowest priority but still in scope.
- **Company fit**: soft preference for <1500 employees (not a hard filter). "Growing" = headcount increasing year-over-year for the past 3 years, checked via public hiring/headcount data (not revenue — not reliably available for private companies).
- **Deal-breaker (hard exclude)**: any company with CEO turnover more than twice in the past 10 years.

## Recommendation approach

Claude generates candidate companies from its own knowledge, then does a live web search pass per candidate to spot-check headcount growth, company size, and CEO/leadership turnover, citing sources. This is best-effort verification, not guaranteed-accurate structured data — present it that way, don't claim it's "verified." A fully verified pipeline backed by a paid data provider is v2+, not v1.

## Differentiation (the pitch)

This monitors target companies' official career pages directly, so every listing is live and real — not a stale repost — and it keeps working off the curated list after the initial recommendation, not just a one-time list.

## v2 (explicitly not v1)

- Daily career-page monitoring and digest.
- Configurable alerting (channels, schedule).
- Kanban pipeline tracking.
- Resume tailoring, cover letter generation, editable .DOCX output.
- Resume file upload (PDF/DOCX) with parsing — v1 uses paste-as-text only.

Do not build these into v1 without an explicit decision to expand scope.

## Stack

HTML/CSS/JS, Supabase, Vercel, GitHub.

## How to work with me

- Challenge my thinking — don't just agree.
- If I'm vague, ask a sharp clarifying question before assuming.
- Push back on scope creep — remind me what I said I'd cut, especially anything beyond the v1 scope above.
- Give me options with tradeoffs, not a single answer.
- Tell me directly (but respectfully) when I'm wrong.
