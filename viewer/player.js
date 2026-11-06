/* Finds the requested deck in the manifest, then loads that deck's scripts. */
(() => {
  const showError = (title, text) => {
    document.getElementById('stage').innerHTML = `<div class="deck-error"><h2>${title}</h2><p>${text}</p><a class="chip big" style="width:fit-content;text-decoration:none" href="../index.html">Back to presentations</a></div>`;
    document.querySelector('.dock').hidden = true;
  };

  const key = new URLSearchParams(location.search).get('deck');
  const manifest = window.QUANT_MANIFEST || { projects: [] };
  let deck = null;
  manifest.projects.forEach((project) => project.presentations.forEach((p) => {
    if (`${project.slug}/${p.id}` === key) deck = p;
  }));
  if (!deck) {
    showError('Presentation not found', 'It may have been moved or renamed. Pick another from the list.');
    return;
  }

  document.title = deck.title;
  const present = Viewer.present;
  let started = false;
  Viewer.present = (slides) => {
    started = true;
    present(slides, { key, title: deck.title });
  };

  const load = (i) => {
    if (i >= deck.scripts.length) {
      if (!started) showError('This presentation did not start', 'Its slide file never called Viewer.present.');
      return;
    }
    const script = document.createElement('script');
    script.src = `../${deck.path}/${deck.scripts[i]}`;
    script.onload = () => load(i + 1);
    script.onerror = () => showError('Could not load this presentation', `Missing file: ${deck.scripts[i]}`);
    document.body.appendChild(script);
  };
  load(0);
})();
