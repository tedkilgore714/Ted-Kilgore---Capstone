function typeText(el, fullText, speed) {
  return new Promise((resolve) => {
    el.textContent = '';
    el.classList.add('is-typing');
    let i = 0;
    const interval = setInterval(() => {
      i += 1;
      el.textContent = fullText.slice(0, i);
      if (i >= fullText.length) {
        clearInterval(interval);
        el.classList.remove('is-typing');
        resolve();
      }
    }, speed);
  });
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function revealSequentially(items, gap) {
  for (const item of items) {
    await wait(gap);
    item.classList.add('is-visible');
  }
}

async function runHiwAnimation() {
  const resume = document.getElementById('hiw-resume');
  const roles = document.getElementById('hiw-roles');
  const rankList = document.getElementById('hiw-location');
  const button = document.getElementById('hiw-generate');
  const resultsPanel = document.getElementById('hiw-results');
  if (!resume || !roles || !rankList || !button || !resultsPanel) return;

  const resumeText =
    'Ted Kilgore — Director of Professional Services. 10+ years leading ' +
    'post-sales and customer success teams at B2B SaaS companies...';
  const rolesText = roles.textContent;
  const rankItems = Array.from(rankList.querySelectorAll('.mockup-rank-item'));
  const results = Array.from(resultsPanel.querySelectorAll('.mockup-result'));

  rankList.classList.add('js-animated');
  resultsPanel.classList.add('js-animated');

  for (;;) {
    resume.textContent = '';
    roles.textContent = '';
    rankItems.forEach((item) => item.classList.remove('is-visible'));
    results.forEach((card) => card.classList.remove('is-visible'));

    await wait(600);
    await typeText(resume, resumeText, 12);
    await wait(400);

    await typeText(roles, rolesText, 35);
    await wait(300);

    await revealSequentially(rankItems, 350);
    await wait(400);

    button.classList.add('is-pressed');
    await wait(200);
    button.classList.remove('is-pressed');

    await revealSequentially(results, 450);

    await wait(3500);
  }
}

function easeInOutCubic(t) {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

// Moves the drag-cursor dot from its current spot to just above the target
// column, along an eased path -- purely cosmetic, so the card move below
// reads as a drag rather than a teleport.
function animateCursorTo(cursor, fromRect, toRect, containerRect, duration) {
  return new Promise((resolve) => {
    const start = performance.now();
    const fromX = fromRect.left + fromRect.width / 2 - containerRect.left;
    const fromY = fromRect.top + fromRect.height / 2 - containerRect.top;
    const toX = toRect.left + toRect.width / 2 - containerRect.left;
    const toY = toRect.top + 14 - containerRect.top;

    cursor.classList.add('is-visible');

    function step(now) {
      const t = Math.min(1, (now - start) / duration);
      const eased = easeInOutCubic(t);
      cursor.style.left = `${fromX + (toX - fromX) * eased}px`;
      cursor.style.top = `${fromY + (toY - fromY) * eased}px`;
      if (t < 1) requestAnimationFrame(step);
      else resolve();
    }
    requestAnimationFrame(step);
  });
}

// Re-parents card into targetColumn, animating the jump with the FLIP
// technique (record position before, move it, invert via transform, then
// play back to 0) rather than faking native HTML5 drag events.
async function moveCardToColumn(card, targetColumn, cursor, positioningContainer) {
  const cardRect = card.getBoundingClientRect();
  const containerRect = positioningContainer.getBoundingClientRect();
  const targetRect = targetColumn.getBoundingClientRect();

  await animateCursorTo(cursor, cardRect, targetRect, containerRect, 500);

  card.classList.add('is-dragging');
  const first = card.getBoundingClientRect();
  targetColumn.appendChild(card);
  const last = card.getBoundingClientRect();
  const dx = first.left - last.left;
  const dy = first.top - last.top;

  card.style.transition = 'none';
  card.style.transform = `translate(${dx}px, ${dy}px)`;
  card.offsetHeight; // force reflow so the transform above applies before transitioning
  card.style.transition = 'transform 0.45s cubic-bezier(.2,.8,.2,1)';
  card.style.transform = 'translate(0, 0)';

  await wait(470);
  card.classList.remove('is-dragging');
  card.style.transition = '';
  card.style.transform = '';
  cursor.classList.remove('is-visible');
}

async function runOpeningsAnimation() {
  const container = document.getElementById('hiw-openings-body');
  const card = document.getElementById('hiw-drag-card');
  const cursor = document.getElementById('hiw-drag-cursor');
  const columns = ['identified', 'applied', 'interviewing', 'closed'].map((status) =>
    document.getElementById(`hiw-col-${status}`)
  );
  if (!container || !card || !cursor || columns.some((c) => !c)) return;

  for (;;) {
    for (let i = 1; i < columns.length; i++) {
      await wait(1700);
      await moveCardToColumn(card, columns[i], cursor, container);
    }
    await wait(2200);

    card.style.transition = 'opacity 0.3s ease';
    card.style.opacity = '0';
    await wait(320);
    columns[0].appendChild(card);
    card.style.transition = '';
    card.style.opacity = '';
    await wait(150);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (prefersReducedMotion) return;
  runHiwAnimation();
  runOpeningsAnimation();
});
