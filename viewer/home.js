/* Lists every project and presentation found in the manifest. */
(() => {
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const progressOf = (key) => {
    try {
      const saved = JSON.parse(localStorage.getItem(`deck-progress:${key}`));
      return saved && saved.index > 0 ? saved : null;
    } catch {
      return null;
    }
  };

  const card = (project, deck) => {
    const key = `${project.slug}/${deck.id}`;
    const saved = progressOf(key);
    const href = `viewer/player.html?deck=${encodeURIComponent(key)}${saved ? `#${encodeURIComponent(saved.id)}` : ''}`;
    const share = saved ? ((saved.index + 1) / saved.total) * 100 : 0;
    return `<a class="deck-card" href="${href}">
      <h3>${esc(deck.title)}</h3>
      <p>${esc(deck.summary)}</p>
      ${saved ? `<div class="deck-progress"><i style="width:${share}%"></i></div>` : ''}
      <div class="deck-foot"><b>${saved ? `Continue at slide ${saved.index + 1} of ${saved.total}` : 'Start'}</b><span>${deck.minutes} min</span></div>
    </a>`;
  };

  const section = (project) => `<section class="project">
    <div class="project-head">
      <div class="pills"><span class="pill status">${esc(project.status)}</span><span class="pill">${esc(project.field)}</span></div>
      <h2>${esc(project.title)}</h2>
      <p>${esc(project.summary)}</p>
    </div>
    ${project.presentations.length
    ? `<div class="deck-grid">${project.presentations.map((d) => card(project, d)).join('')}</div>`
    : '<div class="empty-state"><b>No presentations yet</b>Add one under this project\'s presentations folder.</div>'}
  </section>`;

  const { projects = [] } = window.QUANT_MANIFEST || {};
  document.getElementById('projects').innerHTML = projects.length
    ? projects.map(section).join('')
    : '<div class="empty-state"><b>No projects found</b>Add a project.json and a deck under <code>presentations/</code>, then run <code>npm run manifest</code>.</div>';
  document.getElementById('theme-btn').addEventListener('click', Theme.toggle);
})();
