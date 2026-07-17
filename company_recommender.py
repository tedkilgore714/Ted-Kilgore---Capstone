import json
import os
import re

from anthropic import Anthropic, beta_tool
from dotenv import load_dotenv
from exa_py import Exa

load_dotenv(os.path.join(os.path.dirname(__file__), "aijobscout.env"))

MODEL = "claude-sonnet-5"
MAX_SEARCHES = 40
TARGET_COMPANY_COUNT = 10
MAX_TOKENS = 32000

COMPANY_SIZE_OPTIONS = [
    "Small (1-200 employees)",
    "Mid-size (201-1,000 employees)",
    "Large (1,001-5,000 employees)",
    "Enterprise (5,000+ employees)",
    "Any Size is Great!",
]

ANY_COMPANY_SIZE = "Any Size is Great!"

LOCAL_RADIUS_MILES = 25

TRAILING_COMMA_PATTERN = re.compile(r",(\s*[\]}])")
URL_PATTERN = re.compile(r"^https?://\S+$")

# Major ATS platforms most companies' real jobs boards live on. When
# Claude's own search misses a company's jobs_url, one direct, deterministic
# Exa search checked against this list resolves most of the remaining
# misses -- without spending another (expensive, non-deterministic) Claude
# turn on what's essentially a domain-matching problem.
ATS_DOMAINS = [
    "greenhouse.io",
    "lever.co",
    "myworkday.com",
    "ashbyhq.com",
    "smartrecruiters.com",
    "icims.com",
    "jobvite.com",
    "bamboohr.com",
    "workable.com",
    "breezy.hr",
]

SYSTEM_PROMPT = (
    "You are a job hunt strategist. Given a resume, target role, location, a "
    "preferred company size range, and whether to include remote-friendly "
    f"companies, use web_search to recommend EXACTLY {TARGET_COMPANY_COUNT} "
    "companies that are a strong fit for the candidate to target.\n\n"
    "This is NOT about finding a specific open job posting — do not try to "
    "find or include a link to a specific req/listing. Do, for each company, "
    "use one web_search to find its actual jobs/careers listing page (the "
    "page that lists all of its open roles, e.g. a company's own /careers "
    "page or its Greenhouse/Lever/Workday/Ashby board) and return that as "
    "jobs_url — use the real URL from search results, never a guessed or "
    "constructed one, and use null if you can't confidently find it. Beyond "
    "that one search per company, use web_search sparingly, only to "
    "spot-check company-level signals (headcount trend, size, leadership "
    "stability) — you do not need to research every single candidate "
    f"exhaustively. Use up to {MAX_SEARCHES} searches total across all "
    f"{TARGET_COMPANY_COUNT} companies.\n\n"
    "Targeting criteria:\n"
    "- Role: match the target role, or a close director/leadership-level "
    "equivalent in the same function.\n"
    f"- Location: \"local\" means the company has an office within "
    f"{LOCAL_RADIUS_MILES} miles of the given location. If remote inclusion "
    "is OFF, only include companies with a local office. If remote "
    "inclusion is ON, include companies with a local office AND any company "
    "(regardless of where its office is) that offers remote work for this "
    "type of role.\n"
    "- Company size: a preference for the given size range, not a strict "
    "hard filter — but do not stretch it loosely either. Only include a "
    "company outside the range if its size is within roughly 50% of the "
    "range's nearest boundary (e.g. if the range tops out at 1,000 "
    "employees, a company with up to ~1,500 is acceptable; a company with "
    "3,000+ should NOT be included just because it's otherwise a strong "
    f"fit). Only go further outside that 50% band if you genuinely cannot "
    f"find {TARGET_COMPANY_COUNT} companies within or near the preferred "
    "range — and if you do, say so implicitly by making sure most of the "
    f"list stays within the tightened band. If the preferred company size "
    f"is \"{ANY_COMPANY_SIZE}\", there is no size preference at all — "
    "ignore this range/50% guidance entirely and pick the best-fitting "
    "companies regardless of size, from tiny startups to huge "
    "enterprises.\n"
    "- Growth: prefer companies whose headcount appears to be increasing "
    "year-over-year for the past few years, based on best-effort public "
    "signals (LinkedIn headcount trends, news, funding announcements, etc).\n"
    "- Hard exclude: do not include any company where the CEO has changed "
    "more than twice in the past 10 years.\n\n"
    "For each company, return: company_name, size_estimate, location_match "
    "(how this company satisfies the location requirement, e.g. \"Local "
    f"office within {LOCAL_RADIUS_MILES} miles of Austin, TX\" or "
    "\"Remote-friendly, HQ in Denver, CO\"), growth_note (a brief "
    "best-effort note on headcount trend and any leadership-turnover signal "
    "you found — this is best-effort research, not guaranteed-accurate "
    "structured data, so do not present it as verified; use null if you "
    "found nothing to go on), jobs_url (the company's actual jobs/careers "
    "listing page URL, as described above — a bare URL string or null, "
    "never prose), fit_rationale (2 sentences on why this company fits the "
    f"resume and role). Return as a JSON array of exactly "
    f"{TARGET_COMPANY_COUNT} companies and nothing else — no prose, no "
    "clarifying questions."
)


def _format_results(results):
    lines = [f"- {r.title} ({r.url}): {(r.highlights or [''])[0]}" for r in results]
    return "\n".join(lines) or "No results found."


def _find_ats_jobs_url(exa, company_name: str) -> str | None:
    """Deterministic fallback for a company Claude's own search missed.

    One direct Exa search for "{company} jobs", then check the top results
    for a domain match against a known ATS platform -- no LLM interpretation
    needed, since we're only matching a domain, not judging relevance.
    Returns None if nothing in the top results matches a known ATS domain
    (company may simply not use one, or may not have surfaced yet).
    """
    try:
        result = exa.search(f"{company_name} jobs", num_results=5)
    except Exception:
        return None

    for r in result.results:
        if any(domain in r.url for domain in ATS_DOMAINS):
            return r.url
    return None


def _get_cached_jobs_url(supabase, company_name: str) -> str | None:
    """jobs_url is an attribute of the company, not of who searched for it
    or why -- reuse any URL already resolved for this same company name by
    any prior search (any user, any role/location) instead of re-running
    paid searches for a company we've already figured out. Checked first,
    before any of the paid fallbacks below. Silently returns None (never
    raises) since this is a cost optimization, not a required dependency --
    a lookup failure should degrade to "research it fresh," not break the
    call."""
    if supabase is None:
        return None
    try:
        response = (
            supabase.table("candidates")
            .select("jobs_url")
            .ilike("company_name", company_name.strip())
            .not_.is_("jobs_url", "null")
            .limit(1)
            .execute()
        )
        if response.data:
            return response.data[0]["jobs_url"]
    except Exception:
        pass
    return None


def _parse_companies_json(text: str) -> list:
    """Extract and parse the JSON array from Claude's response text.

    Strips trailing commas before parsing — a comma immediately before a
    closing } or ] is never valid JSON, so this is a safe repair for the
    occasional LLM formatting slip rather than a real ambiguity.
    """
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON array found in Claude's response:\n{text}")
    cleaned = TRAILING_COMMA_PATTERN.sub(r"\1", match.group(0))
    companies = json.loads(cleaned)

    # jobs_url must be a bare URL or absent -- never prose from a model
    # that couldn't find one but explained itself instead of saying null.
    for company in companies:
        url = company.get("jobs_url")
        if url and not URL_PATTERN.match(url):
            company["jobs_url"] = None

    return companies


def recommend_companies(
    resume: str,
    role: str,
    location: str,
    company_size: str,
    include_remote: bool,
    angle: str = None,
    already_seen: list = None,
) -> list:
    """Ask Claude to recommend TARGET_COMPANY_COUNT companies that fit the
    resume/role/location/preferences, using best-effort company-level
    research (headcount, size, leadership stability) — not a live-verified
    job posting per company like company_matcher.match_companies().

    include_remote controls whether remote-friendly companies (regardless
    of office location) are included alongside local ones (within
    LOCAL_RADIUS_MILES of location).

    angle is an optional steering hint for this call (e.g. "healthcare
    companies" or "sub-100-employee startups") — useful for callers that
    invoke this repeatedly and want a genuinely different set of results.

    already_seen is an optional list of company names to avoid
    re-recommending (e.g. companies a caller has already collected from a
    prior call).

    Returns the parsed JSON array (list of dicts) from Claude's response.
    """
    claude = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=600.0)
    exa = Exa(api_key=os.environ["EXA_API_KEY"])
    searches_used = 0

    @beta_tool
    def web_search(query: str) -> str:
        """Search the web for a company's headcount trend, size, or leadership/CEO history.

        Args:
            query: The search query.
        """
        nonlocal searches_used
        if searches_used >= MAX_SEARCHES:
            return f"Search limit reached ({MAX_SEARCHES}). Answer with what you already have."
        searches_used += 1
        result = exa.search(query, num_results=5, contents={"highlights": True})
        return _format_results(result.results)

    user_message = (
        f"Resume:\n{resume}\n\n"
        f"Target role: {role}\n"
        f"Location: {location}\n"
        f"Preferred company size: {company_size}\n"
        f"Include remote-friendly companies: {'Yes' if include_remote else 'No'}"
    )
    if angle:
        user_message += f"\n\nSearch angle for this round: {angle}"
    if already_seen:
        user_message += (
            "\n\nDo NOT recommend any of these companies — already found in "
            f"a prior search: {', '.join(already_seen)}"
        )

    runner = claude.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        tools=[web_search],
        messages=[{"role": "user", "content": user_message}],
    )

    final_message = None
    for message in runner:
        final_message = message

    text = "".join(b.text for b in final_message.content if b.type == "text")
    if not text:
        raise ValueError(
            f"Claude's final message had no text content (stop_reason: "
            f"{final_message.stop_reason}). This usually means max_tokens "
            f"was hit mid-thought before any output was written."
        )
    companies = _parse_companies_json(text)

    try:
        from shortlist_agent import get_supabase_client
        supabase = get_supabase_client()
    except Exception:
        supabase = None

    for company in companies:
        if not company.get("jobs_url"):
            company["jobs_url"] = (
                _get_cached_jobs_url(supabase, company["company_name"])
                or _find_ats_jobs_url(exa, company["company_name"])
            )

    return companies


if __name__ == "__main__":
    sample_resume = (
        "Ted Kilgore — Director of Professional Services. 10+ years leading "
        "post-sales, onboarding, and customer success teams at B2B SaaS "
        "companies. Built and scaled PS orgs from 3 to 20+ people, owns "
        "renewal/expansion targets, background in implementation consulting."
    )
    sample_role = "Director of Professional Services"
    sample_location = "Austin, TX"
    sample_company_size = COMPANY_SIZE_OPTIONS[0]
    sample_include_remote = True

    companies = recommend_companies(
        sample_resume,
        sample_role,
        sample_location,
        sample_company_size,
        sample_include_remote,
    )
    print(json.dumps(companies, indent=2))
