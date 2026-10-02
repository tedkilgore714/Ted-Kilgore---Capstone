import os
import re
from datetime import date

import requests
from dotenv import load_dotenv
from exa_py import Exa
from anthropic import Anthropic
from composio import Composio

load_dotenv(os.path.join(os.path.dirname(__file__), "aijobscout.env"))

MY_ROLE = "Director of Professional Services"
MY_LOCATION = "Austin"

GMAIL_USER_ID = "pg-test-ee614ebd-aec6-462f-ba1c-0399d74feadd"
GMAIL_DRAFT_TOOL_VERSION = "20260702_01"
RECIPIENT_EMAIL = "aijobscout@gmail.com"  # send the digest to myself

CONFIG_JS_PATH = os.path.join(os.path.dirname(__file__), "config.js")


def read_supabase_config():
    text = open(CONFIG_JS_PATH).read()
    url = re.search(r"SUPABASE_URL\s*=\s*'([^']+)'", text).group(1)
    key = re.search(r"SUPABASE_ANON_KEY\s*=\s*'([^']+)'", text).group(1)
    return url, key


def fetch_active_companies():
    url, key = read_supabase_config()
    response = requests.get(
        f"{url}/rest/v1/target_companies",
        params={"select": "*", "active": "eq.true"},
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
    )
    response.raise_for_status()
    return response.json()


def search_company(exa, company_name):
    result = exa.search(
        f"{company_name} hiring 2026 {MY_ROLE}",
        num_results=5,
        contents={"highlights": True},
    )
    return result.results


def format_search_results(results):
    lines = []
    for r in results:
        highlight = (r.highlights or [""])[0]
        lines.append(f"- {r.title} ({r.url}): {highlight}")
    return "\n".join(lines)


def angle_for_company(claude, company_name, search_results):
    prompt = (
        f"I'm job hunting for {MY_ROLE} in {MY_LOCATION}. Here's what Exa "
        f"just found about {company_name}: {format_search_results(search_results)}. "
        f"Write ONE sentence about the SPECIFIC angle for this company — "
        f"cite something concrete from the results. Respond with only that "
        f"one sentence — no offers to help further, no follow-up questions, "
        f"no numbered lists."
    )
    response = claude.messages.create(
        model="claude-sonnet-5",
        max_tokens=300,
        thinking={"type": "disabled"},
        messages=[{"role": "user", "content": prompt}],
    )
    return next(b.text for b in response.content if b.type == "text")


def build_digest(angles):
    lines = [f"Today's shortlist — {date.today().isoformat()}", ""]
    for company_name, angle in angles:
        lines.append(f"{company_name}: {angle}")
    return "\n".join(lines)


def save_gmail_draft(digest_text):
    composio = Composio(api_key=os.environ["COMPOSIO_API_KEY"])
    composio.tools.execute(
        slug="GMAIL_CREATE_EMAIL_DRAFT",
        user_id=GMAIL_USER_ID,
        version=GMAIL_DRAFT_TOOL_VERSION,
        arguments={
            "recipient_email": RECIPIENT_EMAIL,
            "subject": f"Today's shortlist — {date.today().isoformat()}",
            "body": digest_text,
        },
    )


def main():
    exa = Exa(api_key=os.environ["EXA_API_KEY"])
    claude = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    angles = []
    for company in fetch_active_companies():
        name = company["name"]
        results = search_company(exa, name)
        angles.append((name, angle_for_company(claude, name, results)))

    digest = build_digest(angles)
    save_gmail_draft(digest)
    print(digest)


if __name__ == "__main__":
    main()
