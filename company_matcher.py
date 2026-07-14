import json
import os
import re

import requests
from anthropic import Anthropic, beta_tool
from dotenv import load_dotenv
from exa_py import Exa

load_dotenv(os.path.join(os.path.dirname(__file__), "aijobscout.env"))

MODEL = "claude-sonnet-5"
MAX_SEARCHES = 15
MAX_VERIFICATION_ROUNDS = 2

CLOSED_POSTING_PHRASES = [
    "no longer",  # catches "no longer open/active/available/accepting..."
    "position was filled",
    "position has been filled",
    "job has been filled",
    "this job is closed",
    "posting has expired",
    "ad has expired",
    "job posting you're looking for might have closed",
    "we couldn't find anything here",
    "page not found",
    "job not found",
]

URL_PATTERN = re.compile(r"^https?://\S+$")
JOB_ID_PATTERN = re.compile(
    r"\d{4,}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
TRAILING_COMMA_PATTERN = re.compile(r",(\s*[\]}])")

SYSTEM_PROMPT = (
    "You are a job hunt strategist. Given a resume, target role, and location, "
    "use web_search to find EXACTLY 5 companies that fit AND that you can "
    "verify have an open position posted directly on their own careers/jobs "
    "site. For each: company_name, job_title (the specific open role title "
    "from the posting), size_estimate, location_match, hiring_signal (a real "
    "job posting URL for that company only — either on the company's own "
    "domain, e.g. careers.company.com, or a single-tenant ATS-hosted board "
    "exclusively for that company, e.g. job-boards.greenhouse.io/company, "
    "jobs.lever.co/company, company.wd1.myworkdayjobs.com, or similar. NEVER "
    "a multi-employer job board or aggregator that lists postings from many "
    "different companies, such as LinkedIn, Indeed, Glassdoor, ZipRecruiter, "
    "or BuiltIn. hiring_signal must link to the specific job posting itself "
    "(a URL containing that posting's own job/req ID), NEVER a generic "
    "company careers homepage or a search/browse-all-openings page. "
    "hiring_signal must be ONLY the bare URL string — no explanatory text, "
    "job titles, req numbers, or parenthetical notes appended to it), "
    "fit_rationale "
    "(2 sentences). hiring_signal is a hard requirement: if you cannot "
    "verify a posting on a candidate company's own site, drop that company "
    "and search for a different one instead — every company in your final "
    "answer must have a confirmed hiring_signal; never use null for "
    "hiring_signal. When searching, prefer queries that target the "
    "company's own domain (e.g. 'site:company.com careers'). Return as JSON "
    f"array of exactly 5 companies, each with a verified hiring_signal. Use "
    f"max {MAX_SEARCHES} searches. For size_estimate and location_match, "
    "use null only if genuinely uncertain. Your final response must ALWAYS "
    "be the JSON array and nothing else — never prose, never a clarifying "
    "question. If you run out of search budget before verifying all 5, "
    "return the JSON array with only the companies you have already "
    "confirmed (fewer than 5 is fine) rather than asking for more budget "
    "or guessing at a hiring_signal."
)


def _format_results(results):
    lines = [f"- {r.title} ({r.url}): {(r.highlights or [''])[0]}" for r in results]
    return "\n".join(lines) or "No results found."


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
    return json.loads(cleaned)


def _is_posting_live(url) -> bool:
    """Fetch a hiring_signal URL and check it actually returns an open posting.

    Catches the common ATS "this job is closed" patterns (Greenhouse redirects
    to ?error=true, Lever 404s, etc.) rather than trusting Exa's search index,
    which can be stale. Not bulletproof against heavily JS-rendered pages that
    don't include the closed-posting text in the raw HTML.

    Also rejects URLs with no job/req ID in the path (e.g. a generic company
    careers homepage) — those aren't links to a specific posting, even if
    the page itself loads fine.
    """
    if not url or not URL_PATTERN.match(url):
        return False
    if not JOB_ID_PATTERN.search(url):
        return False
    try:
        response = requests.get(
            url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}
        )
    except requests.RequestException:
        return False
    if response.status_code != 200:
        return False
    if "error=true" in response.url.lower():
        return False
    if not JOB_ID_PATTERN.search(response.url):
        # Redirected away from the specific posting to a generic page
        # (e.g. a closed job silently bouncing to the careers homepage).
        return False
    text = response.text.lower()
    return not any(phrase in text for phrase in CLOSED_POSTING_PHRASES)


def match_companies(resume: str, role: str, location: str) -> list:
    """Ask Claude to find 5 companies matching the resume/role/location, using Exa search.

    Returns the parsed JSON array (list of dicts) from Claude's response.
    """
    claude = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    exa = Exa(api_key=os.environ["EXA_API_KEY"])
    searches_used = 0

    @beta_tool
    def web_search(query: str) -> str:
        """Search the web for information about a company — headcount growth, size, leadership turnover, or open job postings.

        Args:
            query: The search query.
        """
        nonlocal searches_used
        if searches_used >= MAX_SEARCHES:
            return f"Search limit reached ({MAX_SEARCHES}). Answer with what you already have."
        searches_used += 1
        result = exa.search(query, num_results=5, contents={"highlights": True})
        return _format_results(result.results)

    messages = [
        {
            "role": "user",
            "content": f"Resume:\n{resume}\n\nTarget role: {role}\nLocation: {location}",
        }
    ]

    # Tracks the best verified set found so far. If a later round breaks
    # format (e.g. Claude runs out of search budget and responds with a
    # clarifying question instead of JSON), fall back to this instead of
    # crashing the whole request.
    verified_companies = []

    for attempt in range(MAX_VERIFICATION_ROUNDS + 1):
        runner = claude.beta.messages.tool_runner(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            tools=[web_search],
            messages=messages,
        )

        final_message = None
        for message in runner:
            final_message = message
        messages.append({"role": "assistant", "content": final_message.content})

        text = "".join(b.text for b in final_message.content if b.type == "text")
        try:
            companies = _parse_companies_json(text)
        except ValueError:
            return verified_companies

        live = {id(c): _is_posting_live(c.get("hiring_signal")) for c in companies}
        verified_companies = [c for c in companies if live[id(c)]]
        broken = [c for c in companies if not live[id(c)]]

        if not broken or attempt == MAX_VERIFICATION_ROUNDS:
            # Never return a company whose hiring_signal couldn't be
            # confirmed live, even after retries — an unverifiable listing
            # is worse than one fewer result.
            return verified_companies

        broken_names = ", ".join(c["company_name"] for c in broken)
        messages.append(
            {
                "role": "user",
                "content": (
                    f"These hiring_signal URLs are dead or the posting is no "
                    f"longer open: {broken_names}. Replace those companies "
                    f"with different ones that have a verified, currently "
                    f"open posting on their own careers site or a "
                    f"single-tenant ATS board. Return the full updated JSON "
                    f"array of 5 companies."
                ),
            }
        )


if __name__ == "__main__":
    sample_resume = (
        "Ted Kilgore — Director of Professional Services. 10+ years leading "
        "post-sales, onboarding, and customer success teams at B2B SaaS "
        "companies. Built and scaled PS orgs from 3 to 20+ people, owns "
        "renewal/expansion targets, background in implementation consulting."
    )
    sample_role = "Director of Professional Services"
    sample_location = "Austin, TX (hybrid preferred)"

    companies = match_companies(sample_resume, sample_role, sample_location)
    print(json.dumps(companies, indent=2))
