const client = supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

const STATUSES = ['identified', 'applied', 'interviewing', 'closed'];

function renderCard(opening) {
  const card = document.createElement('div');
  card.className = 'kanban-card';

  const title = document.createElement('div');
  title.className = 'kanban-card-title';
  title.textContent = opening.title;
  card.appendChild(title);

  const company = document.createElement('div');
  company.className = 'kanban-card-company';
  company.textContent = opening.company;
  card.appendChild(company);

  if (opening.location) {
    const location = document.createElement('div');
    location.className = 'kanban-card-meta';
    location.textContent = opening.location;
    card.appendChild(location);
  }

  if (opening.url) {
    const link = document.createElement('a');
    link.className = 'kanban-card-link';
    link.href = opening.url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = 'View posting';
    card.appendChild(link);
  }

  return card;
}

async function loadOpenings() {
  const { data, error } = await client
    .from('openings')
    .select('*')
    .order('created_at', { ascending: false });

  const columns = {};
  STATUSES.forEach((status) => {
    const column = document.querySelector(`.kanban-column[data-status="${status}"] .kanban-cards`);
    column.innerHTML = '';
    columns[status] = column;
  });

  if (error) {
    console.error('Failed to load openings', error);
    return;
  }

  STATUSES.forEach((status) => {
    const items = data.filter((opening) => opening.status === status);
    if (items.length === 0) {
      const empty = document.createElement('p');
      empty.className = 'kanban-empty';
      empty.textContent = 'No openings yet.';
      columns[status].appendChild(empty);
      return;
    }
    items.forEach((opening) => columns[status].appendChild(renderCard(opening)));
  });
}

document.getElementById('opening-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.target;
  const statusEl = document.getElementById('opening-form-status');
  statusEl.textContent = 'Saving...';

  const { error } = await client.from('openings').insert({
    company: form.company.value,
    title: form.title.value,
    url: form.url.value || null,
    location: form.location.value || null,
  });

  if (error) {
    statusEl.textContent = `Error: ${error.message}`;
    console.error(error);
    return;
  }

  statusEl.textContent = 'Added.';
  form.reset();
  loadOpenings();
});

loadOpenings();
