"""Long check: does reversal in fear predict the ladder coins' daily moves? Plan: research.md, "Long check".

    python -m ladderprice.cli long-check
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import reversal

COINS = ["SOLUSDT", "XRPUSDT", "DOGEUSDT"]
START, END = "2020-03-01", "2025-07-30"
REGIMES = ("fear", "neutral", "greed")
BLOCK, N_BOOT = 10, 2000
FEE_BAR, EDGE_BAR = 0.0013, 0.0043  # daily drift per unit of z needed to clear the fee, and the fee plus the 4-cent edge


def panel(z: pd.DataFrame, ret: pd.DataFrame, labels: pd.Series, coins: list[str] | None, start: str, end: str,
          demean: bool = False) -> pd.DataFrame:
    """Long table of (day, coin, z, log return, regime) for the given coins, or every eligible token if coins is None."""
    days = z.index[(z.index >= start) & (z.index <= end)]
    zz = z.loc[days] if coins is None else z.loc[days, [c for c in coins if c in z.columns]]
    rr = np.log1p(ret.reindex(index=days, columns=zz.columns))
    if demean:
        rr = rr.sub(rr.where(zz.notna()).mean(axis=1), axis=0)
    df = pd.DataFrame({"day": np.repeat(days.to_numpy(), zz.shape[1]), "coin": np.tile(zz.columns.to_numpy(), len(days)),
                       "z": zz.to_numpy().ravel(), "r": rr.to_numpy().ravel()})
    df["regime"] = labels.reindex(df["day"]).to_numpy()
    return df[np.isfinite(df["z"]) & np.isfinite(df["r"]) & df["regime"].isin(REGIMES)].reset_index(drop=True)


def slopes(df: pd.DataFrame) -> dict:
    """OLS slope of return on z within each regime (separate intercepts), same as one regression with interactions."""
    out = {}
    for r in REGIMES:
        g = df[df["regime"] == r]
        out[r] = float(np.polyfit(g["z"], g["r"], 1)[0]) if len(g) > 10 and g["z"].var() > 0 else np.nan
    return out


def bootstrap(df: pd.DataFrame, block: int = BLOCK, n_boot: int = N_BOOT, seed: int = 0) -> pd.DataFrame:
    """Slopes on moving-block resamples of days; all coins of a day move together."""
    days = np.sort(df["day"].unique())
    pos = {d: i for i, d in enumerate(days)}
    groups = df.groupby(df["day"].map(pos)).indices
    n = len(days)
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n_boot):
        starts = rng.integers(0, n - block + 1, int(np.ceil(n / block)))
        idx = np.concatenate([np.arange(a, a + block) for a in starts])[:n]
        take = np.concatenate([groups[i] for i in idx if i in groups])
        rows.append(slopes(df.iloc[take]))
    return pd.DataFrame(rows)


def summarize(df: pd.DataFrame) -> dict:
    est = slopes(df)
    b = bootstrap(df)
    fm = b["fear"] - b["greed"]
    d = est["fear"] - est["greed"]
    out = {"days": int(df["day"].nunique()), "rows": int(len(df)),
           "regime_days": {r: int(df.loc[df["regime"] == r, "day"].nunique()) for r in REGIMES}}
    for r in REGIMES:
        out[r] = {"slope": est[r], "lo": float(b[r].quantile(0.025)), "hi": float(b[r].quantile(0.975))}
    out["fear"]["p_one_sided"] = float(max((b["fear"] <= 0).mean(), 1 / N_BOOT))
    out["fear_minus_greed"] = {"est": d, "lo": float(fm.quantile(0.025)), "hi": float(fm.quantile(0.975)),
                               "p": float(max(2 * min((fm <= 0).mean(), (fm >= 0).mean()), 1 / N_BOOT))}
    return out


def run(close: pd.DataFrame, qvol: pd.DataFrame, fng: pd.Series, start: str = START, end: str = END) -> dict:
    z, ret = reversal.signals(close, qvol)
    labels = reversal.regime_labels(fng)
    primary = summarize(panel(z, ret, labels, COINS, start, end))
    f = primary["fear"]
    verdict = ("worth a ladder strategy" if f["p_one_sided"] < 0.05 and f["slope"] >= FEE_BAR else
               "significant but too small to clear fees" if f["p_one_sided"] < 0.05 else "not significant")
    return {"period": {"start": start, "end": end}, "primary": primary, "verdict": verdict,
            "bars": {"fee": FEE_BAR, "fee_plus_edge": EDGE_BAR},
            "per_coin": {c: summarize(panel(z, ret, labels, [c], start, end)) for c in COINS},
            "universe_demeaned": summarize(panel(z, ret, labels, None, start, end, demean=True))}
