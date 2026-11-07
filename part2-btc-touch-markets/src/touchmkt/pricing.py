"""Fair values for touch contracts from Deribit option trades. Plan: research.md, "Fair value from Deribit".

Units: time in years, volatility as a decimal, total variance w = vol^2 * time. Rates are ignored.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

YEAR = 365.0 * 24 * 3600
MIN_TRADES, MIN_STRIKES, MAX_K = 8, 4, 0.3


def black_call(f, k, w):
    """Undiscounted Black call price with total variance w."""
    f, k, w = np.asarray(f, float), np.asarray(k, float), np.maximum(np.asarray(w, float), 1e-12)
    s = np.sqrt(w)
    d1 = (np.log(f / k) + 0.5 * w) / s
    return f * norm.cdf(d1) - k * norm.cdf(d1 - s)


def fit_smile(logm: np.ndarray, w: np.ndarray, strikes: np.ndarray) -> tuple[float, float, float] | None:
    """Least-squares w(k) = a + b k + c k^2 on trades with |k| <= MAX_K; None if too few trades or strikes."""
    ok = np.isfinite(logm) & np.isfinite(w) & (np.abs(logm) <= MAX_K) & (w > 0)
    if ok.sum() < MIN_TRADES or len(np.unique(strikes[ok])) < MIN_STRIKES:
        return None
    x = logm[ok]
    a = np.column_stack([np.ones_like(x), x, x * x])
    coef, *_ = np.linalg.lstsq(a, w[ok], rcond=None)
    return float(coef[0]), float(coef[1]), float(coef[2])


def smile_w(coef: tuple[float, float, float], k) -> np.ndarray:
    k = np.clip(np.asarray(k, float), -MAX_K, MAX_K)  # flat beyond the fitted range
    return np.maximum(coef[0] + coef[1] * k + coef[2] * k * k, 1e-8)


def total_variance(k, t_end: float, fits: list[tuple[float, tuple]]) -> float:
    """Total variance at log-moneyness k for a horizon t_end (years), from fits [(tau, coef)] sorted by tau.

    Linear in time between the bracketing expiries; scaled in proportion to time before the first
    (w = w1 * t / tau1) and after the last (constant volatility).
    """
    if not fits:
        return np.nan
    taus = [t for t, _ in fits]
    ws = [float(smile_w(c, k)) for _, c in fits]
    if t_end <= taus[0]:
        return ws[0] * t_end / taus[0]
    if t_end >= taus[-1]:
        return ws[-1] * t_end / taus[-1]
    j = int(np.searchsorted(taus, t_end))
    t0, t1, w0, w1 = taus[j - 1], taus[j], ws[j - 1], ws[j]
    return w0 + (w1 - w0) * (t_end - t0) / (t1 - t0)


def digital_above(s: float, k: float, t_end: float, fits, ref: float, h: float = 1e-3) -> float:
    """P(S_T > K) = -dC/dK, with the smile read at log(K / ref), by central difference."""
    def call(kk):
        return black_call(s, kk, total_variance(np.log(kk / ref), t_end, fits))

    return float(np.clip(-(call(k * (1 + h)) - call(k * (1 - h))) / (2 * k * h), 0.0, 1.0))


def touch_reflection(direction: str, digital_up: float) -> float:
    """FAIR = min(1, 2 x P(finish beyond K)): reach uses P(S_T > K), dip uses P(S_T < K)."""
    d = digital_up if direction == "reach" else 1.0 - digital_up
    return float(min(1.0, 2.0 * d))


def touch_gbm(direction: str, s: float, k: float, w: float) -> float:
    """One-touch probability under driftless-price GBM (log drift -vol^2/2), total variance w over the window."""
    if w <= 0:
        return float((direction == "reach" and s >= k) or (direction == "dip" and s <= k))
    sd = np.sqrt(w)
    b = np.log(k / s)
    nu = -0.5 * w  # log drift times T
    if direction == "reach":
        if b <= 0:
            return 1.0
        return float(norm.cdf((-b + nu) / sd) + np.exp(2 * nu * b / w) * norm.cdf((-b - nu) / sd))
    if b >= 0:
        return 1.0
    return float(norm.cdf((b - nu) / sd) + np.exp(2 * nu * b / w) * norm.cdf((b + nu) / sd))


def expiry_of(instrument: pd.Series) -> pd.Series:
    """Deribit instrument names -> expiry timestamps (08:00 UTC)."""
    d = pd.to_datetime(instrument.str.split("-").str[1], format="%d%b%y", errors="coerce")
    return d.dt.tz_localize("UTC") + pd.Timedelta(hours=8)


def grid_fits(trades: pd.DataFrame, grid: pd.DatetimeIndex, lookback: str = "60min") -> dict:
    """For each grid time: index price, and [(expiry, coef)] fitted on trades in the lookback window before it.

    trades needs columns t (UTC), instrument, iv (percent), index.
    """
    tr = trades.dropna(subset=["iv", "index"]).copy()
    tr["expiry"] = expiry_of(tr["instrument"])
    tr["strike"] = tr["instrument"].str.split("-").str[2].astype(float)
    tr = tr.sort_values("t").reset_index(drop=True)
    times = tr["t"].dt.tz_convert("UTC").dt.tz_localize(None).to_numpy()
    out = {}
    lb = pd.Timedelta(lookback)
    for g in grid:
        gn = g.tz_convert("UTC").tz_localize(None)
        i0, i1 = np.searchsorted(times, (gn - lb).to_datetime64(), "left"), np.searchsorted(times, gn.to_datetime64(), "left")
        if i1 - i0 < MIN_TRADES:
            continue
        win = tr.iloc[i0:i1]
        ref = float(win["index"].iloc[-1])
        fits = []
        for ex, e in win.groupby("expiry"):
            tau = (ex - g).total_seconds() / YEAR
            if tau <= 0:
                continue
            w = (e["iv"].to_numpy() / 100) ** 2 * tau
            coef = fit_smile(np.log(e["strike"].to_numpy() / e["index"].to_numpy()), w, e["strike"].to_numpy())
            if coef is not None:
                fits.append((ex, coef))
        if fits:
            out[g] = (ref, sorted(fits, key=lambda x: x[0]))
    return out
