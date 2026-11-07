import numpy as np
import pandas as pd
from scipy.stats import norm

from touchmkt import pricing as P

FLAT = lambda vol, tau: [(tau, (vol * vol * tau, 0.0, 0.0))]


def test_digital_matches_black_with_flat_vol():
    s, k, vol, t = 100.0, 105.0, 0.5, 7 / 365
    w = vol * vol * t
    d2 = (np.log(s / k) - 0.5 * w) / np.sqrt(w)
    assert abs(P.digital_above(s, k, t, FLAT(vol, t), ref=s) - norm.cdf(d2)) < 1e-5


def test_negative_skew_raises_the_digital_call():
    # With volatility rising as the strike falls, -dC/dK gains -vega * dvol/dK > 0: the digital call is worth more.
    t = 7 / 365
    flat = [(t, (0.25 * t, 0.0, 0.0))]
    skew = [(t, (0.25 * t, -0.2 * t, 0.0))]  # vol rises as the strike falls
    assert P.digital_above(100, 95, t, skew, ref=100) > P.digital_above(100, 95, t, flat, ref=100)


def test_gbm_touch_matches_monte_carlo_and_reflection():
    rng = np.random.default_rng(0)
    s, k, vol, t, n = 100.0, 104.0, 0.6, 5 / 365, 2000
    w = vol * vol * t
    dt = t / n
    paths = np.cumsum(-0.5 * vol * vol * dt + vol * np.sqrt(dt) * rng.standard_normal((20000, n)), axis=1)
    mc = (paths.max(axis=1) >= np.log(k / s)).mean()
    exact = P.touch_gbm("reach", s, k, w)
    assert abs(exact - mc) < 0.015  # discrete monitoring makes MC slightly lower
    d = P.digital_above(s, k, t, FLAT(vol, t), ref=s)
    assert abs(P.touch_reflection("reach", d) - exact) < 0.02  # 2 x digital is within about a cent for short horizons


def test_touch_bounds_and_edges():
    assert P.touch_gbm("reach", 100, 99, 0.01) == 1.0 and P.touch_gbm("dip", 100, 101, 0.01) == 1.0
    assert P.touch_gbm("reach", 100, 110, 0.0) == 0.0
    d = 0.3
    assert P.touch_reflection("reach", d) == 0.6 and P.touch_reflection("dip", d) == 1.0
    for k in (90.0, 97.0):
        dn = 1 - P.digital_above(100, k, 0.02, FLAT(0.5, 0.02), ref=100)
        assert P.touch_gbm("dip", 100, k, 0.25 * 0.02) >= dn  # touching is at least as likely as finishing beyond


def test_total_variance_interpolates_in_time():
    fits = [(0.01, (0.0004, 0.0, 0.0)), (0.03, (0.0016, 0.0, 0.0))]
    assert abs(P.total_variance(0.0, 0.02, fits) - 0.001) < 1e-12
    assert abs(P.total_variance(0.0, 0.005, fits) - 0.0002) < 1e-12  # before the first expiry: in proportion
    assert abs(P.total_variance(0.0, 0.06, fits) - 0.0032) < 1e-12  # after the last: constant vol


def test_smile_fit_recovers_quadratic_and_needs_enough_strikes():
    k = np.linspace(-0.2, 0.2, 12)
    w = 0.002 - 0.001 * k + 0.01 * k * k
    a, b, c = P.fit_smile(k, w, np.arange(12.0))
    assert abs(a - 0.002) < 1e-9 and abs(b + 0.001) < 1e-9 and abs(c - 0.01) < 1e-9
    assert P.fit_smile(k, w, np.array([1.0, 2.0, 3.0] * 4)) is None


def test_grid_fits_use_only_past_trades():
    t0 = pd.Timestamp("2026-01-05 12:00", tz="UTC")
    rows = []
    for i in range(30):
        strike = 90000 + 2000 * (i % 6)
        rows.append({"t": t0 - pd.Timedelta(minutes=50 - i), "instrument": f"BTC-9JAN26-{strike}-C", "iv": 50.0, "index": 95000.0})
    late = {"t": t0 + pd.Timedelta(minutes=1), "instrument": "BTC-9JAN26-96000-C", "iv": 500.0, "index": 95000.0}
    tr = pd.DataFrame(rows + [late] * 20)
    fits = P.grid_fits(tr, pd.DatetimeIndex([t0]))
    ref, f = fits[t0]
    tau = (pd.Timestamp("2026-01-09 08:00", tz="UTC") - t0).total_seconds() / P.YEAR
    assert ref == 95000.0 and abs(np.sqrt(P.smile_w(f[0][1], 0.0) / tau) - 0.5) < 1e-6
