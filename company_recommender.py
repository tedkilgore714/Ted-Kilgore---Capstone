import json
import os
import re

from anthropic import Anthropic, beta_tool
from dotenv import load_dotenv
from exa_py import Exa

load_dotenv(os.path.join(os.path.dirname(__file__), "aijobscout.env"))

MODEL = "claude-sonnet-5"
MAX_SEARCHES = 40
TARGET_COMPANY_COUNT = 30

COMPANY_SIZE_OPTIONS = [
    "Small (1-200 employees)",
    "Mid-size (201-1,000 employees)",
    "Large (1,001-5,000 employees)",
    "Enterprise (5,000+ employees)",
]

WORKSITE_OPTIONS = ["Local On-Site", "Local Hybrid", "National Remote"]

TRAILING_COMMA_PATTERN = re.compile(r",(\s*[\]}])")

SYSTEM_PROMPT = (
    "You are a job hunt strategist. Given a resume, target role, location, a "
    "preferred company size range, and a ranked worksite preference (most to "
    f"least preferred), use web_search to recommend EXACTLY {TARGET_COMPANY_COUNT} "
    "companies that are a strong fit for the candidate to target.\n\n"
    "This is NOT about finding a specific open job posting — do not include a "
    "hiring_signal or job posting URL. Use web_search sparingly, only to "
    "spot-check company-level signals (headcount trend, size, leadership "
    "stability) — you do not need to research every single candidate "
    f"exhaustively. Use up to {MAX_SEARCHES} searches total across all "
    f"{TARGET_COMPANY_COUNT} companies.\n\n"
    "Targeting criteria:\n"
    "- Role: match the target role, or a close director/leadership-level "
    "equivalent in the same function.\n"
    "- Worksite preference: the candidate ranked their worksite types from "
    "most to least preferred. Favor companies matching their higher-ranked "
    "types first, but fill out the full "
    f"{TARGET_COMPANY_COUNT} across all worksite types as needed rather than "
    "returning fewer companies. worksite_match must be exactly one of the "
    "ranked option strings you were given.\n"
    "- Company size: a soft preference for the given size range — not a "
    "hard filter. Companies outside the range can still be included if "
    "otherwise a strong fit, but prioritize matches.\n"
    "- Growth: prefer companies whose headcount appears to be increasing "
    "year-over-year for the past few years, based on best-effort public "
    "signals (LinkedIn headcount trends, news, funding announcements, etc).\n"
    "- Hard exclude: do not include any company where the CEO has changed "
    "more than twice in the past 10 years.\n\n"
    "For each company, return: company_name, size_estimate, worksite_match, "
    "growth_note (a brief best-effort note on headcount trend and any "
    "leadership-turnover signal you found — this is best-effort research, "
    "not guaranteed-accurate structured data, so do not present it as "
    "verified; use null if you found nothing to go on), fit_rationale (2 "
    f"sentences on why this company fits the resume and role). Return as a "
    f"JSON array of exactly {TARGET_COMPANY_COUNT} companies and nothing "
    "else — no prose, no clarifying questions."
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


def recommend_companies(
    resume: str,
    role: str,
    location: str,
    company_size: str,
    worksite_ranking: list,
) -> list:
    """Ask Claude to recommend TARGET_COMPANY_COUNT companies that fit the
    resume/role/location/preferences, using best-effort company-level
    research (headcount, size, leadership stability) — not a live-verified
    job posting per company like company_matcher.match_companies().

    worksite_ranking is a list of the 3 WORKSITE_OPTIONS strings, ordered
    from most to least preferred.

    Returns the parsed JSON array (list of dicts) from Claude's response.
    """
    claude = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
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

    ranking_text = " > ".join(worksite_ranking)
    user_message = (
        f"Resume:\n{resume}\n\n"
        f"Target role: {role}\n"
        f"Location: {location}\n"
        f"Preferred company size: {company_size}\n"
        f"Worksite preference (most to least preferred): {ranking_text}"
    )

    runner = claude.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        tools=[web_search],
        messages=[{"role": "user", "content": user_message}],
    )

    final_message = None
    for message in runner:
        final_message = message

    text = "".join(b.text for b in final_message.content if b.type == "text")
    return _parse_companies_json(text)


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
    sample_worksite_ranking = ["Local Hybrid", "Local On-Site", "National Remote"]

    companies = recommend_companies(
        sample_resume,
        sample_role,
        sample_location,
        sample_company_size,
        sample_worksite_ranking,
    )
    print(json.dumps(companies, indent=2))
