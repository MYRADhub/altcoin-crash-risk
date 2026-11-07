/* Pure helpers for the touch-market deck. Same formulas as src/touchmkt/pricing.py (flat volatility). */
(() => {
/* Standard normal CDF (Abramowitz and Stegun 7.1.26, error below 1.5e-7). */
function normCdf(x) {
  const s = x < 0 ? -1 : 1;
  const z = Math.abs(x) / Math.SQRT2;
  const t = 1 / (1 + 0.3275911 * z);
  const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-z * z);
  return 0.5 * (1 + s * y);
}

/* P(finish beyond K): dist = log(K / S) (> 0 for an up strike), vol = daily volatility, days = horizon. */
function finishBeyond(dist, vol, days) {
  const w = vol * vol * days;
  const sd = Math.sqrt(w);
  return dist >= 0 ? normCdf((-dist - 0.5 * w) / sd) : normCdf((dist + 0.5 * w) / sd);
}

/* Twice the finish probability, capped at 1 (the reflection value). */
function touchReflect(dist, vol, days) {
  return Math.min(1, 2 * finishBeyond(dist, vol, days));
}

/* One-touch probability under driftless-price GBM (log drift -vol^2/2). */
function touchGBM(dist, vol, days) {
  const w = vol * vol * days;
  if (w <= 0) return 0;
  const sd = Math.sqrt(w);
  const nu = -0.5 * w;
  const b = dist;
  if (b >= 0) return normCdf((-b + nu) / sd) + Math.exp((2 * nu * b) / w) * normCdf((-b - nu) / sd);
  return normCdf((b - nu) / sd) + Math.exp((2 * nu * b) / w) * normCdf((b + nu) / sd);
}

/* Seeded random numbers (mulberry32) and a normal draw, for the simulated paths on the reflection slide. */
function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function normal(r) {
  return Math.sqrt(-2 * Math.log(1 - r())) * Math.cos(2 * Math.PI * r());
}

/* Simulate n log-price paths of `steps` steps over `days` with daily vol; count paths that touch and that finish above dist.
   jumpEvery > 0 adds a jump of +-jumpSize to a step with probability 1 / jumpEvery (synthetic, to show jumps break the 2x rule). */
function simulate({ n, steps, vol, days, dist, seed = 1, jumpEvery = 0, jumpSize = 0, keep = 0 }) {
  const r = rng(seed);
  const dt = days / steps;
  const s = vol * Math.sqrt(dt);
  let touched = 0;
  let finished = 0;
  const paths = [];
  for (let i = 0; i < n; i += 1) {
    let x = 0;
    let hit = false;
    const p = keep > i ? [[0, 0]] : null;
    for (let j = 1; j <= steps; j += 1) {
      x += -0.5 * s * s + s * normal(r);
      if (jumpEvery > 0 && r() < 1 / jumpEvery) x += (r() < 0.5 ? -1 : 1) * jumpSize;
      if (x >= dist) hit = true;
      if (p) p.push([j * dt, x]);
    }
    if (hit) touched += 1;
    if (x >= dist) finished += 1;
    if (p) paths.push({ p, hit });
  }
  return { touched: touched / n, finished: finished / n, paths };
}

const Touch = { normCdf, finishBeyond, touchReflect, touchGBM, simulate };
if (typeof module !== 'undefined') module.exports = Touch;
else globalThis.Touch = Touch;
})();
