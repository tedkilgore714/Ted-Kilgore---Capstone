const API_BASE = 'https://ted-kilgore-capstone.onrender.com';

// Must match TARGET_COUNT in shortlist_agent.py -- caps what's shown here
// as defense-in-depth in case a scope ever has more rows saved than the
// current target (e.g. from before a target change), even though the
// backend now caps what it ranks/emails too.
const DISPLAY_LIMIT = 10;

// Must match REJECT_CAP in shortlist_agent.py -- free-tier limit on how
// many companies can be rejected per search scope. Enforced server-side;
// this is only used here to grey out the UI once the limit is reached
// instead of letting a click round-trip to a 403.
const REJECT_CAP = 5;

// Jobs-board links: CompanyRecommender now researches each company's
// actual jobs/careers listing page (jobs_url) via web_search -- best-effort,
// not live-verified the way company_matcher.py's hiring_signal is. Falls
// back to a Google search only when it couldn't confidently find one.
const CAREERS_LINK_MODE = 'google'; // 'omit' | 'google' -- fallback when jobs_url is missing

function getCareersLink(company) {
  if (company.jobs_url) return company.jobs_url;
  if (CAREERS_LINK_MODE === 'google') {
    return `https://www.google.com/search?q=${encodeURIComponent(company.company_name + ' jobs')}`;
  }
  return null;
}

function addCompanyField(card, label, value) {
  if (!value) return;
  const field = document.createElement('div');
  field.className = 'company-card-field';

  const labelEl = document.createElement('span');
  labelEl.className = 'company-card-label';
  labelEl.textContent = label;
  field.appendChild(labelEl);

  const valueEl = document.createElement('p');
  valueEl.className = 'company-card-value';
  valueEl.textContent = value;
  field.appendChild(valueEl);

  card.appendChild(field);
}

function renderCompany(company, rejectDisabled, onReject) {
  const card = document.createElement('div');
  card.className = 'company-card';

  const name = document.createElement('div');
  name.className = 'company-card-name';
  name.textContent = company.company_name;
  card.appendChild(name);

  addCompanyField(card, 'Size Estimate', company.size_estimate);
  addCompanyField(card, 'Location Match', company.location_match);
  addCompanyField(card, 'Growth / Leadership Note', company.growth_note);
  addCompanyField(card, 'Fit Rationale', company.fit_rationale);

  const actions = document.createElement('div');
  actions.className = 'company-card-actions';

  const careersLink = getCareersLink(company);
  if (careersLink) {
    const link = document.createElement('a');
    link.className = 'kanban-card-link';
    link.href = careersLink;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = company.jobs_url ? 'Jobs board' : 'Search jobs';
    actions.appendChild(link);
  }

  const rejectButton = document.createElement('button');
  rejectButton.type = 'button';
  rejectButton.className = 'company-card-reject';
  rejectButton.textContent = 'Not a fit';
  rejectButton.disabled = rejectDisabled;
  rejectButton.title = rejectDisabled
    ? `Free plan limit reached — up to ${REJECT_CAP} rejections per search`
    : 'Reject this company and search for a replacement';
  rejectButton.addEventListener('click', () => onReject(company, card, rejectButton));
  actions.appendChild(rejectButton);

  card.appendChild(actions);

  return card;
}

function dedupeByCompanyName(candidates) {
  const seen = new Map();
  for (const c of candidates) {
    const key = (c.company_name || '').trim().toLowerCase();
    if (!key) continue;
    const existing = seen.get(key);
    if (!existing || (c.rank || Infinity) < (existing.rank || Infinity)) {
      seen.set(key, c);
    }
  }
  return Array.from(seen.values())
    .sort((a, b) => (a.rank || Infinity) - (b.rank || Infinity))
    .slice(0, DISPLAY_LIMIT);
}

function scopeKey(c) {
  return [c.email, c.role, c.location, c.company_size, c.include_remote].join('|');
}

function lastTouched(c) {
  return c.updated_at || c.created_at;
}

// Different searches (different role/location/size/remote) can produce
// completely unrelated companies -- showing them all merged in one grid
// reads as broken. Instead, only show the most recently touched search's
// results. Uses updated_at (falling back to created_at) rather than
// created_at alone, because re-running a scope that's already at the
// target count saves 0 new rows -- created_at never changes, but
// updated_at does (the agent still re-ranks and bumps it), so this is
// what makes a re-run actually show up as "current" here.
function filterToMostRecentSearch(candidates) {
  if (candidates.length === 0) return { scope: null, rows: [] };

  const mostRecent = candidates.reduce((latest, c) =>
    new Date(lastTouched(c)) > new Date(lastTouched(latest)) ? c : latest
  );
  const key = scopeKey(mostRecent);
  const rows = candidates.filter((c) => scopeKey(c) === key);
  return { scope: mostRecent, rows };
}

function describeScope(scope) {
  const parts = [scope.role, scope.location, scope.company_size];
  let text = `Showing: ${parts.join(' — ')}`;
  if (scope.include_remote) text += ' (+ remote-friendly)';
  return text;
}

async function authHeaders(extra) {
  const { data: { session } } = await authClient.auth.getSession();
  return { ...extra, ...(session ? { Authorization: `Bearer ${session.access_token}` } : {}) };
}

async function rejectCompany(candidateId, company, cardEl, button) {
  if (!confirm(`Reject ${company.company_name}? This uses one of your ${REJECT_CAP} rejections for this search, and a replacement search will run in the background.`)) {
    return;
  }
  button.disabled = true;
  button.textContent = 'Rejecting...';

  try {
    const response = await fetch(`${API_BASE}/reject`, {
      method: 'POST',
      headers: await authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ candidate_id: candidateId }),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(result.detail || `${response.status} ${response.statusText}`);
    }
    cardEl.remove();
    const note = document.getElementById('reject-limit-note');
    if (note) note.textContent = result.message || 'Rejected — finding a replacement.';
  } catch (error) {
    console.error('Failed to reject company', error);
    alert(`Could not reject: ${error.message}`);
    button.disabled = false;
    button.textContent = 'Not a fit';
  }
}

async function loadCompanies() {
  const list = document.getElementById('companies-list');
  const scopeLabel = document.getElementById('companies-scope-label');
  const limitNote = document.getElementById('reject-limit-note');
  list.innerHTML = '<p class="kanban-empty">Loading...</p>';
  scopeLabel.textContent = '';
  limitNote.textContent = '';

  let data;
  try {
    const response = await fetch(`${API_BASE}/candidates`, { headers: await authHeaders() });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    data = await response.json();
  } catch (error) {
    console.error('Failed to load candidates', error);
    list.innerHTML = '';
    const msg = document.createElement('p');
    msg.className = 'kanban-empty';
    msg.textContent = 'Could not load companies right now — try refreshing in a moment.';
    list.appendChild(msg);
    return;
  }

  list.innerHTML = '';

  const { scope, rows } = filterToMostRecentSearch(data || []);
  const rejectedCount = rows.filter((c) => c.rejected).length;
  const companies = dedupeByCompanyName(rows.filter((c) => !c.rejected));

  if (companies.length === 0 && rejectedCount === 0) {
    const empty = document.createElement('p');
    empty.className = 'kanban-empty';
    empty.textContent =
      'No companies yet — run a shortlist search above and your companies will appear here once it finishes (about 5-10 minutes).';
    list.appendChild(empty);
    return;
  }

  scopeLabel.textContent = describeScope(scope);

  const atCap = rejectedCount >= REJECT_CAP;
  limitNote.textContent = atCap
    ? `Free plan limit reached — you've rejected ${REJECT_CAP} of ${REJECT_CAP} companies for this search.`
    : `${rejectedCount} of ${REJECT_CAP} rejections used for this search.`;

  companies.forEach((company) => {
    const card = renderCompany(company, atCap, (c, cardEl, button) =>
      rejectCompany(company.id, c, cardEl, button)
    );
    list.appendChild(card);
  });
}

// Trigger form -- kicks off the Shortlist Agent (fire-and-forget) directly
// from the real site instead of the separate Render demo page.
const shortlistForm = document.getElementById('shortlist-form');
const shortlistStatus = document.getElementById('shortlist-status');

shortlistForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  shortlistStatus.textContent = 'Starting...';

  // Clear the previous search's results right away -- leaving them up
  // while a new search runs reads as if the button did nothing.
  document.getElementById('companies-scope-label').textContent = '';
  document.getElementById('companies-list').innerHTML =
    '<p class="kanban-empty">Search started — your new shortlist will appear here in about 5-10 minutes.</p>';

  const payload = {
    resume: document.getElementById('shortlist-resume').value,
    role: document.getElementById('shortlist-role').value,
    location: document.getElementById('shortlist-location').value,
    company_size: document.getElementById('shortlist-size').value,
    include_remote: document.getElementById('shortlist-remote').checked,
  };

  try {
    const response = await fetch(`${API_BASE}/shortlist`, {
      method: 'POST',
      headers: await authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const result = await response.json();
    shortlistStatus.textContent =
      result.message ||
      `Shortlist search started — this takes about 5-10 minutes. Results will be emailed to you when it's done, or refresh this page.`;
  } catch (error) {
    console.error('Failed to start shortlist search', error);
    shortlistStatus.textContent = `Error: ${error.message}`;
  }
});

document.getElementById('refresh-companies').addEventListener('click', loadCompanies);

// Prefill the location field from the browser's geolocation, so someone
// searching from where they already live doesn't have to type it --
// still fully editable for anyone planning to relocate or search
// elsewhere. Silently does nothing on denial/error/unsupported browsers;
// this is a convenience, not a requirement, and the field stays usable
// either way.
function prefillLocation() {
  const input = document.getElementById('shortlist-location');
  if (!input || input.value || !navigator.geolocation) return;

  navigator.geolocation.getCurrentPosition(
    async (position) => {
      try {
        const { latitude, longitude } = position.coords;
        const response = await fetch(
          `https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=${latitude}&longitude=${longitude}&localityLanguage=en`
        );
        if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
        const place = await response.json();

        if (input.value) return; // user started typing while this was in flight

        const city = place.city || place.locality;
        const stateCode = (place.principalSubdivisionCode || '').split('-').pop();
        const state = stateCode || place.principalSubdivision;

        if (city && state) {
          input.value = `${city}, ${state}`;
        } else if (city) {
          input.value = city;
        }
      } catch (error) {
        console.error('Reverse geocoding failed', error);
      }
    },
    () => {}, // permission denied or unavailable -- leave the field as-is
    { timeout: 8000 }
  );
}

// Gate the whole page behind a signed-in session -- companies.html renders
// both #signed-out-panel and #signed-in-content hidden by default so there's
// no flash of the form before this resolves.
authClient.auth.getSession().then(({ data: { session } }) => {
  if (!session) {
    document.getElementById('signed-out-panel').hidden = false;
    return;
  }
  document.getElementById('signed-in-content').hidden = false;
  document.getElementById('signed-in-note').textContent = `Signed in as ${session.user.email}`;
  loadCompanies();
  prefillLocation();
});

document.getElementById('sign-out').addEventListener('click', async () => {
  await authClient.auth.signOut();
  window.location.href = 'account.html?return=companies.html';
});
