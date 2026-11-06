"""Scores, bootstrap tests and the trading rule. Plan: research.md, "Scores"."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

MODELS = ["MKT", "OWN", "BETA", "CRASH", "FACTOR"]
PRIMARY = ["MKT", "OWN", "BETA"]
FEE = 0.07
EDGE = 0.04
CAPTURE = 0.5
CAP = 200.0


def brier(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    return (p - y) ** 2


def log_loss(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def event_scores(prints: pd.DataFrame, models: list[str], fn=brier, weighted: bool = True) -> pd.DataFrame:
    """Mean score per event, one row per event with its day and series.

    Prints are weighted by contracts traded within each event (primary) or equally (weighted=False).
    """
    y = prints["y"].to_numpy()
    w = prints["count"].to_numpy() if weighted else np.ones(len(prints))
    df = pd.DataFrame({m: fn(prints[m].to_numpy(), y) * w for m in models})
    df["w"] = w
    df["event"], df["day"], df["series"] = prints["event"].to_numpy(), prints["day"].to_numpy(), prints["series"].to_numpy()
    g = df.groupby(["event", "day", "series"], as_index=False)[models + ["w"]].sum()
    g[models] = g[models].div(g["w"], axis=0)
    return g.drop(columns="w").sort_values("day").reset_index(drop=True)


def day_block_bootstrap(values: np.ndarray, days: np.ndarray, block: int = 10, n_boot: int = 2000, seed: int = 0) -> np.ndarray:
    """Draws of the mean of `values` (one per event), resampling blocks of consecutive event days."""
    u = np.unique(days)
    pos = {d: i for i, d in enumerate(u)}
    by_day = [[] for _ in u]
    for i, d in enumerate(days):
        by_day[pos[d]].append(i)
    by_day = [np.array(b) for b in by_day]
    n = len(u)
    starts = np.arange(max(n - block + 1, 1))
    k = int(np.ceil(n / block))
    rng = np.random.default_rng(seed)
    draws = np.empty(n_boot)
    for b in range(n_boot):
        pick = (rng.choice(starts, k)[:, None] + np.arange(block)[None, :]).ravel()[:n]
        idx = np.concatenate([by_day[min(j, n - 1)] for j in pick])
        draws[b] = values[idx].mean()
    return draws


def paired_test(ev: pd.DataFrame, a: str, b: str, n_boot: int = 2000) -> dict:
    d = (ev[a] - ev[b]).to_numpy()
    draws = day_block_bootstrap(d, ev["day"].to_numpy(), n_boot=n_boot)
    p = 2 * min((draws >= 0).mean(), (draws <= 0).mean())
    return {"est": float(d.mean()), "lo": float(np.quantile(draws, 0.025)), "hi": float(np.quantile(draws, 0.975)),
            "p": float(max(p, 1 / n_boot))}


def holm(tests: dict) -> dict:
    running = 0.0
    for i, k in enumerate(sorted(tests, key=lambda k: tests[k]["p"])):
        running = max(running, min(1.0, tests[k]["p"] * (len(tests) - i)))
        tests[k]["p_holm"] = running
    return tests


def auc(p: np.ndarray, y: np.ndarray) -> float:
    r = stats.rankdata(p)
    n1 = int(y.sum())
    n0 = len(y) - n1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)) if n1 and n0 else float("nan")


def calibration(p: np.ndarray, y: np.ndarray, edges=(0.05, 0.15, 0.3, 0.5, 0.7, 0.85, 0.951)) -> list[dict]:
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        s = (p >= lo) & (p < hi)
        if s.any():
            out.append({"bin": f"{lo:.2f}-{hi:.2f}", "n": int(s.sum()), "mean_p": float(p[s].mean()), "freq": float(y[s].mean())})
    return out


def score_set(prints: pd.DataFrame, models: list[str], primary_vs: list[str] | None, target: str = "FACTOR",
              weighted: bool = True) -> dict:
    ev = event_scores(prints, models, weighted=weighted)
    evl = event_scores(prints, models, log_loss, weighted=weighted)
    y = prints["y"].to_numpy()
    out = {"events": int(len(ev)), "days": int(ev["day"].nunique()), "prints": int(len(prints)),
           "brier": {m: float(ev[m].mean()) for m in models}, "log": {m: float(evl[m].mean()) for m in models},
           "auc": {m: auc(prints[m].to_numpy(), y) for m in models},
           "calibration": {m: calibration(prints[m].to_numpy(), y) for m in models}}
    if primary_vs:
        out["tests"] = holm({o: paired_test(ev, target, o) for o in primary_vs})
    return out


def trade(prints: pd.DataFrame, model: str) -> pd.DataFrame:
    """Taker rule at each print: buy the side the model prices at least EDGE above price plus fee."""
    q, p, y = prints[model].to_numpy(), prints["p"].to_numpy(), prints["y"].to_numpy()
    fee = FEE * p * (1 - p)
    yes = q - p - fee >= EDGE
    no = (1 - q) - (1 - p) - fee >= EDGE
    cost_per = np.where(yes, p + fee, np.where(no, (1 - p) + fee, np.nan))
    pay_per = np.where(yes, y, np.where(no, 1 - y, np.nan))
    n = np.minimum(CAPTURE * prints["count"].to_numpy(), CAP / cost_per)
    df = pd.DataFrame({"day": prints["day"].to_numpy(), "series": prints["series"].to_numpy(), "side": np.where(yes, "yes", np.where(no, "no", "")),
                       "cost": n * cost_per, "pnl": n * (pay_per - cost_per)})
    return df[df["side"] != ""]


def trade_summary(tr: pd.DataFrame, n_boot: int = 2000) -> dict:
    if tr.empty:
        return {"trades": 0}
    by_day = tr.groupby("day")[["cost", "pnl"]].sum()
    days = by_day.index.to_numpy()
    rng = np.random.default_rng(0)
    vals = by_day.to_numpy()
    draws = []
    for _ in range(n_boot):
        s = vals[rng.integers(0, len(vals), len(vals))].sum(axis=0)
        draws.append(s[1] / s[0])
    return {"trades": int(len(tr)), "days": int(len(days)), "cost": float(tr["cost"].sum()), "pnl": float(tr["pnl"].sum()),
            "return": float(tr["pnl"].sum() / tr["cost"].sum()), "lo": float(np.quantile(draws, 0.025)), "hi": float(np.quantile(draws, 0.975)),
            "yes_share": float((tr["side"] == "yes").mean())}
