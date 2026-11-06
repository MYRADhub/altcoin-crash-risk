import numpy as np
import pandas as pd

from ladderprice import longcheck


def table(fear_slope, greed_slope, n_days=600, seed=0):
    rng = np.random.default_rng(seed)
    days = pd.date_range("2021-01-01", periods=n_days, freq="D")
    reg = np.where((np.arange(n_days) // 30) % 2 == 0, "fear", "greed")
    rows = []
    for c in ("A", "B", "C"):
        z = rng.normal(size=n_days)
        r = np.where(reg == "fear", fear_slope, greed_slope) * z + rng.normal(0, 0.03, n_days)
        rows.append(pd.DataFrame({"day": days, "coin": c, "z": z, "r": r, "regime": reg}))
    return pd.concat(rows, ignore_index=True)


def test_detects_planted_reversal_in_fear():
    out = longcheck.summarize(table(0.006, -0.004))
    assert abs(out["fear"]["slope"] - 0.006) < 0.002
    assert out["fear"]["p_one_sided"] < 0.01 and out["fear_minus_greed"]["p"] < 0.01
    assert np.isnan(out["neutral"]["slope"])


def test_no_effect_is_not_significant():
    out = longcheck.summarize(table(0.0, 0.0, seed=3))
    assert out["fear"]["p_one_sided"] > 0.05
    assert out["fear"]["lo"] < 0 < out["fear"]["hi"]


def test_panel_uses_same_day_return_and_drops_missing():
    days = pd.date_range("2021-01-01", periods=5, freq="D")
    z = pd.DataFrame({"X": [np.nan, 1.0, -1.0, 2.0, 0.5]}, index=days)
    ret = pd.DataFrame({"X": [0.0, 0.01, -0.02, np.nan, 0.03]}, index=days)
    labels = pd.Series(["fear"] * 5, index=days)
    df = longcheck.panel(z, ret, labels, ["X"], "2021-01-01", "2021-01-05")
    assert list(df["day"]) == [days[1], days[2], days[4]]
    assert np.allclose(df["r"], np.log1p([0.01, -0.02, 0.03]))
