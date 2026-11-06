/* Light and dark theme, shared by the home page and player. Loaded in <head> to avoid a flash. */
const Theme = (() => {
  const KEY = 'deck-theme';
  const root = document.documentElement;
  try {
    const saved = localStorage.getItem(KEY);
    if (saved) root.dataset.theme = saved;
  } catch { /* storage unavailable */ }
  const isDark = () => (root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches);
  return {
    toggle() {
      const next = isDark() ? 'light' : 'dark';
      root.dataset.theme = next;
      try { localStorage.setItem(KEY, next); } catch { /* storage unavailable */ }
    },
  };
})();
