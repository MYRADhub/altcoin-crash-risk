/* Shared presentation engine. Decks call Viewer.present(slides) and use Viewer.kit for widgets. */

const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
const range = (a, b, n) => Array.from({ length: n + 1 }, (_, i) => a + ((b - a) * i) / n);
const money = (v) => {
  const a = Math.abs(v);
  const s = a >= 1e9 ? `${(a / 1e9).toFixed(2)}bn` : a >= 1e6 ? `${(a / 1e6).toFixed(2)}m` : a >= 1e3 ? Math.round(a).toLocaleString('en-US') : a.toFixed(0);
  return `${v < 0 ? '-' : ''}$${s}`;
};
const pct = (v, d = 2) => `${v.toFixed(d)}%`;

/* Sliders. Each chip below animates sliders to a preset, so the chart moves on its own. */
function Controls(host, defs, onChange) {
  const vals = {};
  const parts = {};
  const paint = (k) => {
    const { input, def, out } = parts[k];
    const v = +input.value;
    vals[k] = v;
    out.textContent = def.fmt(v);
    input.style.setProperty('--p', `${((v - def.min) / (def.max - def.min)) * 100}%`);
  };
  defs.forEach((def) => {
    const id = `ctl-${def.id}`;
    const label = document.createElement('label');
    label.className = 'ctl';
    label.htmlFor = id;
    label.innerHTML = `<span>${def.label}</span><output></output><input type="range" id="${id}" min="${def.min}" max="${def.max}" step="${def.step}" value="${def.val}" style="--tone:var(--${def.tone || 'ink'})">`;
    host.appendChild(label);
    const input = label.querySelector('input');
    parts[def.k] = { input, def, out: label.querySelector('output') };
    paint(def.k);
    input.addEventListener('input', () => { paint(def.k); onChange(); });
    input.addEventListener('pointerup', () => input.blur());
  });
  let frame;
  return {
    vals,
    animate(target, ms = 650) {
      cancelAnimationFrame(frame);
      const from = Object.fromEntries(Object.keys(target).map((k) => [k, vals[k]]));
      const apply = (t) => {
        Object.entries(target).forEach(([k, to]) => {
          const { def, input } = parts[k];
          const raw = from[k] + (to - from[k]) * t;
          input.value = t >= 1 ? to : Math.round(raw / def.step) * def.step;
          paint(k);
        });
        onChange();
      };
      if (reduced) return apply(1);
      const start = performance.now();
      const step = (now) => {
        const p = Math.min(1, (now - start) / ms);
        apply(1 - Math.pow(1 - p, 3));
        if (p < 1) frame = requestAnimationFrame(step);
      };
      frame = requestAnimationFrame(step);
    },
  };
}

function Chips(host, label, items, controls, after) {
  host.innerHTML = `<span class="chips-label">${label}</span>${items.map((x, i) => `<button class="chip" type="button" data-i="${i}">${x[0]}</button>`).join('')}`;
  host.addEventListener('click', (e) => {
    const b = e.target.closest('.chip');
    if (!b) return;
    [...host.querySelectorAll('.chip')].forEach((c) => c.classList.toggle('on', c === b));
    controls.animate(items[+b.dataset.i][1]);
    if (after) after(+b.dataset.i);
  });
}

/* Stat tiles whose numbers glide to their new value. */
function Stats(host) {
  const cells = [];
  let raf = null;
  const tick = () => {
    let moving = false;
    cells.forEach((c) => {
      if (c.fmt === null) return;
      const gap = c.target - c.cur;
      if (Math.abs(gap) < 1e-6 * Math.max(1, Math.abs(c.target)) || reduced) c.cur = c.target;
      else { c.cur += gap * 0.32; moving = true; }
      c.el.textContent = c.fmt(c.cur);
    });
    raf = moving ? requestAnimationFrame(tick) : null;
  };
  return (items) => {
    if (cells.length !== items.length) {
      host.innerHTML = items.map(([l]) => `<div class="stat"><span>${l}</span><b></b></div>`).join('');
      cells.length = 0;
      [...host.children].forEach((node, i) => cells.push({ node, el: node.querySelector('b'), cur: typeof items[i][1] === 'number' ? items[i][1] : 0, target: 0, fmt: null }));
    }
    items.forEach(([, value, fmt, tone], i) => {
      const c = cells[i];
      c.node.className = `stat ${tone || ''}`;
      if (typeof value === 'number') { c.target = value; c.fmt = fmt; }
      else { c.fmt = null; c.el.textContent = value; }
    });
    if (!raf) raf = requestAnimationFrame(tick);
  };
}

function niceTicks(a, b, n) {
  const raw = (b - a || 1) / n;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
  const out = [];
  for (let v = Math.ceil(a / step) * step; v <= b + step * 1e-6; v += step) out.push(+v.toFixed(10));
  return out;
}

let clipSeq = 0;
function chart(el, o) {
  if (!el.clientWidth) return;
  const W = el.clientWidth;
  const compact = innerHeight < 760 && innerWidth > 900;
  const H = Math.round((o.h || 250) * (compact ? 0.78 : 1));
  const m = { l: 44, r: 12, t: 14, b: 37 };
  const [x0, x1] = o.x;
  const [y0, y1] = o.y;
  const px = (x) => m.l + ((x - x0) / (x1 - x0)) * (W - m.l - m.r);
  const py = (y) => H - m.b - ((y - y0) / (y1 - y0)) * (H - m.t - m.b);
  const id = `clip-${++clipSeq}`;
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${o.alt}"><defs><clipPath id="${id}"><rect x="${m.l}" y="${m.t - 6}" width="${W - m.l - m.r}" height="${H - m.t - m.b + 8}"/></clipPath></defs>`;
  niceTicks(y0, y1, o.yn || 4).forEach((t) => {
    s += `<line x1="${m.l}" x2="${W - m.r}" y1="${py(t)}" y2="${py(t)}" style="stroke:var(--line)"/><text x="${m.l - 7}" y="${py(t) + 4}" text-anchor="end">${(o.yf || String)(t)}</text>`;
  });
  niceTicks(x0, x1, W < 480 ? 4 : 6).forEach((t) => {
    s += `<text x="${px(t)}" y="${H - m.b + 16}" text-anchor="middle">${(o.xf || String)(t)}</text>`;
  });
  s += `<text x="${(m.l + W - m.r) / 2}" y="${H - 3}" text-anchor="middle">${o.xl}</text><text x="${m.l + 5}" y="${m.t + 3}">${o.yl}</text><g clip-path="url(#${id})">`;
  (o.bars || []).forEach((b) => {
    const top = py(Math.max(b.y, 0));
    const h = Math.abs(py(b.y) - py(0));
    s += `<rect x="${px(b.x) - b.w / 2}" y="${top}" width="${b.w}" height="${h}" rx="${Math.min(b.w / 2, 2)}" style="fill:var(--${b.c});opacity:${b.o || 1}"/>`;
  });
  (o.areas || []).forEach((a) => {
    const base = py(a.base ?? y0);
    const pts = a.p.map((q) => `${px(q[0]).toFixed(1)},${py(q[1]).toFixed(1)}`).join(' ');
    s += `<polygon points="${px(a.p[0][0])},${base} ${pts} ${px(a.p[a.p.length - 1][0])},${base}" style="fill:var(--${a.c});opacity:.12"/>`;
  });
  (o.v || []).forEach((v) => {
    s += `<line x1="${px(v.x)}" x2="${px(v.x)}" y1="${m.t}" y2="${H - m.b}" style="stroke:var(--${v.c || 'muted'});stroke-dasharray:3 4"/>`;
  });
  if (o.zero) s += `<line x1="${m.l}" x2="${W - m.r}" y1="${py(0)}" y2="${py(0)}" style="stroke:var(--muted)"/>`;
  (o.series || []).forEach((a) => {
    s += `<polyline fill="none" stroke-linejoin="round" stroke-linecap="round" points="${a.p.map((q) => `${px(q[0]).toFixed(1)},${py(q[1]).toFixed(1)}`).join(' ')}" style="stroke:var(--${a.c || 'ink'});stroke-width:${a.w || 2};${a.d ? `stroke-dasharray:${a.d}` : ''};opacity:${a.o || 1}"/>`;
  });
  (o.pts || []).forEach((q) => {
    s += `<circle cx="${px(q.x)}" cy="${py(q.y)}" r="${q.r || 4}" style="fill:var(--${q.c || 'ink'});${q.ring ? 'stroke:var(--panel);stroke-width:2.5' : ''}"/>`;
  });
  s += '</g>';
  (o.labels || []).forEach((l) => {
    s += `<text class="lbl" x="${px(l.x) + (l.dx || 0)}" y="${py(l.y) + (l.dy || 0)}" text-anchor="${l.a || 'start'}" style="fill:var(--${l.c || 'ink'})">${l.t}</text>`;
  });
  el.innerHTML = `${s}</svg>`;
}

const q = (root, sel) => root.querySelector(sel);

function saveProgress(key, id, index, total) {
  try { localStorage.setItem(`deck-progress:${key}`, JSON.stringify({ id, index, total })); } catch { /* storage unavailable */ }
}

function present(slides, meta) {
  const stage = document.getElementById('stage');
  let current = -1;
  const renderers = new Map();

  slides.forEach((s, i) => {
    const el = document.createElement('section');
    el.className = 'slide';
    el.id = `slide-${s.id}`;
    el.setAttribute('aria-label', s.title);
    if (s.html) {
      el.innerHTML = s.html;
    } else {
      el.innerHTML = `<div class="inner ${s.solo ? 'solo' : ''}"><div class="copy"><div class="kicker">${s.kicker}</div><h2 class="title">${s.title}</h2>${s.body ? `<div class="prose">${s.body}</div>` : ''}${s.deep ? `<details class="deep"><summary>Go deeper</summary><div class="more">${s.deep}</div></details>` : ''}</div><div class="lab">${s.lab}</div></div>`;
    }
    stage.appendChild(el);
    s.el = el;
    s.index = i;
  });

  const dots = document.getElementById('dots');
  dots.innerHTML = slides.map((s, i) => `<button class="dot" type="button" data-i="${i}" title="${i + 1}. ${s.title}" aria-label="Slide ${i + 1}: ${s.title}"></button>`).join('');
  const gridEl = document.getElementById('overview-grid');
  gridEl.innerHTML = slides.map((s, i) => `<button class="tile" type="button" data-i="${i}"><small>${String(i + 1).padStart(2, '0')}${s.kicker ? ` · ${s.kicker}` : ''}</small><b>${s.title}</b></button>`).join('');

  function ensure(s) {
    if (renderers.has(s.id)) return;
    const render = s.init ? s.init(s.el) : null;
    renderers.set(s.id, render || null);
  }

  function go(i, { push = true } = {}) {
    const n = Math.max(0, Math.min(slides.length - 1, i));
    if (n === current) return;
    const back = n < current;
    if (current >= 0) slides[current].el.classList.remove('active');
    const s = slides[n];
    s.el.classList.toggle('from-left', back);
    s.el.classList.add('active');
    s.el.scrollTop = 0;
    current = n;
    ensure(s);
    const render = renderers.get(s.id);
    if (render) render();
    if (push) { try { history.replaceState(null, '', `#${s.id}`); } catch { location.hash = s.id; } }
    document.getElementById('progress-fill').style.width = `${(n / (slides.length - 1)) * 100}%`;
    document.getElementById('count').textContent = `${n + 1} / ${slides.length}`;
    [...dots.children].forEach((d, j) => { d.classList.toggle('done', j < n); d.classList.toggle('now', j === n); });
    [...gridEl.children].forEach((t, j) => t.classList.toggle('now', j === n));
    document.getElementById('prev').disabled = n === 0;
    document.getElementById('next').disabled = n === slides.length - 1;
    document.title = n === 0 ? meta.title : `${s.title} | ${meta.title}`;
    saveProgress(meta.key, s.id, n, slides.length);
  }

  const overview = document.getElementById('overview');
  const toggleOverview = (show = overview.hidden) => { overview.hidden = !show; };
  const fullscreen = () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen?.().catch(() => {});
  };

  document.getElementById('prev').addEventListener('click', () => go(current - 1));
  document.getElementById('next').addEventListener('click', () => go(current + 1));
  stage.addEventListener('click', (e) => { if (e.target.closest('[data-next]')) go(current + 1); });
  document.getElementById('theme-btn').addEventListener('click', Theme.toggle);
  document.getElementById('full-btn').addEventListener('click', fullscreen);
  document.getElementById('overview-btn').addEventListener('click', () => toggleOverview());
  document.getElementById('overview-close').addEventListener('click', () => toggleOverview(false));
  dots.addEventListener('click', (e) => { const d = e.target.closest('.dot'); if (d) go(+d.dataset.i); });
  gridEl.addEventListener('click', (e) => { const t = e.target.closest('.tile'); if (t) { toggleOverview(false); go(+t.dataset.i); } });

  addEventListener('keydown', (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const tag = e.target.tagName;
    const typing = tag === 'INPUT' && e.target.type !== 'range';
    if (typing) return;
    const onRange = tag === 'INPUT';
    const onControl = tag === 'BUTTON' || tag === 'SUMMARY' || tag === 'A';
    switch (e.key) {
      case 'ArrowRight': case 'PageDown': if (!onRange) { e.preventDefault(); go(current + 1); } break;
      case 'ArrowLeft': case 'PageUp': if (!onRange) { e.preventDefault(); go(current - 1); } break;
      case ' ': if (!onControl) { e.preventDefault(); go(current + (e.shiftKey ? -1 : 1)); } break;
      case 'Home': if (!onRange) { e.preventDefault(); go(0); } break;
      case 'End': if (!onRange) { e.preventDefault(); go(slides.length - 1); } break;
      case 'o': case 'O': toggleOverview(); break;
      case 't': case 'T': Theme.toggle(); break;
      case 'f': case 'F': fullscreen(); break;
      case 'Escape': toggleOverview(false); break;
      default:
    }
  });

  let touch = null;
  stage.addEventListener('touchstart', (e) => {
    const t = e.touches[0];
    touch = e.target.closest('input, svg, .table-wrap, .terms') ? null : { x: t.clientX, y: t.clientY };
  }, { passive: true });
  stage.addEventListener('touchend', (e) => {
    if (!touch) return;
    const t = e.changedTouches[0];
    const dx = t.clientX - touch.x;
    const dy = t.clientY - touch.y;
    if (Math.abs(dx) > 70 && Math.abs(dx) > Math.abs(dy) * 1.6) go(current + (dx < 0 ? 1 : -1));
    touch = null;
  }, { passive: true });

  let resizeTimer;
  addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { const r = renderers.get(slides[current].id); if (r) r(); }, 120);
  });

  const fromHash = () => {
    const i = slides.findIndex((s) => s.id === location.hash.slice(1));
    return i >= 0 ? i : 0;
  };
  addEventListener('hashchange', () => go(fromHash(), { push: false }));
  go(fromHash(), { push: false });
}

const Viewer = { present, kit: { Controls, Chips, Stats, chart, range, money, pct, q, reduced } };
