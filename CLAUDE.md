# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Who I am

Ted Kilgore, Director of Professional Services. Building this as a capstone project and personal tool.

## Problem statement

I spend 5 hours every weekday researching and applying to job openings — time that should go toward networking and skills growth. Specific pain points:
- Too many listings to sift through manually.
- Most listings are stale/no longer active.
- Applications go through ATS systems that often filter them out before a human ever sees them.
- To be seriously considered, I need to apply the same day a role is posted.

## Vision

v1 is a personal tool for my own job search. If it works, it may eventually become a product for other job seekers — but that's explicitly out of scope for v1.

## v1 scope

A website that takes in my job titles/keywords and location/remote preference, and automates:
1. Finding job listings matching those titles/keywords and location/remote preference.
2. Validating listings are real and currently active.
3. Opening the job posting on the official company career site so I can manually submit.

Manual submission is intentional for v1 — no auto-submit.

### Validation approach

Listings are sourced from LinkedIn. A listing is validated by navigating to the hiring company's own career page and checking for a matching posting. No match on the career page = the role is no longer valid.

**Open questions to resolve in the PRD:**
- LinkedIn's ToS prohibits automated scraping; scraping under a personal account risks that account being restricted. Decide: manual-paste input, a non-LinkedIn job source/API, or accepted scraping risk.
- How to resolve a company name/LinkedIn post into the correct career page URL.
- What counts as a "match" on the career page (exact title, fuzzy match, human confirmation).

## v2 (explicitly not v1)

- Tailoring my resume for the specific role.
- Writing a cover letter for the role.
- Producing editable .DOCX files for both.

Do not build these into v1 without an explicit decision to expand scope.

## Stack

HTML/CSS/JS, Supabase, Vercel, GitHub.

## How to work with me

- Challenge my thinking — don't just agree.
- If I'm vague, ask a sharp clarifying question before assuming.
- Push back on scope creep — remind me what I said I'd cut, especially anything beyond the six v1 steps above.
- Give me options with tradeoffs, not a single answer.
- Tell me directly (but respectfully) when I'm wrong.
