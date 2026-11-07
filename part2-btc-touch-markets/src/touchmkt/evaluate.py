"""Tests and summaries. Plan: research.md, "Primary tests" and "Secondary"."""

from __future__ import annotations

import numpy as np
import pandas as pd

FEE = 0.07
EDGE = 0.04
CAPTURE, CAP = 0.5, 200.0
BLOCK, N_BOOT = 10, 2000


def block_draws(values: np.ndarray, days: np.ndarray, fn=np.mean, block: int = BLOCK, n_boot: int = N_BOOT, seed: int = 0) -> np.ndarray:
    """fn of resampled values, moving blocks of consecutive days (all rows of a day move together)."""
    u = np.sort(np.unique(days))
    pos = np.searchsorted(u, days)
    groups = [np.flatnonzero(pos == i) for i in range(len(u))]
    n = len(u)
    rng = np.random.default_rng(seed)
    out = np.empty(n_boot)
    for b in range(n_boot):
        starts = rng.integers(0, max(n - block + 1, 1), int(np.ceil(n / block)))
        idx = np.concatenate([np.arange(a, min(a + block, n)) for a in starts])[:n]
        take = np.concatenate([groups[i] for i in idx])
        out[b] = fn(values[take])
    return out


def test_mean(values: np.ndarray, days: np.ndarray) -> dict:
    draws = block_draws(values, days)
    est = float(values.mean())
    centered = draws - est
    p = float(max((np.abs(centered) >= abs(est)).mean(), 1 / N_BOOT))
    return {"est": est, "lo": float(np.quantile(draws, 0.025)), "hi": float(np.quantile(draws, 0.975)), "p": p,
            "n": int(len(values)), "days": int(len(np.unique(days)))}


def holm(tests: dict) -> dict:
    running = 0.0
    for i, k in enumerate(sorted(tests, key=lambda k: tests[k]["p"])):
        running = max(running, min(1.0, tests[k]["p"] * (len(tests) - i)))
        tests[k]["p_holm"] = running
    return tests


def event_means(tr: pd.DataFrame, cols: list[str], by: list[str] | None = None) -> pd.DataFrame:
    """Share-weighted mean of cols within each event (and extra keys), one row per group with its day."""
    keys = ["event", "day", "kind"] + (by or [])
    w = tr["size"].to_numpy()
    df = tr[keys].copy()
    for c in cols:
        df[c] = tr[c].to_numpy() * w
    df["w"] = w
    g = df.groupby(keys, as_index=False)[cols + ["w"]].sum()
    g[cols] = g[cols].div(g["w"], axis=0)
    return g.drop(columns="w")


def primary(tr: pd.DataFrame, fair: str = "FAIR") -> dict:
    tr = tr.assign(prem=tr["p"] - tr[fair], b_mkt=(tr["p"] - tr["y"]) ** 2, b_fair=(tr[fair] - tr["y"]) ** 2)
    pr = event_means(tr, ["prem"], ["direction"])
    out = {}
    for d in ("reach", "dip"):
        g = pr[pr["direction"] == d]
        out[f"{d} premium"] = test_mean(g["prem"].to_numpy(), g["day"].to_numpy())
    br = event_means(tr, ["b_mkt", "b_fair"])
    out["Brier market minus FAIR"] = test_mean((br["b_mkt"] - br["b_fair"]).to_numpy(), br["day"].to_numpy())
    out["Brier market minus FAIR"] |= {"market": float(br["b_mkt"].mean()), "fair": float(br["b_fair"].mean())}
    return holm(out)


def premium_table(tr: pd.DataFrame, by: str, fair: str = "FAIR") -> dict:
    out = {}
    for key, g in tr.groupby(by, observed=True):
        for d in ("reach", "dip"):
            gg = g[g["direction"] == d]
            if gg["event"].nunique() < 10:
                continue
            e = event_means(gg.assign(prem=gg["p"] - gg[fair]), ["prem"])
            out[f"{key}|{d}"] = test_mean(e["prem"].to_numpy(), e["day"].to_numpy())
    return out


def calibration(p: np.ndarray, y: np.ndarray, w: np.ndarray, edges=(0.03, 0.1, 0.2, 0.35, 0.5, 0.65, 0.8, 0.9, 0.971)) -> list[dict]:
    out = []
    for a, b in zip(edges[:-1], edges[1:]):
        m = (p >= a) & (p < b)
        if m.sum():
            out.append({"bucket": [a, b], "n": int(m.sum()), "mean_price": float(np.average(p[m], weights=w[m])),
                        "win_rate": float(np.average(y[m], weights=w[m]))})
    return out


def trade(tr: pd.DataFrame, fair: str = "FAIR") -> pd.DataFrame:
    q, p, y = tr[fair].to_numpy(), tr["p"].to_numpy(), tr["y"].to_numpy()
    fee = FEE * p * (1 - p)
    yes = q - p - fee >= EDGE
    no = (1 - q) - (1 - p) - fee >= EDGE
    cost_per = np.where(yes, p + fee, np.where(no, 1 - p + fee, np.nan))
    pay = np.where(yes, y, np.where(no, 1 - y, np.nan))
    n = np.minimum(CAPTURE * tr["size"].to_numpy(), CAP / cost_per)
    df = pd.DataFrame({"day": tr["day"].to_numpy(), "kind": tr["kind"].to_numpy(), "direction": tr["direction"].to_numpy(),
                       "side": np.where(yes, "yes", np.where(no, "no", "")), "cost": n * cost_per, "pnl": n * (pay - cost_per)})
    return df[df["side"] != ""]


def trade_summary(t: pd.DataFrame) -> dict:
    if t.empty:
        return {"trades": 0}
    d = t.groupby("day")[["cost", "pnl"]].sum()
    v = d.to_numpy()
    draws = block_draws(np.arange(len(v)), d.index.to_numpy(), fn=lambda ix: v[ix, 1].sum() / v[ix, 0].sum())
    return {"trades": int(len(t)), "days": int(len(d)), "cost": float(v[:, 0].sum()), "pnl": float(v[:, 1].sum()),
            "return": float(v[:, 1].sum() / v[:, 0].sum()), "lo": float(np.quantile(draws, 0.025)), "hi": float(np.quantile(draws, 0.975)),
            "yes_share": float((t["side"] == "yes").mean())}


def slope_test(df: pd.DataFrame, x: str, y: str) -> dict:
    df = df[np.isfinite(df[x]) & np.isfinite(df[y])]
    idx = np.arange(len(df))
    xs, ys = df[x].to_numpy(), df[y].to_numpy()
    est = float(np.polyfit(xs, ys, 1)[0])
    draws = block_draws(idx, df["day"].to_numpy(), fn=lambda ix: np.polyfit(xs[ix], ys[ix], 1)[0])
    p = float(max((np.abs(draws - est) >= abs(est)).mean(), 1 / N_BOOT))
    return {"slope": est, "lo": float(np.quantile(draws, 0.025)), "hi": float(np.quantile(draws, 0.975)), "p": p, "n": int(len(df))}
