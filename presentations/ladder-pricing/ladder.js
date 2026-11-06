/* Pure helpers for the ladder pricing deck. The same formulas as src/ladderprice/pricing.py, for the interactive slides. */
(() => {
const T_SD = Math.SQRT2; // standard deviation of a unit-scale Student-t with 4 degrees of freedom

/* Cumulative probability of a Student-t with 4 degrees of freedom (closed form). */
function t4cdf(t) {
  const x = t / Math.sqrt(t * t + 4);
  return 0.5 + 0.75 * x * (1 - (x * x) / 3);
}

/* Quantile of a Student-t with 4 degrees of freedom (closed form). */
function t4inv(p) {
  if (p === 0.5) return 0;
  const a = 4 * p * (1 - p);
  const q = Math.cos(Math.acos(Math.sqrt(a)) / 3) / Math.sqrt(a);
  return Math.sign(p - 0.5) * 2 * Math.sqrt(q - 1);
}

/* P(log return > x) when the log return is a t(4) with standard deviation sd. */
function pOwn(x, sd) {
  return 1 - t4cdf(x / (sd / T_SD));
}

/* P(beta * r_btc + e > x): r_btc ~ t(4) with sd btcSd, e ~ t(4) with sd resSd, beta = betaDown when BTC falls. */
function pMapped(x, btcSd, betaDown, betaUp, resSd, n = 201) {
  let s = 0;
  for (let i = 0; i < n; i += 1) {
    const rb = (btcSd / T_SD) * t4inv((i + 0.5) / n);
    const b = rb < 0 ? betaDown : betaUp;
    s += 1 - t4cdf((x - b * rb) / (resSd / T_SD));
  }
  return s / n;
}

/* Brier score of one forecast. */
function brier(p, y) {
  return (p - y) ** 2;
}

/* Kalshi taker fee per contract at price p (dollars). */
function fee(p) {
  return 0.07 * p * (1 - p);
}

/* Days since 2025-01-01, for date axes. */
function dayNumber(iso) {
  return Math.round((Date.parse(`${iso}T00:00:00Z`) - Date.parse('2025-01-01T00:00:00Z')) / 864e5);
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
function dayLabel(n) {
  const d = new Date(Date.parse('2025-01-01T00:00:00Z') + n * 864e5);
  return `${MONTHS[d.getUTCMonth()]} ${String(d.getUTCFullYear()).slice(2)}`;
}

const Ladder = { T_SD, t4cdf, t4inv, pOwn, pMapped, brier, fee, dayNumber, dayLabel };
if (typeof module !== 'undefined') module.exports = Ladder;
else globalThis.Ladder = Ladder;
})();
