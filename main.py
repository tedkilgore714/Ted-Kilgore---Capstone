from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from company_matcher import match_companies
from company_recommender import (
    COMPANY_SIZE_OPTIONS,
    LOCAL_RADIUS_MILES,
    TARGET_COMPANY_COUNT,
    recommend_companies,
)
from shortlist_agent import build_replacement, build_shortlist, get_supabase_client, reject_candidate

app = FastAPI(title="AI Job Scout — Company Matcher")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_current_user(authorization: str = Header(None)) -> dict | None:
    """Phase 2 of the real-per-user-accounts rollout (see
    user_accounts_phase1.sql) -- optional for now. Returns None (not an
    error) when no/invalid Authorization is given, so every caller of this
    can keep working unauthenticated during the dual-path window; Phase 5
    is what makes this required. Validates the token against Supabase's
    Auth server directly (supabase-py's auth.get_user) rather than adding
    a JWT-decoding dependency -- fine at this traffic level.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ")
    try:
        resp = get_supabase_client().auth.get_user(token)
    except Exception:
        return None
    if not resp or not resp.user:
        return None
    return {"id": resp.user.id, "email": resp.user.email}


class MatchRequest(BaseModel):
    resume: str
    role: str
    location: str


@app.post("/matcher")
def matcher(request: MatchRequest):
    try:
        return match_companies(request.resume, request.role, request.location)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


class RecommendRequest(BaseModel):
    resume: str
    role: str
    location: str
    company_size: str
    include_remote: bool


@app.post("/recommend")
def recommend(request: RecommendRequest):
    try:
        return recommend_companies(
            request.resume,
            request.role,
            request.location,
            request.company_size,
            request.include_remote,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


class ShortlistRequest(BaseModel):
    resume: str
    role: str
    location: str
    company_size: str
    include_remote: bool
    email: str


def _run_shortlist_job(resume: str, role: str, location: str, company_size: str, include_remote: bool, email: str, user_id: str = None) -> None:
    """Runs in the background after /shortlist responds. Errors are logged
    server-side (visible in Render logs) rather than raised — the client
    already got its "started" response, and a failure here just means the
    digest email won't arrive."""
    try:
        build_shortlist(resume, role, location, company_size, include_remote, email, user_id=user_id)
    except Exception as e:
        print(f"[/shortlist background job] failed: {e}", flush=True)


@app.post("/shortlist")
def shortlist(request: ShortlistRequest, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)):
    # Dual-path (Phase 2 of the accounts rollout): a verified session's
    # email always wins over whatever the client typed in the request body,
    # since only the former is actually backed by anything -- but the
    # client-supplied email keeps working when there's no session yet, so
    # this doesn't break anything ahead of the frontend shipping auth.
    recipient_email = user["email"] if user else request.email
    background_tasks.add_task(
        _run_shortlist_job,
        request.resume,
        request.role,
        request.location,
        request.company_size,
        request.include_remote,
        recipient_email,
        user["id"] if user else None,
    )
    return {
        "status": "started",
        "message": f"Shortlist search started — this takes about 5-10 minutes. Results will be emailed to {recipient_email} when it's done, or view /candidates-demo.",
    }


@app.get("/candidates")
def candidates(
    email: str = None,
    role: str = None,
    location: str = None,
    company_size: str = None,
    include_remote: bool = None,
    user: dict = Depends(get_current_user),
):
    supabase = get_supabase_client()
    query = supabase.table("candidates").select("*")
    # A verified session scopes strictly to that user's own rows, ignoring
    # any client-supplied email entirely -- that's the actual fix for
    # "anyone can read anyone's shortlist by passing an arbitrary email".
    # Only falls back to the old unverified email filter when there's no
    # session at all, so this stays a no-op change until the frontend
    # actually starts sending a session.
    if user is not None:
        query = query.eq("user_id", user["id"])
    elif email is not None:
        query = query.eq("email", email)
    if role is not None:
        query = query.eq("role", role)
    if location is not None:
        query = query.eq("location", location)
    if company_size is not None:
        query = query.eq("company_size", company_size)
    if include_remote is not None:
        query = query.eq("include_remote", include_remote)
    response = query.order("role").order("location").order("rank").execute()
    return response.data or []


class RejectRequest(BaseModel):
    candidate_id: str


@app.post("/reject")
def reject(request: RejectRequest, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)):
    try:
        row = reject_candidate(request.candidate_id, user_id=user["id"] if user else None)
    except ValueError as e:
        status_code = 404 if str(e) == "Company not found." else 403
        raise HTTPException(status_code=status_code, detail=str(e))
    background_tasks.add_task(build_replacement, row)
    return {
        "status": "rejected",
        "message": "Rejected. Finding a replacement — check back in a minute or two.",
    }


DEMO_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>AI Job Scout — Company Matcher</title>
<style>
  :root { color-scheme: light dark; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    max-width: 900px;
    margin: 2rem auto;
    padding: 0 1.5rem;
    line-height: 1.5;
  }
  h1 { font-size: 1.5rem; }
  label { display: block; font-weight: 600; margin-top: 1rem; margin-bottom: 0.25rem; }
  textarea, input {
    width: 100%;
    box-sizing: border-box;
    padding: 0.5rem;
    font-family: inherit;
    font-size: 1rem;
    border: 1px solid #999;
    border-radius: 6px;
  }
  textarea { min-height: 140px; resize: vertical; }
  button {
    margin-top: 1.25rem;
    padding: 0.65rem 1.25rem;
    font-size: 1rem;
    font-weight: 600;
    border: none;
    border-radius: 6px;
    background: #2563eb;
    color: white;
    cursor: pointer;
  }
  button:disabled { opacity: 0.6; cursor: not-allowed; }
  #status { margin-top: 1rem; font-style: italic; }
  #results {
    margin-top: 2rem;
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 1rem;
  }
  @media (max-width: 600px) {
    #results { grid-template-columns: 1fr; }
  }
  .card {
    border: 1px solid #ccc;
    border-radius: 8px;
    padding: 1rem;
    min-width: 0;
    overflow-wrap: break-word;
  }
  .card h3 { margin: 0 0 0.5rem; overflow-wrap: break-word; }
  .card dl { margin: 0; }
  .card dt { font-weight: 600; font-size: 0.85rem; margin-top: 0.5rem; }
  .card dd {
    margin: 0;
    overflow-wrap: anywhere;
    word-break: break-word;
  }
  .card dd a { overflow-wrap: anywhere; word-break: break-word; }
  .missing { color: #888; font-style: italic; }
  #json-details {
    margin-top: 1.5rem;
    border: 1px solid #ccc;
    border-radius: 8px;
    padding: 0.75rem 1rem;
  }
  #json-details summary {
    cursor: pointer;
    font-weight: 600;
  }
  #json-output {
    margin: 0.75rem 0 0;
    padding: 0.75rem;
    background: rgba(127, 127, 127, 0.1);
    border-radius: 6px;
    font-size: 0.85rem;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    max-height: 400px;
    overflow-y: auto;
  }
</style>
</head>
<body>
  <h1>AI Job Scout — Company Matcher</h1>

  <label for="resume">Resume</label>
  <textarea id="resume" placeholder="Paste your resume here..."></textarea>

  <label for="role">Target role</label>
  <input id="role" type="text" placeholder="e.g. Director of Professional Services">

  <label for="location">Location</label>
  <input id="location" type="text" placeholder="e.g. Austin, TX (hybrid preferred)">

  <button id="submit-btn">Find matching companies →</button>
  <div id="status"></div>
  <div id="results"></div>

  <details id="json-details" style="display: none;">
    <summary>Show JSON</summary>
    <pre id="json-output"></pre>
  </details>

<script>
const NOT_ENOUGH_EVIDENCE = "— not enough evidence to say —";

function field(value) {
  return (value === null || value === undefined || value === "")
    ? NOT_ENOUGH_EVIDENCE
    : value;
}

function renderCard(company) {
  const card = document.createElement("div");
  card.className = "card";

  const hiringSignal = company.hiring_signal
    ? `<a href="${company.hiring_signal}" target="_blank" rel="noopener noreferrer">${company.job_title || "View posting"}</a>`
    : `<span class="missing">${NOT_ENOUGH_EVIDENCE}</span>`;

  card.innerHTML = `
    <h3>${field(company.company_name)}</h3>
    <dl>
      <dt>Size Estimate</dt>
      <dd>${field(company.size_estimate)}</dd>
      <dt>Location Match</dt>
      <dd>${field(company.location_match)}</dd>
      <dt>Hiring Signal</dt>
      <dd>${hiringSignal}</dd>
      <dt>Fit Rationale</dt>
      <dd>${field(company.fit_rationale)}</dd>
    </dl>
  `;
  return card;
}

document.getElementById("submit-btn").addEventListener("click", async () => {
  const resume = document.getElementById("resume").value;
  const role = document.getElementById("role").value;
  const location = document.getElementById("location").value;

  const statusEl = document.getElementById("status");
  const resultsEl = document.getElementById("results");
  const btn = document.getElementById("submit-btn");
  const jsonDetailsEl = document.getElementById("json-details");
  const jsonOutputEl = document.getElementById("json-output");

  resultsEl.innerHTML = "";
  jsonDetailsEl.style.display = "none";
  jsonDetailsEl.open = false;
  statusEl.textContent = "Searching...";
  btn.disabled = true;

  try {
    const response = await fetch("/matcher", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resume, role, location }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || `Request failed (${response.status})`);
    }

    const companies = await response.json();
    statusEl.textContent = "";
    companies.forEach((company) => resultsEl.appendChild(renderCard(company)));

    jsonOutputEl.textContent = JSON.stringify(companies, null, 2);
    jsonDetailsEl.style.display = "block";
  } catch (err) {
    statusEl.textContent = `Error: ${err.message}`;
  } finally {
    btn.disabled = false;
  }
});
</script>
</body>
</html>
"""


@app.get("/demo", response_class=HTMLResponse)
def demo():
    return DEMO_HTML


_COMPANY_SIZE_OPTIONS_HTML = "\n".join(
    f'<option value="{opt}">{opt}</option>' for opt in COMPANY_SIZE_OPTIONS
)

RECOMMEND_DEMO_HTML = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>AI Job Scout — Company Recommender</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    max-width: 900px;
    margin: 2rem auto;
    padding: 0 1.5rem;
    line-height: 1.5;
  }}
  h1 {{ font-size: 1.5rem; }}
  label {{ display: block; font-weight: 600; margin-top: 1rem; margin-bottom: 0.25rem; }}
  textarea, input, select {{
    width: 100%;
    box-sizing: border-box;
    padding: 0.5rem;
    font-family: inherit;
    font-size: 1rem;
    border: 1px solid #999;
    border-radius: 6px;
    background: Field;
    color: FieldText;
  }}
  textarea {{ min-height: 140px; resize: vertical; }}
  .checkbox-row {{
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-top: 1rem;
  }}
  .checkbox-row input {{ width: auto; }}
  .checkbox-row label {{ font-weight: 400; margin: 0; }}
  button {{
    margin-top: 1.25rem;
    padding: 0.65rem 1.25rem;
    font-size: 1rem;
    font-weight: 600;
    border: none;
    border-radius: 6px;
    background: #2563eb;
    color: white;
    cursor: pointer;
  }}
  button:disabled {{ opacity: 0.6; cursor: not-allowed; }}
  #status {{ margin-top: 1rem; font-style: italic; }}
  #results {{
    margin-top: 2rem;
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 1rem;
  }}
  @media (max-width: 600px) {{
    #results {{ grid-template-columns: 1fr; }}
  }}
  .card {{
    border: 1px solid #ccc;
    border-radius: 8px;
    padding: 1rem;
    min-width: 0;
    overflow-wrap: break-word;
  }}
  .card h3 {{ margin: 0 0 0.5rem; overflow-wrap: break-word; }}
  .card dl {{ margin: 0; }}
  .card dt {{ font-weight: 600; font-size: 0.85rem; margin-top: 0.5rem; }}
  .card dd {{
    margin: 0;
    overflow-wrap: anywhere;
    word-break: break-word;
  }}
  .missing {{ color: #888; font-style: italic; }}
  #json-details {{
    margin-top: 1.5rem;
    border: 1px solid #ccc;
    border-radius: 8px;
    padding: 0.75rem 1rem;
  }}
  #json-details summary {{ cursor: pointer; font-weight: 600; }}
  #json-output {{
    margin: 0.75rem 0 0;
    padding: 0.75rem;
    background: rgba(127, 127, 127, 0.1);
    border-radius: 6px;
    font-size: 0.85rem;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    max-height: 400px;
    overflow-y: auto;
  }}
</style>
</head>
<body>
  <h1>AI Job Scout — Company Recommender</h1>
  <p>Free-tier v1: {TARGET_COMPANY_COUNT} companies matched to your background — best-effort research, not verified live job postings.</p>

  <label for="resume">Resume</label>
  <textarea id="resume" placeholder="Paste your resume here..."></textarea>

  <label for="role">Target role</label>
  <input id="role" type="text" placeholder="e.g. Director of Professional Services">

  <label for="location">Location</label>
  <input id="location" type="text" placeholder="e.g. Austin, TX">
  <div class="checkbox-row">
    <input id="include-remote" type="checkbox">
    <label for="include-remote">Include remote-friendly companies (in addition to companies with a local office within {LOCAL_RADIUS_MILES} miles)</label>
  </div>

  <label for="company-size">Preferred company size</label>
  <select id="company-size">
{_COMPANY_SIZE_OPTIONS_HTML}
  </select>

  <button id="submit-btn">Find {TARGET_COMPANY_COUNT} target companies →</button>
  <div id="status"></div>
  <div id="results"></div>

  <details id="json-details" style="display: none;">
    <summary>Show JSON</summary>
    <pre id="json-output"></pre>
  </details>

<script>
const NOT_ENOUGH_EVIDENCE = "— not enough evidence to say —";

function field(value) {{
  return (value === null || value === undefined || value === "")
    ? NOT_ENOUGH_EVIDENCE
    : value;
}}

function renderCard(company) {{
  const card = document.createElement("div");
  card.className = "card";
  card.innerHTML = `
    <h3>${{field(company.company_name)}}</h3>
    <dl>
      <dt>Size Estimate</dt>
      <dd>${{field(company.size_estimate)}}</dd>
      <dt>Location Match</dt>
      <dd>${{field(company.location_match)}}</dd>
      <dt>Growth / Leadership Note</dt>
      <dd>${{field(company.growth_note)}}</dd>
      <dt>Fit Rationale</dt>
      <dd>${{field(company.fit_rationale)}}</dd>
    </dl>
  `;
  return card;
}}

document.getElementById("submit-btn").addEventListener("click", async () => {{
  const resume = document.getElementById("resume").value;
  const role = document.getElementById("role").value;
  const location = document.getElementById("location").value;
  const companySize = document.getElementById("company-size").value;
  const includeRemote = document.getElementById("include-remote").checked;

  const statusEl = document.getElementById("status");
  const resultsEl = document.getElementById("results");
  const btn = document.getElementById("submit-btn");
  const jsonDetailsEl = document.getElementById("json-details");
  const jsonOutputEl = document.getElementById("json-output");

  resultsEl.innerHTML = "";
  jsonDetailsEl.style.display = "none";
  jsonDetailsEl.open = false;
  statusEl.textContent = "Searching...";
  btn.disabled = true;

  try {{
    const response = await fetch("/recommend", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{
        resume, role, location,
        company_size: companySize,
        include_remote: includeRemote,
      }}),
    }});

    if (!response.ok) {{
      const err = await response.json().catch(() => ({{}}));
      throw new Error(err.detail || `Request failed (${{response.status}})`);
    }}

    const companies = await response.json();
    statusEl.textContent = "";
    companies.forEach((company) => resultsEl.appendChild(renderCard(company)));

    jsonOutputEl.textContent = JSON.stringify(companies, null, 2);
    jsonDetailsEl.style.display = "block";
  }} catch (err) {{
    statusEl.textContent = `Error: ${{err.message}}`;
  }} finally {{
    btn.disabled = false;
  }}
}});
</script>
</body>
</html>
"""


@app.get("/recommend-demo", response_class=HTMLResponse)
def recommend_demo():
    return RECOMMEND_DEMO_HTML


SHORTLIST_DEMO_HTML = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>AI Job Scout — Shortlist Agent</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    max-width: 700px;
    margin: 2rem auto;
    padding: 0 1.5rem;
    line-height: 1.5;
  }}
  h1 {{ font-size: 1.5rem; }}
  label {{ display: block; font-weight: 600; margin-top: 1rem; margin-bottom: 0.25rem; }}
  textarea, input, select {{
    width: 100%;
    box-sizing: border-box;
    padding: 0.5rem;
    font-family: inherit;
    font-size: 1rem;
    border: 1px solid #999;
    border-radius: 6px;
    background: Field;
    color: FieldText;
  }}
  textarea {{ min-height: 140px; resize: vertical; }}
  .checkbox-row {{
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-top: 1rem;
  }}
  .checkbox-row input {{ width: auto; }}
  .checkbox-row label {{ font-weight: 400; margin: 0; }}
  button {{
    margin-top: 1.25rem;
    padding: 0.65rem 1.25rem;
    font-size: 1rem;
    font-weight: 600;
    border: none;
    border-radius: 6px;
    background: #2563eb;
    color: white;
    cursor: pointer;
  }}
  button:disabled {{ opacity: 0.6; cursor: not-allowed; }}
  #status {{ margin-top: 1rem; font-style: italic; }}
  a.results-link {{ display: inline-block; margin-top: 1rem; }}
</style>
</head>
<body>
  <h1>AI Job Scout — Shortlist Agent</h1>
  <p>Builds a 10-company shortlist, saves it, and emails you a digest when done. Takes about 5-10 minutes — no need to keep this tab open.</p>

  <label for="resume">Resume</label>
  <textarea id="resume" placeholder="Paste your resume here..."></textarea>

  <label for="email">Email</label>
  <input id="email" type="email" placeholder="you@example.com">
  <p style="font-size:0.85rem;color:#666;margin:0.25rem 0 0;">Your shortlist digest gets sent here when the search finishes.</p>

  <label for="role">Target role</label>
  <input id="role" type="text" placeholder="e.g. Director of Professional Services">

  <label for="location">Location</label>
  <input id="location" type="text" placeholder="e.g. Austin, TX">
  <div class="checkbox-row">
    <input id="include-remote" type="checkbox">
    <label for="include-remote">Include remote-friendly companies (in addition to companies with a local office within {LOCAL_RADIUS_MILES} miles)</label>
  </div>

  <label for="company-size">Preferred company size</label>
  <select id="company-size">
{_COMPANY_SIZE_OPTIONS_HTML}
  </select>

  <button id="submit-btn">Start shortlist search →</button>
  <div id="status"></div>

<script>
document.getElementById("submit-btn").addEventListener("click", async () => {{
  const resume = document.getElementById("resume").value;
  const email = document.getElementById("email").value;
  const role = document.getElementById("role").value;
  const location = document.getElementById("location").value;
  const companySize = document.getElementById("company-size").value;
  const includeRemote = document.getElementById("include-remote").checked;

  const statusEl = document.getElementById("status");
  const btn = document.getElementById("submit-btn");

  statusEl.innerHTML = "Starting...";
  btn.disabled = true;

  try {{
    const response = await fetch("/shortlist", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{
        resume, email, role, location,
        company_size: companySize,
        include_remote: includeRemote,
      }}),
    }});

    if (!response.ok) {{
      const err = await response.json().catch(() => ({{}}));
      throw new Error(err.detail || `Request failed (${{response.status}})`);
    }}

    const result = await response.json();
    statusEl.innerHTML = `${{result.message}} <a class="results-link" href="/candidates-demo">View saved candidates →</a>`;
  }} catch (err) {{
    statusEl.textContent = `Error: ${{err.message}}`;
    btn.disabled = false;
  }}
}});
</script>
</body>
</html>
"""


@app.get("/shortlist-demo", response_class=HTMLResponse)
def shortlist_demo():
    return SHORTLIST_DEMO_HTML


CANDIDATES_DEMO_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>AI Job Scout — Saved Candidates</title>
<style>
  :root { color-scheme: light dark; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    max-width: 900px;
    margin: 2rem auto;
    padding: 0 1.5rem;
    line-height: 1.5;
  }
  h1 { font-size: 1.5rem; }
  label { display: block; font-weight: 600; margin-top: 1rem; margin-bottom: 0.25rem; }
  select {
    width: 100%;
    box-sizing: border-box;
    padding: 0.5rem;
    font-family: inherit;
    font-size: 1rem;
    border: 1px solid #999;
    border-radius: 6px;
    background: Field;
    color: FieldText;
  }
  #status { margin-top: 1rem; font-style: italic; }
  #results {
    margin-top: 2rem;
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 1rem;
  }
  @media (max-width: 600px) {
    #results { grid-template-columns: 1fr; }
  }
  .card {
    border: 1px solid #ccc;
    border-radius: 8px;
    padding: 1rem;
    min-width: 0;
    overflow-wrap: break-word;
  }
  .card h3 { margin: 0 0 0.5rem; overflow-wrap: break-word; }
  .card dl { margin: 0; }
  .card dt { font-weight: 600; font-size: 0.85rem; margin-top: 0.5rem; }
  .card dd { margin: 0; overflow-wrap: anywhere; word-break: break-word; }
  .missing { color: #888; font-style: italic; }
</style>
</head>
<body>
  <h1>AI Job Scout — Saved Candidates</h1>

  <label for="search-picker">Search</label>
  <select id="search-picker"></select>

  <div id="status">Loading...</div>
  <div id="results"></div>

<script>
const NOT_ENOUGH_EVIDENCE = "— not enough evidence to say —";

function field(value) {
  return (value === null || value === undefined || value === "")
    ? NOT_ENOUGH_EVIDENCE
    : value;
}

function searchKey(c) {
  return JSON.stringify([c.role, c.location, c.company_size, c.include_remote]);
}

function searchLabel(c) {
  const remote = c.include_remote ? "+ remote-friendly" : "local only";
  return `${c.role} — ${c.location} — ${c.company_size} (${remote})`;
}

function renderCard(company) {
  const card = document.createElement("div");
  card.className = "card";
  card.innerHTML = `
    <h3>${field(company.rank)}. ${field(company.company_name)}</h3>
    <dl>
      <dt>Size Estimate</dt>
      <dd>${field(company.size_estimate)}</dd>
      <dt>Location Match</dt>
      <dd>${field(company.location_match)}</dd>
      <dt>Growth / Leadership Note</dt>
      <dd>${field(company.growth_note)}</dd>
      <dt>Fit Rationale</dt>
      <dd>${field(company.fit_rationale)}</dd>
    </dl>
  `;
  return card;
}

let allCandidates = [];

function renderSelectedSearch() {
  const picker = document.getElementById("search-picker");
  const resultsEl = document.getElementById("results");
  const selected = picker.value;
  resultsEl.innerHTML = "";
  allCandidates
    .filter((c) => searchKey(c) === selected)
    .forEach((c) => resultsEl.appendChild(renderCard(c)));
}

(async () => {
  const statusEl = document.getElementById("status");
  const picker = document.getElementById("search-picker");

  try {
    const response = await fetch("/candidates");
    if (!response.ok) throw new Error(`Request failed (${response.status})`);
    allCandidates = await response.json();

    if (allCandidates.length === 0) {
      statusEl.textContent = "No candidates saved yet — run a search at /shortlist-demo first.";
      picker.style.display = "none";
      return;
    }

    const seen = new Set();
    for (const c of allCandidates) {
      const key = searchKey(c);
      if (seen.has(key)) continue;
      seen.add(key);
      const option = document.createElement("option");
      option.value = key;
      option.textContent = searchLabel(c);
      picker.appendChild(option);
    }

    statusEl.textContent = "";
    picker.addEventListener("change", renderSelectedSearch);
    renderSelectedSearch();
  } catch (err) {
    statusEl.textContent = `Error: ${err.message}`;
  }
})();
</script>
</body>
</html>
"""


@app.get("/candidates-demo", response_class=HTMLResponse)
def candidates_demo():
    return CANDIDATES_DEMO_HTML
