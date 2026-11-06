"""Reversal in fear: a return-side factor signal for the ladders. Plan: research.md, "Follow-up: reversal in fear".

Day convention: panels are indexed by UTC day d, and close[d] is the price at the end of day d.
Everything used on day t is known at the start of day t.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

WINDOW, MIN_RETURNS = 180, 170
VOL_DAYS, MIN_QVOL = 30, 1e6
MIN_TOKENS = 50
CLIP = 3.0
FEAR, GREED = 35.0, 65.0
SLOPE_WINDOW, SLOPE_MIN = 365, 30


def signals(close: pd.DataFrame, qvol: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Clipped cross-sectional z-score of the reversal signal among eligible tokens, and each day's simple return."""
    close = close.asfreq("D")
    qvol = qvol.reindex(close.index)
    ret = close / close.shift(1) - 1.0
    n_ok = ret.notna().rolling(WINDOW, min_periods=1).sum().shift(1)
    med_vol = qvol.rolling(VOL_DAYS, min_periods=20).median().shift(1)
    raw = -(close.shift(2) / close.shift(22) - 1.0)
    elig = (n_ok >= MIN_RETURNS) & (med_vol >= MIN_QVOL) & close.shift(1).notna() & raw.notna()
    s = raw.where(elig)
    n = s.notna().sum(axis=1)
    z = s.sub(s.mean(axis=1), axis=0).div(s.std(axis=1), axis=0).clip(-CLIP, CLIP)
    z[n < MIN_TOKENS] = np.nan
    return z, ret


def daily_slopes(z: pd.DataFrame, ret: pd.DataFrame) -> pd.Series:
    """OLS slope of each day's return on that day's signal across tokens (with an intercept)."""
    out = {}
    r = ret.reindex(index=z.index, columns=z.columns)
    for d in z.index:
        a, b = z.loc[d].to_numpy(), r.loc[d].to_numpy()
        ok = np.isfinite(a) & np.isfinite(b)
        if ok.sum() < MIN_TOKENS:
            continue
        a, b = a[ok], b[ok]
        va = np.var(a)
        if va > 0:
            out[d] = float(np.cov(a, b, bias=True)[0, 1] / va)
    return pd.Series(out, dtype=float).sort_index()


def regime_labels(fng: pd.Series) -> pd.Series:
    """Fear, neutral or greed for day t from the 30-day mean of the index through day t-1."""
    f = fng.reindex(pd.date_range(fng.index.min(), fng.index.max(), freq="D"))
    m = f.rolling(30, min_periods=20).mean().shift(1)
    lab = pd.Series(np.where(m < FEAR, "fear", np.where(m > GREED, "greed", "neutral")), index=m.index)
    return lab.where(m.notna())


def forecast_slopes(g: pd.Series, labels: pd.Series, window: int = SLOPE_WINDOW, min_n: int = SLOPE_MIN) -> pd.Series:
    """b_t: mean of earlier daily slopes within `window` days that share day t's regime label (0 if fewer than min_n)."""
    days = pd.date_range(g.index.min(), labels.index.max(), freq="D")
    lab_g = labels.reindex(g.index)
    out = pd.Series(np.nan, index=days)
    for t in days:
        lt = labels.get(t)
        if not isinstance(lt, str):
            continue
        past = g[(g.index < t) & (g.index >= t - pd.Timedelta(days=window))]
        same = past[lab_g.reindex(past.index) == lt]
        out[t] = float(same.mean()) if len(same) >= min_n else 0.0
    return out


def regime_means(g: pd.Series, labels: pd.Series, start: str, end: str, block: int = 10, n_boot: int = 2000, seed: int = 0) -> dict:
    """Mean daily slope by regime over [start, end], with a day-block bootstrap interval for fear minus greed."""
    s = g[(g.index >= start) & (g.index <= end)]
    lab = labels.reindex(s.index)
    out = {r: {"days": int((lab == r).sum()), "mean": float(s[lab == r].mean()) if (lab == r).any() else None}
           for r in ("fear", "neutral", "greed")}
    vals, labs = s.to_numpy(), lab.to_numpy()
    n = len(vals)
    if (lab == "fear").any() and (lab == "greed").any():
        rng = np.random.default_rng(seed)
        draws = []
        for _ in range(n_boot):
            starts = rng.integers(0, max(n - block + 1, 1), int(np.ceil(n / block)))
            idx = np.concatenate([np.arange(a, a + block) for a in starts])[:n]
            v, lb = vals[idx], labs[idx]
            if (lb == "fear").any() and (lb == "greed").any():
                draws.append(v[lb == "fear"].mean() - v[lb == "greed"].mean())
        d = np.array(draws)
        est = out["fear"]["mean"] - out["greed"]["mean"]
        out["fear_minus_greed"] = {"est": est, "lo": float(np.quantile(d, 0.025)), "hi": float(np.quantile(d, 0.975)),
                                   "p": float(max(2 * min((d <= 0).mean(), (d >= 0).mean()), 1 / n_boot))}
    return out
