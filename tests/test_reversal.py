import numpy as np
import pandas as pd

from ladderprice import pricing, reversal


def panel(n_tok=80, n_days=400, slope=0.0, seed=0):
    rng = np.random.default_rng(seed)
    days = pd.date_range("2024-01-01", periods=n_days, freq="D")
    r = rng.normal(0, 0.03, (n_days, n_tok))
    close = pd.DataFrame(100 * np.exp(np.cumsum(r, axis=0)), index=days, columns=[f"T{i}USDT" for i in range(n_tok)])
    qvol = pd.DataFrame(5e6, index=days, columns=close.columns)
    return close, qvol


def test_signal_is_standardized_and_needs_history():
    close, qvol = panel()
    z, _ = reversal.signals(close, qvol)
    assert z.iloc[:reversal.MIN_RETURNS].isna().all().all()
    row = z.iloc[-1].dropna()
    assert len(row) == 80 and abs(row.mean()) < 0.05 and abs(row.std() - 1) < 0.1 and row.abs().max() <= reversal.CLIP


def test_signal_is_point_in_time():
    close, qvol = panel()
    z0, _ = reversal.signals(close, qvol)
    t = close.index[300]
    bumped = close.copy()
    bumped.loc[t:, "T0USDT"] *= 3.0  # a jump on day t and after
    z1, _ = reversal.signals(bumped, qvol)
    pd.testing.assert_frame_equal(z0.loc[:close.index[301]], z1.loc[:close.index[301]])  # visible from day t+2 only
    assert z1.loc[close.index[302], "T0USDT"] < z0.loc[close.index[302], "T0USDT"]


def test_thin_tokens_are_not_eligible():
    close, qvol = panel()
    qvol["T1USDT"] = 1e5
    z, _ = reversal.signals(close, qvol)
    assert z["T1USDT"].isna().all()


def test_daily_slope_recovers_planted_reversal():
    close, qvol = panel(n_tok=200)
    z, ret = reversal.signals(close, qvol)
    rng = np.random.default_rng(1)
    planted = 0.004 * z + rng.normal(0, 0.01, z.shape)
    g = reversal.daily_slopes(z, planted.where(z.notna()))
    assert abs(g.mean() - 0.004) < 0.0005


def test_regime_label_uses_only_earlier_days():
    days = pd.date_range("2024-01-01", periods=100, freq="D")
    fng = pd.Series(20.0, index=days)
    lab = reversal.regime_labels(fng)
    assert lab.iloc[:20].isna().all() and (lab.iloc[25:] == "fear").all()
    fng2 = fng.copy()
    fng2.iloc[60:] = 90.0
    lab2 = reversal.regime_labels(fng2)
    assert lab2.iloc[60] == "fear" and lab2.iloc[99] == "greed"


def test_forecast_slope_matches_regime_and_needs_enough_days():
    days = pd.date_range("2024-01-01", periods=200, freq="D")
    labels = pd.Series(["fear"] * 100 + ["greed"] * 100, index=days)
    g = pd.Series(np.where(np.arange(200) < 100, 0.01, -0.02), index=days)
    b = reversal.forecast_slopes(g, labels, min_n=30)
    assert b.iloc[10] == 0.0 and b.iloc[50] == 0.01  # too few fear days, then enough
    assert b.iloc[110] == 0.0 and b.iloc[140] == -0.02  # greed uses greed days only
    g2 = g.copy()
    g2.iloc[150:] = 5.0
    assert reversal.forecast_slopes(g2, labels, min_n=30).iloc[150] == b.iloc[150]  # day t's own slope is not used


def test_positive_drift_raises_the_probability():
    x = np.array([0.0, 0.02])
    args = (np.array([0.02, 0.02]), np.array([1.2, 1.2]), np.array([1.0, 1.0]), np.array([0.02, 0.02]))
    assert (pricing.p_mapped(x - 0.005, *args) > pricing.p_mapped(x, *args)).all()


def test_regime_means_reports_fear_minus_greed():
    days = pd.date_range("2024-01-01", periods=300, freq="D")
    labels = pd.Series(np.where(np.arange(300) % 20 < 10, "fear", "greed"), index=days)
    g = pd.Series(np.where(labels == "fear", 0.003, -0.001), index=days) + np.random.default_rng(0).normal(0, 0.001, 300)
    out = reversal.regime_means(g, labels, "2024-01-01", "2024-12-31")
    assert abs(out["fear_minus_greed"]["est"] - 0.004) < 0.0005 and out["fear_minus_greed"]["p"] < 0.01
