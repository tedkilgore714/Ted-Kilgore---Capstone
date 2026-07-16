const API_BASE = 'https://ted-kilgore-capstone.onrender.com';

// Jobs-board links: the Agent's underlying research (CompanyRecommender)
// doesn't collect a verified job-posting URL for each company -- only the
// Matcher does that -- so this is a best-effort Google search for the
// company's jobs board rather than a link to a specific posting.
const CAREERS_LINK_MODE = 'google'; // 'omit' | 'google'

function getCareersLink(company) {
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

function renderCompany(company) {
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

  const careersLink = getCareersLink(company);
  if (careersLink) {
    const link = document.createElement('a');
    link.className = 'kanban-card-link';
    link.href = careersLink;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = 'Jobs board';
    card.appendChild(link);
  }

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
  return Array.from(seen.values()).sort((a, b) => (a.rank || Infinity) - (b.rank || Infinity));
}

function scopeKey(c) {
  return [c.role, c.location, c.company_size, c.include_remote].join('|');
}

// Different searches (different role/location/size/remote) can produce
// completely unrelated companies -- showing them all merged in one grid
// reads as broken. Instead, only show the most recently created search's
// results, identified by whichever row has the latest created_at.
function filterToMostRecentSearch(candidates) {
  if (candidates.length === 0) return { scope: null, rows: [] };

  const mostRecent = candidates.reduce((latest, c) =>
    new Date(c.created_at) > new Date(latest.created_at) ? c : latest
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

async function loadCompanies() {
  const list = document.getElementById('companies-list');
  const scopeLabel = document.getElementById('companies-scope-label');
  list.innerHTML = '<p class="kanban-empty">Loading...</p>';
  scopeLabel.textContent = '';

  let data;
  try {
    const response = await fetch(`${API_BASE}/candidates`);
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
  const companies = dedupeByCompanyName(rows);

  if (companies.length === 0) {
    const empty = document.createElement('p');
    empty.className = 'kanban-empty';
    empty.textContent =
      'No companies yet — run a shortlist search above and your companies will appear here once it finishes (about 5-10 minutes).';
    list.appendChild(empty);
    return;
  }

  scopeLabel.textContent = describeScope(scope);
  companies.forEach((company) => list.appendChild(renderCompany(company)));
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
    email: document.getElementById('shortlist-email').value,
    role: document.getElementById('shortlist-role').value,
    location: document.getElementById('shortlist-location').value,
    company_size: document.getElementById('shortlist-size').value,
    include_remote: document.getElementById('shortlist-remote').checked,
  };

  try {
    const response = await fetch(`${API_BASE}/shortlist`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const result = await response.json();
    shortlistStatus.textContent =
      result.message ||
      `Shortlist search started — this takes about 5-10 minutes. Results will be emailed to ${payload.email} when it's done, or refresh this page.`;
  } catch (error) {
    console.error('Failed to start shortlist search', error);
    shortlistStatus.textContent = `Error: ${error.message}`;
  }
});

document.getElementById('refresh-companies').addEventListener('click', loadCompanies);

loadCompanies();
