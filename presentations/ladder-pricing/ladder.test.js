const test = require('node:test');
const assert = require('node:assert/strict');
const L = require('./ladder.js');
const D = require('./deck-data.js');

const close = (a, b, eps = 1e-6) => assert.ok(Math.abs(a - b) < eps, `${a} is not close to ${b}`);

test('t4 quantile matches scipy and inverts the cdf', () => {
  close(L.t4inv(0.01), -3.746947388);
  close(L.t4inv(0.3), -0.568649063);
  close(L.t4inv(0.5), 0);
  close(L.t4inv(0.9), 1.5332062741);
  for (const p of [0.02, 0.4, 0.77]) close(L.t4cdf(L.t4inv(p)), p, 1e-9);
});

test('own and mapped probabilities match the Python model', () => {
  close(L.pOwn(0.03, 0.04), 0.1743205697);
  close(L.pMapped(-0.02, 0.02, 1.6, 1.2, 0.015, 401), 0.7522068951, 1e-4);
  // With no BTC exposure the mapped model is the own model.
  close(L.pMapped(0.01, 0.02, 0, 0, 0.03), L.pOwn(0.01, 0.03), 1e-9);
});

test('fee and brier', () => {
  close(L.fee(0.5), 0.0175);
  close(L.brier(0.8, 1), 0.04);
});

test('generated data is complete', () => {
  assert.ok(D.primary.brier.MKT > D.primary.brier.FACTOR);
  for (const k of ['KXSOLD', 'KXXRPD', 'KXDOGED']) assert.ok(D.perCoin[k] && D.liquidity[k] > 0 && D.pnl[k].length > 10);
  assert.ok(D.example.pts.length > 20 && D.ethPts.length === 500);
  assert.ok(D.reversal.shiftCents >= 0 && D.longCheck.pooled.lo < D.longCheck.pooled.hi && D.longCheck.perCoin.DOGEUSDT);
  assert.equal(L.dayLabel(L.dayNumber('2026-03-15')), 'Mar 26');
});
