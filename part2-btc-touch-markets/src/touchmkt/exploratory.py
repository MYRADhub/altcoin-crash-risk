"""Exploratory, added after the planned Kalshi check: are the violations real or stale prints?

    python -m touchmkt.exploratory

A violation from the planned check is kept only if (1) the two trades are at most 60 seconds apart, (2) Binance's
price moved less than 0.1% between them, and (3) the prints are on the executable sides: on Kalshi someone sold YES
(so a bid existed at that price) and on Polymarket someone bought the touch YES (so an ask existed at that price).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import download, secondary

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


def poly_sides(pm_dir: Path) -> pd.DataFrame:
    """Taker action in YES terms for every Polymarket trade: +1 bought YES (or sold NO), -1 sold YES (or bought NO)."""
    rows = []
    for f in sorted(pm_dir.glob("daily-*.json")):
        ev = json.loads(f.read_text())
        for m in ev["markets"]:
            for t in m["trades"]:
                buy = t["side"] == "BUY"
                yes = t["outcome"] == "Yes"
                rows.append((ev["slug"], float(download.parse_question(m["question"])[1]), int(t["ts"]), float(t["p_yes"]),
                             1 if buy == yes else -1))
    df = pd.DataFrame(rows, columns=["event", "strike", "ts", "p", "yes_action"])
    df["t"] = pd.to_datetime(df["ts"], unit="s", utc=True)
    return df.drop(columns="ts")


def kalshi_trades(kalshi_dir: Path) -> pd.DataFrame:
    rows = []
    for f in sorted(kalshi_dir.glob("*.json")):
        ev = json.loads(f.read_text())
        date = download.kalshi_event_date(ev["event"])
        for m in ev["markets"]:
            for t in m.get("trades") or []:
                rows.append((date, float(m["floor_strike"]), t["t"], t["p"], t.get("side")))
    df = pd.DataFrame(rows, columns=["date", "kstrike", "t", "kp", "kside"])
    df["t"] = pd.to_datetime(df["t"], utc=True, format="ISO8601")
    return df.sort_values("t").reset_index(drop=True)


def main() -> None:
    tr = pd.read_csv(DATA / "derived" / "trades.csv.gz")
    for c in ("t", "start", "end"):
        tr[c] = pd.to_datetime(tr[c], utc=True, format="ISO8601")
    tr["day"] = pd.to_datetime(tr["day"])
    d = tr[tr["kind"] == "daily"].copy()
    d["date"] = d["day"].dt.strftime("%Y-%m-%d")
    kal = kalshi_trades(DATA / "kalshi")
    sides = poly_sides(DATA / "polymarket")
    close = download.load_klines(DATA / "binance")["close"]
    rows = []
    for (date, dirn, k), g in d.groupby(["date", "direction", "strike"]):
        kd = kal[kal["date"] == date]
        if kd.empty:
            continue
        ks = np.sort(kd["kstrike"].unique())
        cand = ks[ks >= k - 0.5] if dirn == "reach" else ks[ks <= k + 0.5]
        if not len(cand):
            continue
        kk = cand[0] if dirn == "reach" else cand[-1]
        kt = kd[kd["kstrike"] == kk].reset_index(drop=True)
        times = kt["t"].dt.tz_convert("UTC").dt.tz_localize(None).to_numpy()
        for r in g.itertuples():
            j = np.searchsorted(times, np.datetime64(r.t.tz_convert(None)), "right") - 1
            if j < 0 or r.t - kt.at[j, "t"] > secondary.PAIR_WINDOW:
                continue
            kp = float(kt.at[j, "kp"])
            beyond = kp if dirn == "reach" else 1 - kp
            fees = 0.07 * r.p * (1 - r.p) + 0.07 * kp * (1 - kp)
            if beyond - r.p <= fees + secondary.TOL:
                continue
            rows.append({"event": r.event, "date": date, "direction": dirn, "strike": k, "t_poly": r.t, "t_kalshi": kt.at[j, "t"],
                         "poly": r.p, "kalshi": kp, "kside": kt.at[j, "kside"], "gap": beyond - r.p - fees, "size": r.size})
    v = pd.DataFrame(rows)
    v["dt_s"] = (v["t_poly"] - v["t_kalshi"]).dt.total_seconds()
    i0 = close.index.searchsorted(v["t_kalshi"].dt.floor("min")) - 1
    i1 = close.index.searchsorted(v["t_poly"].dt.floor("min")) - 1
    v["move_pct"] = 100 * np.abs(close.to_numpy()[i1] / close.to_numpy()[i0] - 1)
    # Polymarket taker action at the matched print (same event, strike, second and price).
    # Match on event, strike and second, then the closest price (the derived file rounds prices to 6 decimals).
    grp = {key: g for key, g in sides.groupby(["event", "strike", "t"])}
    acts = []
    for e, k, t, p in zip(v["event"], v["strike"], v["t_poly"], v["poly"]):
        g = grp.get((e, float(k), t))
        if g is None:
            acts.append(np.nan)
            continue
        i = int(np.argmin(np.abs(g["p"].to_numpy() - p)))
        acts.append(float(g["yes_action"].iloc[i]) if abs(g["p"].iloc[i] - p) < 1e-4 else np.nan)
    v["poly_yes_action"] = acts
    out_missing = int(np.isnan(np.array(acts, float)).sum())
    # Executable: Kalshi seller of YES for reach (bid at kp); for dip the bound uses NO = 1 - kp, so a Kalshi YES buyer.
    k_ok = np.where(v["direction"] == "reach", v["kside"] == "no", v["kside"] == "yes")
    v["executable_sides"] = k_ok & (v["poly_yes_action"] == 1)
    out = {"violations": int(len(v)), "days": int(v["date"].nunique()), "poly_side_unmatched": out_missing,
           "within_60s": int((v["dt_s"] <= 60).sum()),
           "within_60s_and_flat": int(((v["dt_s"] <= 60) & (v["move_pct"] < 0.1)).sum()),
           "all_three": int(((v["dt_s"] <= 60) & (v["move_pct"] < 0.1) & v["executable_sides"]).sum())}
    keep = v[(v["dt_s"] <= 60) & (v["move_pct"] < 0.1) & v["executable_sides"]]
    out["all_three_days"] = int(keep["date"].nunique())
    out["all_three_median_gap_cents"] = float(100 * keep["gap"].median()) if len(keep) else None
    out["all_three_shares"] = float(keep["size"].sum()) if len(keep) else 0.0
    out["all_three_dollars_poly_side"] = float((keep["size"] * keep["poly"]).sum()) if len(keep) else 0.0
    print(json.dumps(out, indent=1))
    (ROOT / "results" / "kalshi_violations_exploratory.json").write_text(json.dumps(out, indent=2))
    v.to_csv(DATA / "derived" / "violations.csv", index=False)


if __name__ == "__main__":
    main()
