const test = require('node:test');
const assert = require('node:assert/strict');
const T = require('./touch.js');
const D = require('./deck-data.js');

const close = (a, b, eps = 1e-6) => assert.ok(Math.abs(a - b) < eps, `${a} is not close to ${b}`);

test('normal cdf matches known values', () => {
  close(T.normCdf(0), 0.5);
  close(T.normCdf(1.96), 0.9750021, 1e-6);
  close(T.normCdf(-1), 0.1586553, 1e-6);
});

test('touch formulas match the Python model', () => {
  // pricing.touch_gbm('reach', 100, 104, 0.6^2 * 5/365) = 0.565183817
  close(T.touchGBM(Math.log(1.04), 0.6 / Math.sqrt(365), 5), 0.5651838170, 1e-6);
  // Reflection is twice the finish probability and never above 1.
  const d = Math.log(1.02);
  close(T.touchReflect(d, 0.03, 1), 2 * T.finishBeyond(d, 0.03, 1), 1e-12);
  assert.equal(T.touchReflect(-0.0001, 0.05, 3), 1); // a down strike just below spot: finishing below is over 50%, so the cap binds
  // A touch is always at least as likely as finishing beyond.
  for (const x of [-0.05, -0.01, 0.01, 0.05]) assert.ok(T.touchGBM(x, 0.03, 1) >= T.finishBeyond(x, 0.03, 1));
});

test('simulated paths touch about twice as often as they finish beyond', () => {
  const s = T.simulate({ n: 4000, steps: 400, vol: 0.03, days: 1, dist: 0.02, seed: 3 });
  assert.ok(s.touched / s.finished > 1.7 && s.touched / s.finished < 2.2, `ratio ${s.touched / s.finished}`);
  const j = T.simulate({ n: 4000, steps: 400, vol: 0.015, days: 1, dist: 0.02, seed: 3, jumpEvery: 100, jumpSize: 0.03 });
  assert.ok(j.touched / j.finished < s.touched / s.finished, 'jumps lower the ratio');
});

test('generated data is complete', () => {
  assert.ok(D.events > 300 && D.trades > 1e6);
  assert.ok(D.calibration.p.length >= 6 && D.calibration.FAIR.length >= 6);
  for (const k of ['primary', 'GBM barrier', 'digital lower bound']) assert.ok(D.premium[k].reach && D.premium[k].dip);
  assert.ok(D.kalshi.violations > D.kalshi.flat && D.kalshi.flat >= D.kalshi.executable);
});
