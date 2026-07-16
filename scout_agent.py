"""Weekly personal scout agent.

For each interest category, searches Exa for genuinely current items, judges
each batch of results with Claude, and keeps looping with a new search angle
until the category has 2-3 solid items or the shared search budget runs out.
Prints an observe/think/act/check panel for every iteration, then emails one
digest via the connected Composio Gmail account.

Tools: Exa search, Composio Gmail. Nothing else.
"""

import json
import os
from datetime import date, timedelta

from anthropic import Anthropic
from composio import Composio
from dotenv import load_dotenv
from exa_py import Exa
from rich.console import Console
from rich.panel import Panel

load_dotenv(os.path.join(os.path.dirname(__file__), "aijobscout.env"))

MODEL = "claude-sonnet-5"

GMAIL_USER_ID = "pg-test-ee614ebd-aec6-462f-ba1c-0399d74feadd"
GMAIL_TOOL_VERSION = "20260702_01"
RECIPIENT_EMAIL = "tedkilgore714@gmail.com"

MAX_TOTAL_SEARCHES = 8
MIN_ITEMS_PER_CATEGORY = 2
MAX_ITEMS_PER_CATEGORY = 3
RESULTS_PER_SEARCH = 6

INTERESTS = [
    {
        "name": "Professional Networking",
        "brief": (
            "Networking opportunities for a Director of Professional Services / "
            "Customer Success leader in B2B SaaS, based in Austin, TX -- "
            "industry meetups, association events, mixers, panels, or "
            "conferences that this person could actually attend: either "
            "physically in or near Austin, or genuinely virtual/online "
            "(livestreamed or remote-attendable). Reject events that require "
            "travel to another city/country and aren't virtual. Not generic "
            "'networking tips' articles."
        ),
    },
    {
        "name": "AI News",
        "brief": (
            "Genuinely new, significant AI industry news from the last few "
            "days -- model releases, major product launches, notable research "
            "results, or acquisitions. Not evergreen explainers, not generic "
            "'top AI tools' listicles."
        ),
    },
    {
        "name": "Austin Area In-Person Events",
        "brief": (
            "Real in-person events happening in Austin, TX this coming week -- "
            "tech meetups, conferences, talks, community gatherings. Must be "
            "physically in Austin, not virtual, not another city."
        ),
    },
]

PANEL_COLORS = {"observe": "cyan", "think": "yellow", "act": "blue", "check": "green"}

PROPOSE_QUERY_TOOL = {
    "name": "propose_search",
    "description": (
        "Propose the next Exa search query for this category, plus a one "
        "sentence reason for the angle. Must be meaningfully different from "
        "any query already tried for this category."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The exact search query to run."},
            "reasoning": {"type": "string", "description": "One sentence: why this angle."},
        },
        "required": ["query", "reasoning"],
    },
}

JUDGE_RESULTS_TOOL = {
    "name": "judge_results",
    "description": "Judge each search result against the category's criteria.",
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer", "description": "1-based index of the result being judged."},
                        "keep": {"type": "boolean"},
                        "date_text": {
                            "type": "string",
                            "description": "The concrete date/time found for this item, or empty string if none.",
                        },
                        "reason": {
                            "type": "string",
                            "description": (
                                "One short, complete, finished sentence stating why kept or "
                                "rejected. No meta-commentary, no trailing 'check this' or "
                                "unfinished thoughts -- this text is shown to the end user "
                                "verbatim."
                            ),
                        },
                    },
                    "required": ["index", "keep", "reason"],
                },
            }
        },
        "required": ["items"],
    },
}


class CategoryState:
    def __init__(self, name: str, brief: str):
        self.name = name
        self.brief = brief
        self.items = []  # list of dicts: title, url, date_text, note
        self.tried_queries = []
        self.searches_done = 0

    @property
    def satisfied(self) -> bool:
        return len(self.items) >= MIN_ITEMS_PER_CATEGORY

    @property
    def full(self) -> bool:
        return len(self.items) >= MAX_ITEMS_PER_CATEGORY


def panel(console: Console, stage: str, title: str, body: str) -> None:
    console.print(Panel(body, title=f"[{stage.upper()}] {title}", border_style=PANEL_COLORS[stage], expand=True))


def propose_query(claude: Anthropic, state: CategoryState, today_str: str, week_end_str: str) -> tuple:
    tried = "\n".join(f"- {q}" for q in state.tried_queries) or "(none yet)"
    kept = "\n".join(f"- {i['title']}" for i in state.items) or "(none yet)"
    prompt = (
        f"Today is {today_str}. We're building a weekly digest and want items "
        f"dated between today and {week_end_str} (or newly opened/announced).\n\n"
        f"Category: {state.name}\n"
        f"What counts: {state.brief}\n\n"
        f"Queries already tried for this category (do NOT repeat or lightly "
        f"reword these -- pick a genuinely different angle):\n{tried}\n\n"
        f"Items already kept for this category:\n{kept}\n\n"
        f"Propose ONE new Exa search query likely to surface real, dated, "
        f"specific items for this category."
    )
    response = claude.messages.create(
        model=MODEL,
        max_tokens=400,
        thinking={"type": "disabled"},
        tools=[PROPOSE_QUERY_TOOL],
        tool_choice={"type": "tool", "name": "propose_search"},
        messages=[{"role": "user", "content": prompt}],
    )
    tool_use = next(b for b in response.content if b.type == "tool_use")
    return tool_use.input["query"], tool_use.input.get("reasoning", "")


def run_search(exa: Exa, query: str) -> list:
    result = exa.search(
        query,
        num_results=RESULTS_PER_SEARCH,
        contents={"text": {"maxCharacters": 500}, "highlights": True},
    )
    return result.results


def format_results_for_judging(results: list) -> str:
    lines = []
    for i, r in enumerate(results, 1):
        highlight = (r.highlights or [""])[0]
        snippet = highlight or (r.text or "")[:300]
        lines.append(
            f"{i}. {r.title}\n   url: {r.url}\n   published: {r.published_date or 'unknown'}\n   text: {snippet}"
        )
    return "\n".join(lines)


def judge_results(
    claude: Anthropic, state: CategoryState, results: list, today_str: str, week_end_str: str
) -> dict:
    if not results:
        return {"items": []}
    prompt = (
        f"Today is {today_str}. We want items dated between today and "
        f"{week_end_str} (or newly opened/announced), matching this category:\n\n"
        f"Category: {state.name}\n"
        f"What counts: {state.brief}\n\n"
        f"Judge each result strictly. Reject anything that: is not actually "
        f"dated this coming week (unless it's a newly-opened/newly-announced "
        f"item where no future date applies), is not actually in the right "
        f"place/topic, or reads like a generic evergreen listicle rather than "
        f"a real, specific, current item.\n\n"
        f"Results:\n{format_results_for_judging(results)}"
    )
    response = claude.messages.create(
        model=MODEL,
        max_tokens=1200,
        thinking={"type": "disabled"},
        tools=[JUDGE_RESULTS_TOOL],
        tool_choice={"type": "tool", "name": "judge_results"},
        messages=[{"role": "user", "content": prompt}],
    )
    tool_use = next(b for b in response.content if b.type == "tool_use")
    return tool_use.input


def format_state_summary(states: list, total_searches: int) -> str:
    lines = [f"Search budget used: {total_searches}/{MAX_TOTAL_SEARCHES}", ""]
    for s in states:
        status = "satisfied" if s.satisfied else "thin"
        lines.append(f"- {s.name}: {len(s.items)} kept ({status}, {s.searches_done} searches so far)")
    return "\n".join(lines)


def scout(console: Console) -> list:
    claude = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    exa = Exa(api_key=os.environ["EXA_API_KEY"])

    today = date.today()
    today_str = today.isoformat()
    week_end_str = (today + timedelta(days=9)).isoformat()

    states = [CategoryState(i["name"], i["brief"]) for i in INTERESTS]
    total_searches = 0

    while total_searches < MAX_TOTAL_SEARCHES:
        candidates = [s for s in states if not s.full]
        if not candidates:
            break
        if all(s.satisfied for s in candidates):
            break
        # work the least-searched unsatisfied category first, for fair allocation
        unsatisfied = [s for s in candidates if not s.satisfied] or candidates
        state = min(unsatisfied, key=lambda s: s.searches_done)

        iteration = state.searches_done + 1
        total_searches += 1

        panel(
            console,
            "observe",
            state.name,
            format_state_summary(states, total_searches - 1) + f"\n\nWorking on: {state.name} (iteration {iteration})",
        )

        try:
            query, reasoning = propose_query(claude, state, today_str, week_end_str)
        except Exception as e:
            panel(console, "think", state.name, f"error proposing query: {e} -- skipping this round")
            state.searches_done += 1
            continue

        state.tried_queries.append(query)
        panel(console, "think", state.name, f'Next query: "{query}"\n\nWhy: {reasoning}')

        try:
            results = run_search(exa, query)
        except Exception as e:
            panel(console, "act", state.name, f"Exa search failed: {e}")
            state.searches_done += 1
            continue

        act_body = f"Exa returned {len(results)} result(s):\n\n" + (
            "\n".join(f"- {r.title} ({r.url})" for r in results) or "(none)"
        )
        panel(console, "act", state.name, act_body)

        try:
            judged = judge_results(claude, state, results, today_str, week_end_str)
        except Exception as e:
            panel(console, "check", state.name, f"error judging results: {e}")
            state.searches_done += 1
            continue

        results_by_index = {i: r for i, r in enumerate(results, 1)}
        check_lines = []
        newly_kept = 0
        for item in judged.get("items", []):
            idx = item.get("index")
            r = results_by_index.get(idx)
            if r is None:
                continue
            verdict = "KEEP" if item.get("keep") else "reject"
            check_lines.append(f"[{verdict}] {r.title} -- {item.get('reason', '')}")
            if item.get("keep") and len(state.items) < MAX_ITEMS_PER_CATEGORY:
                state.items.append(
                    {
                        "title": r.title,
                        "url": r.url,
                        "date_text": item.get("date_text") or (r.published_date or ""),
                        "note": item.get("reason", ""),
                    }
                )
                newly_kept += 1

        check_body = "\n".join(check_lines) or "(no items to judge)"
        check_body += f"\n\nKept {newly_kept} new item(s). Category now has {len(state.items)}/{MAX_ITEMS_PER_CATEGORY}."
        panel(console, "check", state.name, check_body)

        state.searches_done += 1

    panel(console, "observe", "Final state", format_state_summary(states, total_searches))
    return states


def build_email_body(states: list, today_str: str) -> str:
    lines = [f"Hey Ted -- here's what's worth a look this week ({today_str}):", ""]
    for state in states:
        lines.append(f"== {state.name} ==")
        if not state.items:
            lines.append("(nothing solid turned up this week -- came up thin despite multiple search angles)")
        else:
            if len(state.items) < MIN_ITEMS_PER_CATEGORY:
                lines.append(f"(only found {len(state.items)} -- thin week for this one, but here's what's real)")
            for item in state.items:
                date_part = f" ({item['date_text']})" if item["date_text"] else ""
                lines.append(f"- {item['title']}{date_part}")
                lines.append(f"  {item['url']}")
                if item["note"]:
                    lines.append(f"  why: {item['note']}")
        lines.append("")
    lines.append("-- your weekly scout")
    return "\n".join(lines)


def send_digest_email(states: list, today_str: str) -> None:
    composio = Composio(api_key=os.environ["COMPOSIO_API_KEY"])
    composio.tools.execute(
        slug="GMAIL_SEND_EMAIL",
        user_id=GMAIL_USER_ID,
        version=GMAIL_TOOL_VERSION,
        arguments={
            "recipient_email": RECIPIENT_EMAIL,
            "subject": f"Your weekly scout -- {today_str}",
            "body": build_email_body(states, today_str),
        },
    )


def main() -> None:
    console = Console()
    states = scout(console)

    today_str = date.today().isoformat()
    body = build_email_body(states, today_str)
    console.print(Panel(body, title="DIGEST", border_style="magenta", expand=True))

    try:
        send_digest_email(states, today_str)
        console.print(f"\n[bold green]done:[/bold green] digest emailed to {RECIPIENT_EMAIL}")
    except Exception as e:
        console.print(f"\n[bold red]done:[/bold red] digest built, but email send failed ({e})")


if __name__ == "__main__":
    main()
