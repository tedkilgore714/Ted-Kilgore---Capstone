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

# Some careers pages refuse the default python-requests UA; a plain browser
# UA keeps the (public, unauthenticated) page fetch working.
_UA_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AIJobScout/1.0)"}

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
    elif host.endswith(".bamboohr.com") or host.endswith(".breezy.hr"):
        # Subdomain-tokened platforms: acme.bamboohr.com / acme.breezy.hr.
        token = host.split(".")[0]
        if token and token not in _GENERIC_SUBDOMAINS:
            platform = "bamboohr" if host.endswith(".bamboohr.com") else "breezy"
            return (platform, token)
    return None


# Subdomain labels that can never be a company's board token on the
# subdomain-tokened platforms (bamboohr/breezy) -- marketing sites, CDNs,
# and app hosts that would otherwise false-match the embed patterns below
# (e.g. a "learn more at www.bamboohr.com" footer link).
_GENERIC_SUBDOMAINS = {"www", "app", "api", "static", "cdn", "attachments-cdn", "help", "support"}

# Signatures an ATS embed leaves in a company's own careers-page HTML, most
# explicit first. Each is (platform, compiled pattern with the board token as
# group 1). The Greenhouse embed-script form (job_board/js?for=<token>) is
# what pages like logicmonitor.com/careers use -- the page looks custom, but
# this script is serving it straight off Greenhouse.
_EMBED_PATTERNS = [
    ("greenhouse", re.compile(r"boards\.greenhouse\.io/embed/job_board(?:/js)?\?[^\"'<>\s]*?for=([A-Za-z0-9_-]+)")),
    ("greenhouse", re.compile(r"boards-api\.greenhouse\.io/v1/boards/([A-Za-z0-9_-]+)")),
    ("greenhouse", re.compile(r"job-boards\.greenhouse\.io/([A-Za-z0-9_-]+)")),
    ("greenhouse", re.compile(r"boards\.greenhouse\.io/(?!embed\b)([A-Za-z0-9_-]+)")),
    ("lever", re.compile(r"api\.lever\.co/v0/postings/([A-Za-z0-9_-]+)")),
    ("lever", re.compile(r"jobs\.lever\.co/([A-Za-z0-9_-]+)")),
    ("ashby", re.compile(r"api\.ashbyhq\.com/posting-api/job-board/([A-Za-z0-9_.%-]+)")),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)")),
    ("bamboohr", re.compile(r"([A-Za-z0-9-]+)\.bamboohr\.com")),
    ("breezy", re.compile(r"([A-Za-z0-9-]+)\.breezy\.hr")),
]


def detect_embedded_ats(careers_url: str) -> tuple | None:
    """Companies increasingly serve their ATS board through their own domain
    (acme.com/careers) instead of linking the bare board URL, so the stored
    jobs_url often isn't a recognizable ATS domain even though a supported
    board powers it. Fetch the page once and look for the embed's signature
    in the HTML. Returns (platform, board_token) or None; never raises."""
    if not careers_url:
        return None
    url = careers_url if "://" in careers_url else f"https://{careers_url}"
    try:
        resp = requests.get(url, timeout=HTTP_TIMEOUT, headers=_UA_HEADERS)
        resp.raise_for_status()
        html = resp.text
    except requests.RequestException:
        return None

    for platform, pattern in _EMBED_PATTERNS:
        for match in pattern.finditer(html):
            token = match.group(1)
            # A marketing/CDN link ("try www.bamboohr.com") isn't a board --
            # keep looking for a real token instead of stopping at it.
            if token in _GENERIC_SUBDOMAINS:
                continue
            return (platform, token)
    return None


def canonical_board_url(platform: str, token: str) -> str:
    """The bare, directly-detectable board URL for a resolved platform/token
    -- what we persist back onto the candidates row so future scans (and the
    cross-user jobs_url cache) skip the HTML fetch."""
    return {
        "greenhouse": f"https://boards.greenhouse.io/{token}",
        "lever": f"https://jobs.lever.co/{token}",
        "ashby": f"https://jobs.ashbyhq.com/{token}",
        "bamboohr": f"https://{token}.bamboohr.com/careers",
        "breezy": f"https://{token}.breezy.hr",
    }[platform]


# Hosts that are job platforms rather than the company's own site. A careers
# URL on one of these must not contribute its domain as a board-token guess
# below -- e.g. careers-carousel.icims.com would yield the token "icims",
# which could validate against some unrelated company's board.
_PLATFORM_HOSTS = (
    "greenhouse.io", "lever.co", "ashbyhq.com", "myworkday.com",
    "smartrecruiters.com", "icims.com", "jobvite.com", "bamboohr.com",
    "workable.com", "breezy.hr", "jazzhr.com", "adp.com", "paylocity.com",
)


def guess_board(jobs_url: str, company_name: str) -> tuple | None:
    """Last-resort resolution for careers pages that render their board with
    custom JavaScript, where no embed signature appears in the HTML (e.g.
    logicmonitor.com/careers builds its Greenhouse board client-side).

    Guess the board token from the company's own domain and name, then
    validate each guess against the three ATS APIs -- a guess only counts if
    the API answers with a real, non-empty board. The domain stem is a strong
    brand identifier, so a validated hit is almost certainly the right
    company; the theoretical miss (an unrelated company owning the exact
    brand-slug token on some platform) is accepted as a rare, reviewable
    wrong-company card rather than a reason to leave the whole company
    unscannable. Returns (platform, token) or None; never raises."""
    tokens = []

    if jobs_url:
        try:
            parsed = urlparse(jobs_url if "://" in jobs_url else f"https://{jobs_url}")
            host = (parsed.netloc or "").lower().removeprefix("www.")
            if host and not any(p in host for p in _PLATFORM_HOSTS):
                # Registrable-domain stem: "logicmonitor" from
                # www.logicmonitor.com or careers.logicmonitor.com.
                stem = host.split(".")[-2] if "." in host else host
                if stem:
                    tokens.append(stem)
        except ValueError:
            pass

    name_slug = re.sub(r"[^a-z0-9]", "", (company_name or "").lower())
    if name_slug and name_slug not in tokens:
        tokens.append(name_slug)

    for token in tokens:
        for platform, fetcher in _FETCHERS.items():
            try:
                if fetcher(token):
                    return (platform, token)
            except (requests.RequestException, ValueError):
                continue
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


def _fetch_bamboohr(token: str) -> list:
    # Same public endpoint BambooHR's own careers widget calls. The list API
    # carries no posted date; atsLocation is the structured one (the plain
    # `location` field is often all-null).
    url = f"https://{token}.bamboohr.com/careers/list"
    resp = requests.get(url, timeout=HTTP_TIMEOUT, headers=_UA_HEADERS)
    resp.raise_for_status()
    postings = []
    for job in resp.json().get("result", []):
        loc = job.get("atsLocation") or job.get("location") or {}
        city, state = loc.get("city"), loc.get("state")
        postings.append(
            {
                "title": job.get("jobOpeningName"),
                "url": f"https://{token}.bamboohr.com/careers/{job['id']}" if job.get("id") else None,
                "location": ", ".join(p for p in (city, state) if p) or None,
                "posted_at": None,
            }
        )
    return postings


def _fetch_breezy(token: str) -> list:
    url = f"https://{token}.breezy.hr/json"
    resp = requests.get(url, timeout=HTTP_TIMEOUT, headers=_UA_HEADERS)
    resp.raise_for_status()
    postings = []
    for job in resp.json():
        postings.append(
            {
                "title": job.get("name"),
                "url": job.get("url"),
                "location": (job.get("location") or {}).get("name"),
                "posted_at": _iso_from_str(job.get("published_date")),
            }
        )
    return postings


_FETCHERS = {
    "greenhouse": _fetch_greenhouse,
    "lever": _fetch_lever,
    "ashby": _fetch_ashby,
    "bamboohr": _fetch_bamboohr,
    "breezy": _fetch_breezy,
}


def find_matching_postings(jobs_url: str, role: str, company_name: str = "") -> tuple:
    """All currently-open postings on `jobs_url`'s board whose title matches
    `role`, best match first, capped at MAX_POSTINGS_PER_COMPANY.

    Board resolution runs cheapest-and-most-certain first:
      1. detect_ats        -- jobs_url already is a bare board URL.
      2. detect_embedded_ats -- fetch the careers page, read the embed
                                signature out of its HTML.
      3. guess_board       -- derive candidate tokens from the company's
                              domain/name and validate them against the ATS
                              APIs (covers JS-rendered boards with no
                              signature in the HTML).

    Returns (postings, resolved_board_url). resolved_board_url is only set
    when step 2 or 3 had to discover the board -- the caller should persist
    it over the stored jobs_url so the next scan goes straight to the board.
    It stays None when jobs_url already was the board.

    Returns ([], None) (never raises) for an unresolvable board, an
    unreachable one, or one with no role-matching openings -- one bad
    company should never sink a whole scan.
    """
    resolved_url = None
    detected = detect_ats(jobs_url)
    if not detected:
        detected = detect_embedded_ats(jobs_url) or guess_board(jobs_url, company_name)
        if not detected:
            return ([], None)
        resolved_url = canonical_board_url(*detected)
    platform, token = detected
    try:
        postings = _FETCHERS[platform](token)
    except (requests.RequestException, ValueError):
        return ([], None)

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
    return (matched[:MAX_POSTINGS_PER_COMPANY], resolved_url)
