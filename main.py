from fastapi import FastAPI, HTTPException
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

app = FastAPI(title="AI Job Scout — Company Matcher")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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
