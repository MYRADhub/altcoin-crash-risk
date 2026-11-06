"""Fair values for "price above K at the close" contracts. Plan: research.md, "Test plan".

All distributions are Student-t with 4 degrees of freedom on log returns, with scale = sd / sqrt(2).
Every feature at time t uses only data up to t.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

DF = 4
T_SD = float(np.sqrt(DF / (DF - 2)))
T_MAD = float(stats.t.ppf(0.75, DF))
WINDOW_H = 720
HAR_H = (24, 168, 720)
GRID = 401
_Q = stats.t.ppf((np.arange(GRID) + 0.5) / GRID, DF)


def har_daily_var(r2_mean: dict[int, float]) -> float:
    """Daily variance from mean squared hourly returns over 1, 7 and 30 days (equal-weight mix)."""
    return float(np.mean([24 * r2_mean[h] for h in HAR_H]))


def hourly_features(alt: pd.Series, btc: pd.Series) -> pd.DataFrame:
    """Per hour close: OWN daily sd, beta, down and up betas, residual daily sd (HAR), using the 720 hours ending there.

    alt and btc are hourly log returns on the same index. Down hours are those with BTC below its window mean.
    """
    a, b = alt.to_numpy(), btc.to_numpy()
    n = len(a)
    cols = {k: np.full(n, np.nan) for k in ("own_sd", "beta", "alpha", "beta_down", "beta_up", "res_sd")}
    ok = np.isfinite(a) & np.isfinite(b)
    for i in range(WINDOW_H, n + 1):
        sl = slice(i - WINDOW_H, i)
        m = ok[sl]
        if m.sum() < WINDOW_H * 0.9:
            continue
        aw, bw = a[sl], b[sl]
        own = {h: np.nanmean(aw[-h:][ok[i - h:i]] ** 2) for h in HAR_H}
        x, y = bw[m], aw[m]
        xc = x - x.mean()
        beta = float(np.sum(xc * (y - y.mean())) / np.sum(xc * xc))
        alpha = float(y.mean() - beta * x.mean())
        down = x < x.mean()
        bd = np.polyfit(x[down], y[down], 1)[0] if down.sum() > 50 else beta
        bu = np.polyfit(x[~down], y[~down], 1)[0] if (~down).sum() > 50 else beta
        e = np.where(m, aw - alpha - beta * bw, np.nan)
        res = {h: np.nanmean(e[-h:] ** 2) for h in HAR_H}
        j = i - 1
        cols["own_sd"][j] = np.sqrt(har_daily_var(own))
        cols["beta"][j], cols["alpha"][j], cols["beta_down"][j], cols["beta_up"][j] = beta, alpha, bd, bu
        cols["res_sd"][j] = np.sqrt(har_daily_var(res))
    return pd.DataFrame(cols, index=alt.index)


def p_own(x: np.ndarray, sd_h: np.ndarray) -> np.ndarray:
    """P(log return > x) for a t(4) with standard deviation sd_h over the horizon."""
    return stats.t.sf(x / (sd_h / T_SD), DF)


def p_mapped(x: np.ndarray, btc_sd_h: np.ndarray, beta_down: np.ndarray, beta_up: np.ndarray, res_sd_h: np.ndarray,
             chunk: int = 20000) -> np.ndarray:
    """P(beta(r_b) * r_b + e > x), r_b ~ t(4) with sd btc_sd_h, e ~ t(4) with sd res_sd_h, beta by the sign of r_b.

    Integrates over BTC by GRID equal-probability quantiles.
    """
    out = np.empty(len(x))
    for s in range(0, len(x), chunk):
        sl = slice(s, s + chunk)
        rb = (btc_sd_h[sl, None] / T_SD) * _Q[None, :]
        beta = np.where(rb < 0, beta_down[sl, None], beta_up[sl, None])
        z = (x[sl, None] - beta * rb) / (res_sd_h[sl, None] / T_SD)
        out[sl] = stats.t.sf(z, DF).mean(axis=1)
    return out


def trailing_scale(z_abs: pd.Series, window: int = 90, min_n: int = 60) -> pd.Series:
    """Scale correction for each date: median |z| over the previous `window` dates / T_MAD; NaN before min_n."""
    med = z_abs.shift(1).rolling(window, min_periods=min_n).median()
    return med / T_MAD


def cell_table(z_abs: pd.Series, cells: pd.Series, all_cells: list[str], days: int = 365, min_n: int = 30) -> pd.DataFrame:
    """For each date and each cell: median |z| over earlier dates in that cell within `days`, / T_MAD.

    1.0 where fewer than min_n earlier dates exist. Dates are the index of z_abs (one per event day).
    """
    df = pd.DataFrame({"z": z_abs, "cell": cells}).sort_index()
    out = pd.DataFrame(1.0, index=df.index, columns=all_cells)
    for d in df.index:
        past = df[(df.index < d) & (df.index > d - pd.Timedelta(days=days))].dropna()
        for c, g in past.groupby("cell"):
            if c in out.columns and len(g) >= min_n:
                out.at[d, c] = float(g["z"].median() / T_MAD)
    return out
