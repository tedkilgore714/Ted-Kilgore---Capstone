const client = supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

function renderCompany(company) {
  const card = document.createElement('div');
  card.className = 'company-card';

  const name = document.createElement('div');
  name.className = 'company-card-name';
  name.textContent = company.company_name;
  card.appendChild(name);

  const metaParts = [];
  if (company.employees) metaParts.push(`~${company.employees.toLocaleString()} employees`);
  if (company.growth) metaParts.push(company.growth);
  if (company.location) metaParts.push(company.location);

  if (metaParts.length) {
    const meta = document.createElement('div');
    meta.className = 'company-card-meta';
    meta.textContent = metaParts.join(' · ');
    card.appendChild(meta);
  }

  if (company.why) {
    const why = document.createElement('p');
    why.className = 'company-card-why';
    why.textContent = `Why: ${company.why}`;
    card.appendChild(why);
  }

  if (company.url) {
    const link = document.createElement('a');
    link.className = 'kanban-card-link';
    link.href = company.url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = 'Careers page';
    card.appendChild(link);
  }

  return card;
}

async function loadCompanies() {
  const list = document.getElementById('companies-list');

  const { data, error } = await client
    .from('companies')
    .select('*')
    .order('company_name', { ascending: true });

  list.innerHTML = '';

  if (error) {
    console.error('Failed to load companies', error);
    const msg = document.createElement('p');
    msg.className = 'kanban-empty';
    msg.textContent =
      'No company list yet — your 30-company shortlist will appear here once it has been generated.';
    list.appendChild(msg);
    return;
  }

  if (!data || data.length === 0) {
    const empty = document.createElement('p');
    empty.className = 'kanban-empty';
    empty.textContent =
      'No companies yet — your 30-company shortlist will appear here once it has been generated.';
    list.appendChild(empty);
    return;
  }

  data.forEach((company) => list.appendChild(renderCompany(company)));
}

// Realtime sync
client
  .channel('companies-realtime')
  .on('postgres_changes', { event: '*', schema: 'public', table: 'companies' }, () => {
    loadCompanies();
  })
  .subscribe();

loadCompanies();
