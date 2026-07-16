import json
import os
import re
from datetime import date

from anthropic import Anthropic
from composio import Composio
from dotenv import load_dotenv
from supabase import create_client

from company_recommender import recommend_companies

load_dotenv(os.path.join(os.path.dirname(__file__), "aijobscout.env"))

CONFIG_JS_PATH = os.path.join(os.path.dirname(__file__), "config.js")

MODEL = "claude-sonnet-5"
TARGET_COUNT = 30

# company_recommender.py already returns ~TARGET_COUNT companies in a
# single call (no live-posting verification to cause shortfalls), so this
# only needs to cover the rare case of a top-up round after heavy overlap
# with companies already saved from a prior run — not a long grind.
MAX_TOOL_CALLS = 5

GMAIL_USER_ID = "pg-test-ee614ebd-aec6-462f-ba1c-0399d74feadd"
GMAIL_TOOL_VERSION = "20260702_01"
RECIPIENT_EMAIL = "tedkilgore714@gmail.com"

SEARCH_COMPANIES_TOOL = {
    "name": "search_companies",
    "description": (
        "Search for candidate companies matching the resume/role/location/"
        "preferences, using a specific angle or steering hint (an industry, "
        "growth stage, or segment not yet explored). Returns fit-matched "
        "companies from best-effort research — not verified job postings. "
        "Use the angle to steer toward genuinely different companies than "
        "previous calls."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "angle": {
                "type": "string",
                "description": (
                    "A specific, narrow search angle for this round — e.g. "
                    "'healthcare companies', 'sub-100-employee startups', "
                    "'companies outside the primary metro area'. Should be "
                    "meaningfully different from angles already tried."
                ),
            }
        },
        "required": ["angle"],
    },
}

ANGLE_SYSTEM_PROMPT = (
    "You are planning a company search strategy for a job seeker's "
    "shortlist. You have one tool, search_companies, which runs a company "
    "search for a given angle and returns fit-matched results. Each turn, "
    "propose ONE new search angle and call the tool with it. Vary industry, "
    "company stage, and segment across turns rather than repeating similar "
    "angles — you'll be told which companies are already saved so you don't "
    "re-suggest them."
)

RANK_SYSTEM_PROMPT = (
    "You are ranking a shortlist of candidate companies for a job seeker, "
    "best fit first, based on their resume and each company's fit "
    "rationale. Return ONLY a JSON array of company names in ranked order "
    "(best fit first) — no prose, no markdown, using the exact company_name "
    "values given."
)


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(
            f"Missing required environment variable: {name}. Add it to "
            f"aijobscout.env before running shortlist_agent.py."
        )
    return value


def _require_env_any(*names: str) -> str:
    """Like _require_env, but accepts any of several possible names for the
    same secret. Local aijobscout.env and Render currently use different
    names for the Supabase service-role-equivalent key
    (SUPABASE_SERVICE_ROLE_KEY vs SUPABASE_SECRET_KEY) — this avoids the
    two environments needing to agree on one name."""
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    raise SystemExit(
        f"Missing required environment variable (tried: {', '.join(names)}). "
        f"Add one of these before running shortlist_agent.py."
    )


def _get_supabase_url() -> str:
    """SUPABASE_URL isn't set as an env var on Render — like daily_digest.py,
    read it out of config.js instead, which is deployed with the rest of
    the repo. Falls back to the env var if config.js doesn't have it."""
    try:
        text = open(CONFIG_JS_PATH).read()
        match = re.search(r"SUPABASE_URL\s*=\s*'([^']+)'", text)
        if match:
            return match.group(1)
    except FileNotFoundError:
        pass
    return _require_env("SUPABASE_URL")


def get_supabase_client():
    """Shared connection helper — used by build_shortlist() below and by
    main.py's /candidates endpoint, so both resolve the URL/key the same
    way instead of duplicating the env-var/config.js fallback logic."""
    supabase_key = _require_env_any("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEY")
    return create_client(_get_supabase_url(), supabase_key)


def _dedupe_key(name: str) -> str:
    return name.strip().lower()


def _fetch_existing_candidates(supabase, role: str, location: str, company_size: str, include_remote: bool) -> list:
    """Candidates are scoped to the exact search that found them, so a
    different role/location/etc. starts its own independent shortlist
    instead of colliding with — or being blocked by — an unrelated one."""
    response = (
        supabase.table("candidates")
        .select("*")
        .eq("role", role)
        .eq("location", location)
        .eq("company_size", company_size)
        .eq("include_remote", include_remote)
        .order("rank")
        .execute()
    )
    return response.data or []


def _save_new_candidates(
    supabase,
    companies: list,
    seen_keys: set,
    role: str,
    location: str,
    company_size: str,
    include_remote: bool,
) -> list:
    """Insert companies not already in seen_keys. Returns the newly inserted rows (with their DB ids)."""
    rows_to_insert = []
    for c in companies:
        name = c.get("company_name")
        if not name:
            continue
        key = _dedupe_key(name)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        rows_to_insert.append(
            {
                "company_name": name,
                "size_estimate": c.get("size_estimate"),
                "location_match": c.get("location_match"),
                "growth_note": c.get("growth_note"),
                "fit_rationale": c.get("fit_rationale"),
                "role": role,
                "location": location,
                "company_size": company_size,
                "include_remote": include_remote,
            }
        )
    if not rows_to_insert:
        return []
    response = supabase.table("candidates").insert(rows_to_insert).execute()
    return response.data or []


def _pick_next_angle(claude, messages: list) -> tuple:
    """Ask Claude for the next search angle via a forced tool call.

    Returns (angle, tool_use_id, assistant_content) so the caller can
    append both the assistant turn and the eventual tool_result.
    """
    response = claude.messages.create(
        model=MODEL,
        max_tokens=500,
        thinking={"type": "disabled"},
        system=ANGLE_SYSTEM_PROMPT,
        tools=[SEARCH_COMPANIES_TOOL],
        tool_choice={"type": "tool", "name": "search_companies"},
        messages=messages,
    )
    tool_use = next(b for b in response.content if b.type == "tool_use")
    return tool_use.input.get("angle", ""), tool_use.id, response.content


def _rank_by_fit(claude, resume: str, role: str, rows: list) -> list:
    """Ask Claude to rank the full saved set by fit, best first. Falls back
    to the existing order if ranking fails for any reason — dedupe/save
    already happened, ranking is a nice-to-have on top."""
    if not rows:
        return rows
    summaries = [
        {"company_name": r["company_name"], "fit_rationale": r.get("fit_rationale")}
        for r in rows
    ]
    try:
        response = claude.messages.create(
            model=MODEL,
            max_tokens=4000,
            thinking={"type": "disabled"},
            system=RANK_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Resume:\n{resume}\n\nTarget role: {role}\n\n"
                        f"Companies:\n{json.dumps(summaries, indent=2)}"
                    ),
                }
            ],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        ranked_names = json.loads(text[text.index("[") : text.rindex("]") + 1])
    except Exception as e:
        print(f"warning: ranking failed ({e}); keeping insertion order", flush=True)
        return rows

    by_key = {_dedupe_key(r["company_name"]): r for r in rows}
    ranked_rows = [by_key.pop(_dedupe_key(name)) for name in ranked_names if _dedupe_key(name) in by_key]
    ranked_rows.extend(by_key.values())  # anything Claude dropped, keep at the end
    return ranked_rows


def _persist_ranks(supabase, ranked_rows: list) -> None:
    for i, row in enumerate(ranked_rows, 1):
        if row.get("id"):
            supabase.table("candidates").update({"rank": i}).eq("id", row["id"]).execute()


def _build_digest(ranked_rows: list) -> str:
    lines = [f"Job Scout Shortlist — {len(ranked_rows)} companies ({date.today().isoformat()})", ""]
    for i, row in enumerate(ranked_rows, 1):
        lines.append(f"{i}. {row['company_name']} — {row.get('fit_rationale', '')}")
    return "\n".join(lines)


def _send_digest_email(ranked_rows: list) -> None:
    composio = Composio(api_key=os.environ["COMPOSIO_API_KEY"])
    composio.tools.execute(
        slug="GMAIL_SEND_EMAIL",
        user_id=GMAIL_USER_ID,
        version=GMAIL_TOOL_VERSION,
        arguments={
            "recipient_email": RECIPIENT_EMAIL,
            "subject": f"Job Scout Shortlist — {len(ranked_rows)} companies ({date.today().isoformat()})",
            "body": _build_digest(ranked_rows),
        },
    )


def build_shortlist(
    resume: str,
    role: str,
    location: str,
    company_size: str,
    include_remote: bool,
) -> list:
    """Build a shortlist of TARGET_COUNT unique companies via
    company_recommender.recommend_companies (fit-matched, best-effort
    research — no live job-posting verification), saving each to Supabase
    as found, then rank by fit and email a digest. Observe/Think/Act/Check
    loop, capped at MAX_TOOL_CALLS — expected to need only 1-2 calls since
    a single recommend_companies() call already targets ~TARGET_COUNT.
    """
    anthropic_key = _require_env("ANTHROPIC_API_KEY")
    _require_env("COMPOSIO_API_KEY")

    claude = Anthropic(api_key=anthropic_key, timeout=600.0)
    supabase = get_supabase_client()

    existing = _fetch_existing_candidates(supabase, role, location, company_size, include_remote)
    seen_keys = {_dedupe_key(row["company_name"]) for row in existing}
    all_saved = list(existing)

    messages = [
        {
            "role": "user",
            "content": (
                f"Resume:\n{resume}\n\nTarget role: {role}\nLocation: {location}\n\n"
                f"Build a shortlist of {TARGET_COUNT} unique target companies using "
                f"the search_companies tool. Currently {len(seen_keys)} of "
                f"{TARGET_COUNT} saved."
            ),
        }
    ]

    for iteration in range(1, MAX_TOOL_CALLS + 1):
        print(f"[iteration {iteration}] observe: {len(seen_keys)} of {TARGET_COUNT} candidates saved", flush=True)

        if len(seen_keys) >= TARGET_COUNT:
            print(f"[iteration {iteration}] check: {len(seen_keys)} of {TARGET_COUNT} saved? yes — stopping", flush=True)
            break

        try:
            angle, tool_use_id, assistant_content = _pick_next_angle(claude, messages)
        except Exception as e:
            print(f"[iteration {iteration}] error: failed to get next angle from Claude ({e}) — stopping", flush=True)
            break

        print(f'[iteration {iteration}] think: next angle — "{angle}"', flush=True)
        messages.append({"role": "assistant", "content": assistant_content})

        print(f'[iteration {iteration}] act: calling CompanyRecommender with angle "{angle}"', flush=True)
        already_seen_names = [row["company_name"] for row in all_saved]
        try:
            companies = recommend_companies(
                resume,
                role,
                location,
                company_size,
                include_remote,
                angle=angle,
                already_seen=already_seen_names,
            )
        except Exception as e:
            print(f"[iteration {iteration}] error: CompanyRecommender call failed ({e})", flush=True)
            companies = []

        new_rows = _save_new_candidates(supabase, companies, seen_keys, role, location, company_size, include_remote)
        all_saved.extend(new_rows)
        print(
            f"[iteration {iteration}] act: CompanyRecommender returned {len(companies)} "
            f"companies, {len(new_rows)} new",
            flush=True,
        )

        done = len(seen_keys) >= TARGET_COUNT
        print(
            f"[iteration {iteration}] check: {len(seen_keys)} of {TARGET_COUNT} saved? "
            f"{'yes' if done else 'no'} — {'stopping' if done else 'looping'}",
            flush=True,
        )

        if done:
            break

        progress_text = (
            f"Saved {len(new_rows)} new unique companies this round. Total: "
            f"{len(seen_keys)} of {TARGET_COUNT}. Keep going with a new, "
            f"genuinely different angle."
        )
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": tool_use_id, "content": progress_text}
                ],
            }
        )
    else:
        print(
            f"stopping: reached max tool calls ({MAX_TOOL_CALLS}) with "
            f"{len(seen_keys)} of {TARGET_COUNT} saved",
            flush=True,
        )

    ranked_rows = _rank_by_fit(claude, resume, role, all_saved)
    _persist_ranks(supabase, ranked_rows)

    try:
        _send_digest_email(ranked_rows)
        print(f"\ndone: {len(ranked_rows)} unique candidates saved and emailed to {RECIPIENT_EMAIL}", flush=True)
    except Exception as e:
        print(f"\ndone: {len(ranked_rows)} unique candidates saved, but digest email failed ({e})", flush=True)

    return ranked_rows


if __name__ == "__main__":
    sample_resume = (
        "Ted Kilgore — Director of Professional Services. 10+ years leading "
        "post-sales, onboarding, and customer success teams at B2B SaaS "
        "companies. Built and scaled PS orgs from 3 to 20+ people, owns "
        "renewal/expansion targets, background in implementation consulting."
    )
    sample_role = "Director of Professional Services"
    sample_location = "Austin, TX"
    sample_company_size = "Mid-size (201-1,000 employees)"
    sample_include_remote = True

    build_shortlist(
        sample_resume,
        sample_role,
        sample_location,
        sample_company_size,
        sample_include_remote,
    )
