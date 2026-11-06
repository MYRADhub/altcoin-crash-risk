import numpy as np
import pandas as pd
import pytest
from scipy import stats

from ladderprice import build, evaluate, kalshi, pricing


def test_ticker_parsing():
    assert kalshi.is_five_pm("KXSOLD-26OCT2817") and not kalshi.is_five_pm("KXSOLD-26OCT2812")
    assert kalshi.event_date("KXXRPD-25DEC0917") == "2025-12-09"
    assert kalshi.event_date("KXETHD-ETH17") is None


def test_mapped_reduces_to_own_in_the_limits():
    x = np.array([-0.05, 0.0, 0.03])
    sd = np.full(3, 0.04)
    zero = np.zeros(3)
    assert np.allclose(pricing.p_mapped(x, sd, zero, zero, sd), pricing.p_own(x, sd))
    assert np.allclose(pricing.p_mapped(x, sd, np.ones(3), np.ones(3), np.full(3, 1e-9)), pricing.p_own(x, sd), atol=3e-3)


def test_mapped_matches_monte_carlo():
    rng = np.random.default_rng(0)
    n = 400_000
    bsd, rsd, bd, bu = 0.03, 0.02, 1.6, 1.1
    rb = bsd / pricing.T_SD * stats.t.rvs(4, size=n, random_state=rng)
    e = rsd / pricing.T_SD * stats.t.rvs(4, size=n, random_state=rng)
    ra = np.where(rb < 0, bd, bu) * rb + e
    for x in (-0.06, -0.01, 0.0, 0.04):
        got = pricing.p_mapped(np.array([x]), np.array([bsd]), np.array([bd]), np.array([bu]), np.array([rsd]))[0]
        assert got == pytest.approx((ra > x).mean(), abs=0.004)


def test_steeper_down_beta_fattens_the_left_tail():
    x = np.array([-0.05])
    args = (np.array([0.03]), np.array([0.02]))
    sym = pricing.p_mapped(x, args[0], np.array([1.2]), np.array([1.2]), args[1])
    crash = pricing.p_mapped(x, args[0], np.array([1.6]), np.array([1.2]), args[1])
    assert crash < sym  # a bigger chance of ending below -5%


def test_hourly_features_recover_beta_and_vols():
    rng = np.random.default_rng(1)
    n = 2000
    idx = pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC")
    b = rng.normal(0, 0.006, n)
    down = b < b.mean()
    a = np.where(down, 1.5, 1.0) * b + rng.normal(0, 0.001, n)
    f = pricing.hourly_features(pd.Series(a, idx), pd.Series(b, idx))
    last = f.iloc[-1]
    assert last["beta_down"] == pytest.approx(1.5, abs=0.12) and last["beta_up"] == pytest.approx(1.0, abs=0.12)
    assert last["own_sd"] == pytest.approx(np.sqrt(24) * a[-720:].std(), rel=0.2)
    assert np.isnan(f["beta"].iloc[700])


def test_hourly_features_use_only_the_past():
    rng = np.random.default_rng(2)
    idx = pd.date_range("2026-01-01", periods=1000, freq="h", tz="UTC")
    a, b = pd.Series(rng.normal(0, 0.01, 1000), idx), pd.Series(rng.normal(0, 0.01, 1000), idx)
    f1 = pricing.hourly_features(a, b)
    a2 = a.copy()
    a2.iloc[900:] *= 5
    f2 = pricing.hourly_features(a2, b)
    pd.testing.assert_series_equal(f1.iloc[899], f2.iloc[899])


def test_trailing_scale_uses_previous_days_and_recovers_scale():
    rng = np.random.default_rng(3)
    z = pd.Series(np.abs(2 * stats.t.rvs(4, size=3000, random_state=rng)), pd.date_range("2020-01-01", periods=3000))
    k = pricing.trailing_scale(z, window=2000)
    assert k.iloc[:60].isna().all()
    assert k.iloc[-1] == pytest.approx(2.0, rel=0.05)
    z2 = z.copy()
    z2.iloc[-1] = 1e6
    assert pricing.trailing_scale(z2, window=2000).iloc[-1] == k.iloc[-1]


def test_cell_table_uses_earlier_days_in_the_same_cell():
    days = pd.date_range("2026-01-01", periods=200)
    cells = pd.Series(["a" if i % 2 else "b" for i in range(200)], days)
    z = pd.Series(np.where(cells == "a", 2 * pricing.T_MAD, pricing.T_MAD), days)
    t = pricing.cell_table(z, cells, ["a", "b", "c"])
    assert (t.iloc[:40] == 1.0).all().all()
    assert t["a"].iloc[-1] == pytest.approx(2.0) and t["b"].iloc[-1] == pytest.approx(1.0) and t["c"].iloc[-1] == 1.0
    z2 = z.copy()
    z2.iloc[-1] = 1e6
    assert pricing.cell_table(z2, cells, ["a", "b"]).iloc[-1].tolist() == t[["a", "b"]].iloc[-1].tolist()


def test_asof_and_regime():
    s = pd.Series([1.0, 2.0, 3.0], pd.to_datetime(["2026-01-01 00:01", "2026-01-01 00:02", "2026-01-01 00:03"], utc=True))
    t = pd.Series(pd.to_datetime(["2026-01-01 00:00:30", "2026-01-01 00:02:00", "2026-01-01 00:02:59"], utc=True))
    out = build.asof(s, t)
    assert np.isnan(out[0]) and out[1] == 2.0 and out[2] == 2.0
    assert build.regime(20) == "fear" and build.regime(50) == "neutral" and build.regime(80) == "greed" and build.regime(np.nan) is None


def test_trade_rule_sides_and_pnl():
    prints = pd.DataFrame({"day": ["d1"] * 3, "series": ["S"] * 3, "p": [0.5, 0.5, 0.5], "y": [1.0, 0.0, 1.0],
                           "count": [100.0, 100.0, 100.0], "M": [0.8, 0.2, 0.52]})
    tr = evaluate.trade(prints, "M")
    assert tr["side"].tolist() == ["yes", "no"]
    fee = 0.07 * 0.25
    assert tr["cost"].iloc[0] == pytest.approx(50 * (0.5 + fee))
    assert tr["pnl"].iloc[0] == pytest.approx(50 * (1 - 0.5 - fee))


def test_day_block_bootstrap_constant_and_paired_test():
    v = np.ones(30)
    days = np.repeat(np.arange(10), 3)
    assert np.allclose(evaluate.day_block_bootstrap(v, days, block=3, n_boot=50), 1.0)
    ev = pd.DataFrame({"day": days, "A": np.zeros(30), "B": np.ones(30)})
    t = evaluate.paired_test(ev, "A", "B", n_boot=200)
    assert t["est"] == -1.0 and t["p"] <= 0.01


def test_event_scores_weight_by_contracts():
    prints = pd.DataFrame({"event": ["e"] * 2, "day": ["d"] * 2, "series": ["S"] * 2, "y": [1.0, 1.0],
                           "count": [99.0, 1.0], "M": [1.0, 0.0]})
    assert evaluate.event_scores(prints, ["M"])["M"].iloc[0] == pytest.approx(0.01)
    assert evaluate.event_scores(prints, ["M"], weighted=False)["M"].iloc[0] == pytest.approx(0.5)
