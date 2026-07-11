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
  const dropzone = document.getElementById('hiw-dropzone');
  const roles = document.getElementById('hiw-roles');
  const rankList = document.getElementById('hiw-location');
  const button = document.getElementById('hiw-generate');
  const resultsPanel = document.getElementById('hiw-results');
  if (!dropzone || !roles || !rankList || !button || !resultsPanel) return;

  const rolesText = roles.textContent;
  const rankItems = Array.from(rankList.querySelectorAll('.mockup-rank-item'));
  const results = Array.from(resultsPanel.querySelectorAll('.mockup-result'));

  dropzone.classList.add('js-animated');
  rankList.classList.add('js-animated');
  resultsPanel.classList.add('js-animated');

  for (;;) {
    dropzone.classList.remove('has-file');
    roles.textContent = '';
    rankItems.forEach((item) => item.classList.remove('is-visible'));
    results.forEach((card) => card.classList.remove('is-visible'));

    await wait(600);
    dropzone.classList.add('has-file');
    await wait(500);

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

document.addEventListener('DOMContentLoaded', () => {
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (prefersReducedMotion) return;
  runHiwAnimation();
});
