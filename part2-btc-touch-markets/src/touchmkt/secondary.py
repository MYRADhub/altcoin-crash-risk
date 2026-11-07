"""Secondary analyses: mood and crowding, and the no-arbitrage bound against Kalshi. Plan: research.md, "Secondary"."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from . import download, evaluate

ET = "America/New_York"
TOL = 0.01
PAIR_WINDOW = pd.Timedelta(minutes=5)


def trailing_z(s: pd.Series, window: int = 365, min_n: int = 90) -> pd.Series:
    prev = s.shift(1)
    return (s - prev.rolling(window, min_periods=min_n).mean()) / prev.rolling(window, min_periods=min_n).std()


def signals(binance_dir: Path) -> pd.DataFrame:
    """Daily (UTC date) standardized 30-day Fear & Greed mean and 7-day BTC funding mean, each known at the start of the date."""
    rows = json.loads((binance_dir / "fng.json").read_text())["data"]
    fng = pd.Series({pd.to_datetime(int(r["timestamp"]), unit="s").normalize(): float(r["value"]) for r in rows}).sort_index()
    fng = fng[~fng.index.duplicated()]
    fng = fng.reindex(pd.date_range(fng.index.min(), fng.index.max(), freq="D"))
    parts = []
    for f in sorted((binance_dir / "funding").glob("*.zip")):
        with zipfile.ZipFile(f) as z:
            for n in z.namelist():
                df = pd.read_csv(io.BytesIO(z.read(n)), header=None)
                if not str(df.iloc[0, 0]).isdigit():
                    df = df.iloc[1:]
                parts.append(pd.DataFrame({"t": pd.to_datetime(df.iloc[:, 0].astype("int64") // 1000, unit="s"),
                                           "r": df.iloc[:, -1].astype(float).to_numpy()}))
    fd = pd.concat(parts).drop_duplicates("t")
    daily = fd.groupby(fd["t"].dt.normalize())["r"].sum()
    daily = daily.reindex(pd.date_range(daily.index.min(), daily.index.max(), freq="D"))
    fund7 = daily.rolling(7, min_periods=5).mean().shift(1)
    return pd.DataFrame({"fng_z": trailing_z(fng.rolling(30, min_periods=20).mean().shift(1)), "fund_z": trailing_z(fund7)})


def mood(tr: pd.DataFrame, sig: pd.DataFrame) -> dict:
    """Event-level reach-minus-dip premium against mood and crowding, known before the window starts."""
    e = evaluate.event_means(tr.assign(prem=tr["p"] - tr["FAIR"]), ["prem"], ["direction", "start"])
    pv = e.pivot_table(index=["event", "day", "kind", "start"], columns="direction", values="prem").dropna().reset_index()
    pv["asym"] = pv["reach"] - pv["dip"]
    d0 = pd.to_datetime(pv["start"]).dt.tz_convert("UTC").dt.tz_localize(None).dt.normalize()
    pv["fng_z"] = sig["fng_z"].reindex(d0).to_numpy()
    pv["fund_z"] = sig["fund_z"].reindex(d0).to_numpy()
    out = {"events": int(len(pv))}
    for x in ("fng_z", "fund_z"):
        out[f"asym on {x}"] = evaluate.slope_test(pv, x, "asym")
        out[f"reach on {x}"] = evaluate.slope_test(pv, x, "reach")
        out[f"dip on {x}"] = evaluate.slope_test(pv, x, "dip")
    return out


def load_kalshi(kalshi_dir: Path) -> pd.DataFrame:
    rows = []
    for f in sorted(kalshi_dir.glob("*.json")):
        ev = json.loads(f.read_text())
        date = download.kalshi_event_date(ev["event"])
        for m in ev["markets"]:
            for t in m.get("trades") or []:
                rows.append((date, float(m["floor_strike"]), t["t"], t["p"]))
    df = pd.DataFrame(rows, columns=["date", "kstrike", "t", "kp"])
    df["t"] = pd.to_datetime(df["t"], utc=True, format="ISO8601")
    return df.sort_values("t").reset_index(drop=True)


def kalshi_bound(tr: pd.DataFrame, kal: pd.DataFrame) -> dict:
    """Pairs daily Polymarket touch trades with the last Kalshi 5 pm ladder trade within 5 minutes, at the nearest strike
    at or beyond K, and counts prices that break P(touch) >= P(beyond K at 5 pm) by more than both fees plus 1 cent."""
    d = tr[tr["kind"] == "daily"].copy()
    d["date"] = d["day"].dt.strftime("%Y-%m-%d")
    out = []
    for (date, dirn, k), g in d.groupby(["date", "direction", "strike"]):
        kd = kal[kal["date"] == date]
        if kd.empty:
            continue
        ks = np.sort(kd["kstrike"].unique())
        if dirn == "reach":
            cand = ks[ks >= k - 0.5]
            if not len(cand):
                continue
            kk = cand[0]
        else:
            cand = ks[ks <= k + 0.5]
            if not len(cand):
                continue
            kk = cand[-1]
        kt = kd[kd["kstrike"] == kk]
        times = kt["t"].dt.tz_convert("UTC").dt.tz_localize(None).to_numpy()
        for r in g.itertuples():
            j = np.searchsorted(times, np.datetime64(r.t.tz_convert(None)), "right") - 1
            if j < 0 or r.t - kt["t"].iloc[j] > PAIR_WINDOW:
                continue
            kp = float(kt["kp"].iloc[j])
            beyond = kp if dirn == "reach" else 1 - kp
            fees = 0.07 * r.p * (1 - r.p) + 0.07 * kp * (1 - kp)
            out.append({"date": date, "direction": dirn, "strike": k, "kstrike": kk, "t": r.t, "poly": r.p, "kalshi_beyond": beyond,
                        "gap": beyond - r.p, "violation": beyond - r.p > fees + TOL, "size": r.size})
    df = pd.DataFrame(out)
    if df.empty:
        return {"pairs": 0}
    v = df[df["violation"]]
    return {"pairs": int(len(df)), "days_paired": int(df["date"].nunique()), "violations": int(len(v)),
            "violation_days": int(v["date"].nunique()), "violation_share": float(len(v) / len(df)),
            "median_gap_cents_when_violated": float(100 * v["gap"].median()) if len(v) else None,
            "median_gap_cents_all": float(100 * df["gap"].median()),
            "shares_at_violations": float(v["size"].sum()) if len(v) else 0.0}
