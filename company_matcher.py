import json
import os
import re

from anthropic import Anthropic, beta_tool
from dotenv import load_dotenv
from exa_py import Exa

load_dotenv(os.path.join(os.path.dirname(__file__), "aijobscout.env"))

MODEL = "claude-sonnet-5"
MAX_SEARCHES = 6

SYSTEM_PROMPT = (
    "You are a job hunt strategist. Given a resume, target role, and location, "
    "use web_search to find EXACTLY 5 companies that fit. For each: company_name, "
    "job_title (the specific open role title from the posting), size_estimate, "
    "location_match, hiring_signal (must be a real job posting URL — NEVER "
    "'probably hiring'), fit_rationale (2 sentences). Return as JSON array. "
    "Use max 6 searches. If uncertain, use null."
)


def _format_results(results):
    lines = [f"- {r.title} ({r.url}): {(r.highlights or [''])[0]}" for r in results]
    return "\n".join(lines) or "No results found."


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
            return "Search limit reached (6). Answer with what you already have."
        searches_used += 1
        result = exa.search(query, num_results=5, contents={"highlights": True})
        return _format_results(result.results)

    user_message = (
        f"Resume:\n{resume}\n\nTarget role: {role}\nLocation: {location}"
    )

    runner = claude.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        tools=[web_search],
        messages=[{"role": "user", "content": user_message}],
    )

    final_message = None
    for message in runner:
        final_message = message

    text = "".join(b.text for b in final_message.content if b.type == "text")
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON array found in Claude's response:\n{text}")

    return json.loads(match.group(0))


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
