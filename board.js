const client = supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

const STATUS_COLUMNS = [
  { value: 'identified', label: 'Identified' },
  { value: 'applied', label: 'Applied' },
  { value: 'interviewing', label: 'Interviewing' },
  { value: 'closed', label: 'Closed' },
];

let openings = [];
let draggedId = null;

function formatDate(value) {
  if (!value) return '';
  const d = new Date(value);
  if (isNaN(d)) return '';
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function buildColumns() {
  const board = document.getElementById('board');
  board.innerHTML = '';

  STATUS_COLUMNS.forEach((col) => {
    const column = document.createElement('div');
    column.className = 'kanban-column';
    column.dataset.status = col.value;
    column.addEventListener('dragover', onColumnDragOver);
    column.addEventListener('dragleave', onColumnDragLeave);
    column.addEventListener('drop', onColumnDrop);

    const header = document.createElement('div');
    header.className = 'kanban-column-header';

    const title = document.createElement('h3');
    title.className = 'kanban-column-title';
    title.textContent = col.label;
    header.appendChild(title);

    const badge = document.createElement('span');
    badge.className = 'kanban-count-badge';
    badge.dataset.count = col.value;
    badge.textContent = '0';
    header.appendChild(badge);

    column.appendChild(header);

    const cardsWrap = document.createElement('div');
    cardsWrap.className = 'kanban-cards';
    cardsWrap.dataset.status = col.value;
    column.appendChild(cardsWrap);

    board.appendChild(column);
  });
}

function renderCard(opening) {
  const card = document.createElement('div');
  card.className = `kanban-card status-${opening.status}`;
  card.draggable = true;
  card.dataset.id = opening.id;

  const title = document.createElement('div');
  title.className = 'kanban-card-title';
  title.textContent = opening.title;
  card.appendChild(title);

  const company = document.createElement('div');
  company.className = 'kanban-card-company';
  company.textContent = opening.company;
  card.appendChild(company);

  const metaParts = [];
  if (opening.location) metaParts.push(opening.location);
  if (opening.match_score !== null && opening.match_score !== undefined) {
    metaParts.push(`Match: ${opening.match_score}`);
  }
  if (opening.posted_at) metaParts.push(`Posted ${formatDate(opening.posted_at)}`);

  if (metaParts.length) {
    const meta = document.createElement('div');
    meta.className = 'kanban-card-meta';
    meta.textContent = metaParts.join(' · ');
    card.appendChild(meta);
  }

  const created = document.createElement('div');
  created.className = 'kanban-card-created';
  created.textContent = `Added ${formatDate(opening.created_at)}`;
  card.appendChild(created);

  card.addEventListener('click', () => openEditModal(opening));
  card.addEventListener('dragstart', onCardDragStart);
  card.addEventListener('dragend', onCardDragEnd);

  return card;
}

function renderCards() {
  STATUS_COLUMNS.forEach((col) => {
    const wrap = document.querySelector(`.kanban-cards[data-status="${col.value}"]`);
    const badge = document.querySelector(`.kanban-count-badge[data-count="${col.value}"]`);
    wrap.innerHTML = '';

    const items = openings.filter((o) => o.status === col.value);
    badge.textContent = items.length;

    if (items.length === 0) {
      const empty = document.createElement('p');
      empty.className = 'kanban-empty';
      empty.textContent = 'Nothing here yet — add an opening or drag one over.';
      wrap.appendChild(empty);
      return;
    }

    items.forEach((opening) => wrap.appendChild(renderCard(opening)));
  });
}

async function loadOpenings() {
  const { data, error } = await client
    .from('openings')
    .select('*')
    .order('created_at', { ascending: false });

  if (error) {
    console.error('Failed to load openings', error);
    return;
  }

  openings = data || [];
  renderCards();
}

// Drag and drop (desktop) -- mobile falls back to the edit modal's status dropdown
function onCardDragStart(event) {
  draggedId = event.currentTarget.dataset.id;
  event.currentTarget.classList.add('dragging');
  event.dataTransfer.effectAllowed = 'move';
  event.dataTransfer.setData('text/plain', draggedId);
}

function onCardDragEnd(event) {
  event.currentTarget.classList.remove('dragging');
}

function onColumnDragOver(event) {
  event.preventDefault();
  event.currentTarget.querySelector('.kanban-cards').classList.add('drag-over');
}

function onColumnDragLeave(event) {
  event.currentTarget.querySelector('.kanban-cards').classList.remove('drag-over');
}

async function onColumnDrop(event) {
  event.preventDefault();
  event.currentTarget.querySelector('.kanban-cards').classList.remove('drag-over');

  const newStatus = event.currentTarget.dataset.status;
  const id = draggedId || event.dataTransfer.getData('text/plain');
  draggedId = null;
  if (!id) return;

  const opening = openings.find((o) => String(o.id) === String(id));
  if (!opening || opening.status === newStatus) return;

  const previousStatus = opening.status;
  opening.status = newStatus;
  renderCards();

  const { error } = await client.from('openings').update({ status: newStatus }).eq('id', id);
  if (error) {
    console.error('Failed to update status', error);
    alert(`Could not move that card: ${error.message}`);
    opening.status = previousStatus;
    renderCards();
  }
}

// Add form
const addToggle = document.getElementById('add-toggle');
const addForm = document.getElementById('add-form');

addToggle.addEventListener('click', () => {
  addForm.hidden = !addForm.hidden;
});

addForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.target;
  const statusEl = document.getElementById('add-status');
  statusEl.textContent = 'Saving...';

  const payload = {
    title: form.title.value,
    company: form.company.value,
    location: form.location.value || null,
    posted_at: form.posted_at.value || null,
    match_score: form.match_score.value ? Number(form.match_score.value) : null,
    url: form.url.value || null,
    notes: form.notes.value || null,
    status: STATUS_COLUMNS[0].value,
  };

  const { error } = await client.from('openings').insert(payload);
  if (error) {
    statusEl.textContent = `Error: ${error.message}`;
    console.error(error);
    return;
  }

  statusEl.textContent = 'Added.';
  form.reset();
  addForm.hidden = true;
  loadOpenings();
});

// Edit modal
const editModal = document.getElementById('edit-modal');
const editForm = document.getElementById('edit-form');

function openEditModal(opening) {
  document.getElementById('edit-id').value = opening.id;
  document.getElementById('edit-title').value = opening.title || '';
  document.getElementById('edit-company').value = opening.company || '';
  document.getElementById('edit-status').value = opening.status || STATUS_COLUMNS[0].value;
  document.getElementById('edit-location').value = opening.location || '';
  document.getElementById('edit-posted_at').value = opening.posted_at || '';
  document.getElementById('edit-match_score').value =
    opening.match_score === null || opening.match_score === undefined ? '' : opening.match_score;
  document.getElementById('edit-salary_range').value = opening.salary_range || '';
  document.getElementById('edit-url').value = opening.url || '';
  document.getElementById('edit-match_reasons').value = opening.match_reasons || '';
  document.getElementById('edit-notes').value = opening.notes || '';
  document.getElementById('edit-status-msg').textContent = '';
  editModal.hidden = false;
}

function closeEditModal() {
  editModal.hidden = true;
}

document.getElementById('edit-cancel').addEventListener('click', closeEditModal);
editModal.addEventListener('click', (event) => {
  if (event.target === editModal) closeEditModal();
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && !editModal.hidden) closeEditModal();
});

editForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const id = document.getElementById('edit-id').value;
  const statusMsg = document.getElementById('edit-status-msg');
  statusMsg.textContent = 'Saving...';

  const matchScoreValue = document.getElementById('edit-match_score').value;

  const payload = {
    title: document.getElementById('edit-title').value,
    company: document.getElementById('edit-company').value,
    status: document.getElementById('edit-status').value,
    location: document.getElementById('edit-location').value || null,
    posted_at: document.getElementById('edit-posted_at').value || null,
    match_score: matchScoreValue ? Number(matchScoreValue) : null,
    salary_range: document.getElementById('edit-salary_range').value || null,
    url: document.getElementById('edit-url').value || null,
    match_reasons: document.getElementById('edit-match_reasons').value || null,
    notes: document.getElementById('edit-notes').value || null,
  };

  const { error } = await client.from('openings').update(payload).eq('id', id);
  if (error) {
    statusMsg.textContent = `Error: ${error.message}`;
    console.error(error);
    return;
  }

  closeEditModal();
  loadOpenings();
});

document.getElementById('edit-delete').addEventListener('click', async () => {
  const id = document.getElementById('edit-id').value;
  if (!confirm('Delete this opening? This cannot be undone.')) return;

  const { error } = await client.from('openings').delete().eq('id', id);
  if (error) {
    alert(`Could not delete: ${error.message}`);
    console.error(error);
    return;
  }

  closeEditModal();
  loadOpenings();
});

// Realtime sync
client
  .channel('openings-realtime')
  .on('postgres_changes', { event: '*', schema: 'public', table: 'openings' }, () => {
    loadOpenings();
  })
  .subscribe();

buildColumns();
loadOpenings();
