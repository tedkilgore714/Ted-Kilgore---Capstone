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

document.addEventListener('DOMContentLoaded', () => {
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (prefersReducedMotion) return;
  runHiwAnimation();
});
