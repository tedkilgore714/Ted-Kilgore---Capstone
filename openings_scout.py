"""Turn a user's saved target companies into openings on their board.

Phase A orchestration: take the companies on a user's My Companies page
(their most recent search), read each one's ATS board via ats_scanner, and
insert any role-matching live postings into the openings table as
source='scout' cards. My Openings then shows them exactly like manually
added cards -- Supabase Realtime pushes them onto any open board live.

Runs with the service-role Supabase client (same as the shortlist job), so
it can write rows on the user's behalf; every inserted row carries the
user_id, and RLS still scopes what the browser can read back.
"""
from datetime import datetime, timezone

from ats_scanner import find_matching_postings
from shortlist_agent import get_supabase_client

MAX_COMPANIES_PER_SCAN = 25  # bound the work (and any future paid tiers)


def _latest_scope_companies(supabase, user_id: str) -> list:
    """The active (non-rejected) companies from the user's most recent
    search -- the same set My Companies shows. Returns [] if the user has
    never run a search.

    "Most recent" = the scope key of their newest candidates row by
    updated_at (falling back to created_at); mirrors how companies.js picks
    which single search to display.
    """
    response = (
        supabase.table("candidates")
        .select("*")
        .eq("user_id", user_id)
        .eq("rejected", False)
        .order("updated_at", desc=True)
        .order("created_at", desc=True)
        .execute()
    )
    rows = response.data or []
    if not rows:
        return []

    newest = rows[0]
    scope_fields = (
        "role", "location", "company_size", "include_remote",
        "radius_miles", "prioritize_growth", "prioritize_stability",
    )
    scope = {f: newest.get(f) for f in scope_fields}
    return [r for r in rows if all(r.get(f) == scope[f] for f in scope_fields)]


def _existing_opening_urls(supabase, user_id: str) -> set:
    """Every posting URL already on this user's board, so a rescan adds only
    genuinely new openings instead of duplicating cards. Lower-cased to match
    the (user_id, lower(url)) uniqueness the migration enforces at the DB
    level -- this is the friendly pre-check; the index is the backstop."""
    response = (
        supabase.table("openings")
        .select("url")
        .eq("user_id", user_id)
        .not_.is_("url", "null")
        .execute()
    )
    return {row["url"].lower() for row in (response.data or []) if row.get("url")}


def scan_openings_for_user(user_id: str) -> dict:
    """Scan the user's current target companies for live openings and insert
    the new ones. Returns a small summary dict for logging. Safe to re-run --
    already-tracked postings are skipped.
    """
    supabase = get_supabase_client()
    companies = _latest_scope_companies(supabase, user_id)
    if not companies:
        print(f"[scan] user {user_id}: no active companies to scan", flush=True)
        return {"companies_scanned": 0, "openings_added": 0}

    companies = companies[:MAX_COMPANIES_PER_SCAN]
    seen_urls = _existing_opening_urls(supabase, user_id)
    now = datetime.now(timezone.utc).isoformat()

    rows_to_insert = []
    scanned = 0
    for company in companies:
        jobs_url = company.get("jobs_url")
        if not jobs_url:
            continue
        scanned += 1
        postings, resolved_url = find_matching_postings(
            jobs_url, company.get("role") or "", company.get("company_name") or ""
        )

        # The stored jobs_url was a company's own careers page and the real
        # board had to be discovered from its HTML -- persist the bare board
        # URL so the next scan (and the cross-user jobs_url cache in
        # company_recommender) goes straight to it. Best-effort: a failed
        # update just means the same one-page fetch happens again next scan.
        if resolved_url:
            try:
                supabase.table("candidates").update({"jobs_url": resolved_url}).eq(
                    "id", company["id"]
                ).execute()
                print(
                    f"[scan] resolved {company['company_name']}: {jobs_url} -> {resolved_url}",
                    flush=True,
                )
            except Exception as e:
                print(f"[scan] couldn't persist resolved board for {company['company_name']}: {e}", flush=True)
        for posting in postings:
            url_key = posting["url"].lower()
            if url_key in seen_urls:
                continue
            seen_urls.add(url_key)
            rows_to_insert.append(
                {
                    "user_id": user_id,
                    "company": company["company_name"],
                    "title": posting["title"],
                    "url": posting["url"],
                    "location": posting.get("location"),
                    "posted_at": posting.get("posted_at"),
                    "match_score": posting.get("match_score"),
                    "match_reasons": (
                        f"Auto-found on {company['company_name']}'s "
                        f"{posting['platform'].title()} board, matched to your "
                        f"target role \"{company.get('role')}\"."
                    ),
                    "status": "identified",
                    "source": "scout",
                    "found_at": now,
                }
            )

    added = 0
    if rows_to_insert:
        # Insert one row at a time so a single duplicate (the unique index
        # firing on a URL added since the pre-check) can't abort the whole
        # batch -- each conflict is just skipped.
        for row in rows_to_insert:
            try:
                supabase.table("openings").insert(row).execute()
                added += 1
            except Exception as e:
                print(f"[scan] skipped {row['url']}: {e}", flush=True)

    print(
        f"[scan] user {user_id}: scanned {scanned} companies, added {added} openings",
        flush=True,
    )
    return {"companies_scanned": scanned, "openings_added": added}
