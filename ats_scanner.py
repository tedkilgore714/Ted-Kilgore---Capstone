"""Read live job postings straight off a company's ATS board.

Phase A of the Openings automation: given a company's jobs_url (already
researched and stored on each candidates row by company_recommender.py),
detect which applicant-tracking system hosts it and call that ATS's public
JSON API to list the currently-open roles. No AI, no web search, no cost --
these are the same public endpoints the ATS's own careers widget calls.

Only the three ATS platforms with clean, unauthenticated JSON boards are
handled here (Greenhouse, Lever, Ashby). Companies on any other platform --
or with a plain custom careers page -- return no postings from this module;
the (planned) Phase B agent fallback is what covers those.
"""
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

HTTP_TIMEOUT = 12  # seconds -- one unresponsive board shouldn't stall a scan
MAX_POSTINGS_PER_COMPANY = 5  # keep a huge board from flooding one user's list

# Words that carry no matching signal in a job title -- dropped before
# comparing a stored target role against a live posting title.
_STOPWORDS = {"of", "the", "and", "for", "a", "an", "to", "in", "at", "on", "&", "-", "/"}


def _significant_words(text: str) -> set:
    words = re.split(r"[^a-z0-9]+", (text or "").lower())
    return {w for w in words if w and w not in _STOPWORDS}


def role_matches_title(role: str, title: str, threshold: float = 0.5) -> float:
    """How well a live posting title matches the user's target role, as a
    0.0-1.0 keyword-overlap ratio. Returns the ratio when it clears
    `threshold` (so the caller can reuse it as a rough match_score), else 0.0.

    Deliberately simple -- this is the free Phase A heuristic. Phase B layers
    a real Claude fit-score on top for the postings this lets through.
    """
    role_words = _significant_words(role)
    if not role_words:
        return 0.0
    title_words = _significant_words(title)
    overlap = len(role_words & title_words) / len(role_words)
    return overlap if overlap >= threshold else 0.0


def detect_ats(jobs_url: str) -> tuple | None:
    """Map a jobs_url to (platform, board_token), or None if it isn't one of
    the three JSON-board ATS platforms we can read. board_token is the
    company's slug on that platform (e.g. 'acme' in jobs.lever.co/acme)."""
    if not jobs_url:
        return None
    try:
        parsed = urlparse(jobs_url if "://" in jobs_url else f"https://{jobs_url}")
    except ValueError:
        return None
    host = (parsed.netloc or "").lower()
    path_parts = [p for p in parsed.path.split("/") if p]

    if "greenhouse.io" in host:
        # boards.greenhouse.io/<token>, job-boards.greenhouse.io/<token>, or
        # greenhouse.io/embed/job_board?for=<token>
        for_match = re.search(r"(?:^|&)for=([^&]+)", parsed.query)
        if for_match:
            return ("greenhouse", for_match.group(1))
        parts = [p for p in path_parts if p not in ("embed", "job_board", "jobs")]
        if parts:
            return ("greenhouse", parts[0])
    elif "lever.co" in host:
        if path_parts:
            return ("lever", path_parts[0])
    elif "ashbyhq.com" in host:
        if path_parts:
            return ("ashby", path_parts[0])
    return None


def _iso_from_ms(ms) -> str | None:
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _iso_from_str(value) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def _fetch_greenhouse(token: str) -> list:
    url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
    resp = requests.get(url, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    postings = []
    for job in resp.json().get("jobs", []):
        postings.append(
            {
                "title": job.get("title"),
                "url": job.get("absolute_url"),
                "location": (job.get("location") or {}).get("name"),
                "posted_at": _iso_from_str(job.get("updated_at") or job.get("first_published")),
            }
        )
    return postings


def _fetch_lever(token: str) -> list:
    url = f"https://api.lever.co/v0/postings/{token}?mode=json"
    resp = requests.get(url, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    postings = []
    for job in resp.json():
        categories = job.get("categories") or {}
        postings.append(
            {
                "title": job.get("text"),
                "url": job.get("hostedUrl") or job.get("applyUrl"),
                "location": categories.get("location"),
                "posted_at": _iso_from_ms(job.get("createdAt")),
            }
        )
    return postings


def _fetch_ashby(token: str) -> list:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{token}"
    resp = requests.get(url, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    postings = []
    for job in resp.json().get("jobs", []):
        postings.append(
            {
                "title": job.get("title"),
                "url": job.get("jobUrl") or job.get("applyUrl"),
                "location": job.get("location"),
                "posted_at": _iso_from_str(job.get("publishedAt") or job.get("publishedDate")),
            }
        )
    return postings


_FETCHERS = {
    "greenhouse": _fetch_greenhouse,
    "lever": _fetch_lever,
    "ashby": _fetch_ashby,
}


def find_matching_postings(jobs_url: str, role: str) -> list:
    """All currently-open postings on `jobs_url`'s board whose title matches
    `role`, best match first, capped at MAX_POSTINGS_PER_COMPANY.

    Returns [] (never raises) for an unrecognized ATS, an unreachable board,
    or a board with no role-matching openings -- one bad company should never
    sink a whole scan.
    """
    detected = detect_ats(jobs_url)
    if not detected:
        return []
    platform, token = detected
    try:
        postings = _FETCHERS[platform](token)
    except (requests.RequestException, ValueError):
        return []

    matched = []
    for posting in postings:
        title, url = posting.get("title"), posting.get("url")
        if not title or not url:
            continue
        score = role_matches_title(role, title)
        if score <= 0:
            continue
        matched.append(
            {
                "title": title,
                "url": url,
                "location": posting.get("location"),
                "posted_at": posting.get("posted_at"),
                "match_score": round(score * 100),
                "platform": platform,
            }
        )

    matched.sort(key=lambda p: p["match_score"], reverse=True)
    return matched[:MAX_POSTINGS_PER_COMPANY]
