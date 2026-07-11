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

async function runHiwAnimation() {
  const resume = document.getElementById('hiw-resume');
  const roles = document.getElementById('hiw-roles');
  const location = document.getElementById('hiw-location');
  const button = document.getElementById('hiw-generate');
  const resultsPanel = document.getElementById('hiw-results');
  if (!resume || !roles || !location || !button || !resultsPanel) return;

  const resumeText = resume.textContent;
  const rolesText = roles.textContent;
  const locationText = location.textContent;
  const results = Array.from(resultsPanel.querySelectorAll('.mockup-result'));

  resultsPanel.classList.add('js-animated');

  for (;;) {
    resume.textContent = '';
    roles.textContent = '';
    location.textContent = '';
    results.forEach((card) => card.classList.remove('is-visible'));

    await typeText(resume, resumeText, 18);
    await wait(250);
    await typeText(roles, rolesText, 35);
    await wait(250);
    await typeText(location, locationText, 35);
    await wait(400);

    button.classList.add('is-pressed');
    await wait(200);
    button.classList.remove('is-pressed');

    for (const card of results) {
      await wait(450);
      card.classList.add('is-visible');
    }

    await wait(3500);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (prefersReducedMotion) return;
  runHiwAnimation();
});
