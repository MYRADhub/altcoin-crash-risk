"""Turn downloaded touch markets into priced trades. Plan: research.md, "Unit" and "Fair value from Deribit"."""

from __future__ import annotations

import gzip
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from . import download, pricing

ET = "America/New_York"
MIN_H = 1.0
MIN_P, MAX_P = 0.03, 0.97
GRID = "10min"
MAX_FIT_AGE = pd.Timedelta(hours=6)
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"


def window(market: dict, title: str) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """Touch window [start, end) in UTC from the market's rules; None if the wording is not recognized."""
    sched = pd.Timestamp(market.get("end") or market.get("event_end") or "NaT")
    if pd.isna(sched):
        return None
    if sched.tzinfo is None:
        sched = sched.tz_localize("UTC")
    # Every window ends at 11:59 PM ET on its last day. The scheduled end is midnight ET (04:00 or 05:00 UTC) or,
    # in 2024, noon UTC on the last day; two hours before it is always on the last day in ET.
    last_day = (sched - pd.Timedelta(hours=2)).tz_convert(ET).normalize().tz_localize(None)
    end = (last_day + pd.Timedelta(days=1)).tz_localize(ET).tz_convert("UTC")
    last = (end - pd.Timedelta(minutes=1)).tz_convert(ET)
    d = market["description"]
    m = re.search(rf"between ((?:{MONTHS}) \d{{1,2}}, \d{{4}}), (\d{{1,2}}:\d{{2}})", d)
    if m:
        start = pd.Timestamp(f"{m.group(1)} {m.group(2)}").tz_localize(ET)
        return start.tz_convert("UTC"), end
    m = re.search(r"between (\d{1,2}):(\d{2}) ?(AM|PM) ET and 11:59 ?PM ET", d)
    if m:
        h = int(m.group(1)) % 12 + (12 if m.group(3) == "PM" else 0)
        start = last.normalize().tz_localize(None).tz_localize(ET) + pd.Timedelta(hours=h, minutes=int(m.group(2)))
        return start.tz_convert("UTC"), end
    if re.search(r"from the creation of this market", d) and market.get("start"):
        start = pd.Timestamp(market["start"])
        return (start.tz_localize("UTC") if start.tzinfo is None else start.tz_convert("UTC")), end
    m0 = re.search(r"from (\d{1,2}):(\d{2}) ?(AM|PM)? ET on the first (date|day)", d)
    if m0:
        hh = int(m0.group(1)) % 12 + (12 if m0.group(3) == "PM" else 0)
        offset = pd.Timedelta(hours=hh, minutes=int(m0.group(2)))
        if "month" in d:
            first = last.normalize().tz_localize(None).replace(day=1)
        else:
            t = re.search(rf"((?:{MONTHS})) (\d{{1,2}})\s*[-–]", title)
            if not t:
                return None
            first = pd.Timestamp(f"{t.group(1)} {t.group(2)} {last.year}")
            if first > last.tz_localize(None):
                first = first.replace(year=last.year - 1)
        return (first.tz_localize(ET) + offset).tz_convert("UTC"), end
    return None


def load_markets(pm_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Markets (one row each) and trades (YES-equivalent price and shares), plus parse counts."""
    mrows, trows, counts = [], [], {"markets": 0, "no_window": 0}
    for f in sorted(pm_dir.glob("*.json")):
        ev = json.loads(f.read_text())
        for i, m in enumerate(ev["markets"]):
            counts["markets"] += 1
            w = window(m | {"event_end": ev.get("end")}, ev.get("title") or "")
            if w is None:
                counts["no_window"] += 1
                continue
            mid = f"{ev['slug']}#{i}"
            # Two-sided wording ("High" or "Low" ... above for up strikes, below for down strikes): side set at the window start.
            two_sided = m["direction"] == "reach" and re.search(r'"?Low"? price', m["description"]) is not None
            mrows.append({"market": mid, "event": ev["slug"], "kind": ev["kind"], "direction": "auto" if two_sided else m["direction"],
                          "strike": download.parse_question(m["question"])[1],
                          "start": w[0], "end": w[1], "y": 1.0 if m["yes_won"] else 0.0, "volume": m["volume"]})
            for t in m["trades"]:
                trows.append((mid, int(t["ts"]), float(t["p_yes"]), float(t["size"]), t["side"]))
    mk = pd.DataFrame(mrows)
    tr = pd.DataFrame(trows, columns=["market", "ts", "p", "size", "side"])
    tr["t"] = pd.to_datetime(tr["ts"], unit="s", utc=True)
    return mk, tr.drop(columns="ts"), counts


def first_touch(mk: pd.DataFrame, bars: pd.DataFrame) -> pd.Series:
    """Open time of the first Binance 1-minute bar in the window that touches the strike (NaT if none)."""
    hi, lo, idx = bars["high"].to_numpy(), bars["low"].to_numpy(), bars.index
    out = []
    for r in mk.itertuples():
        a, b = idx.searchsorted(r.start, "left"), idx.searchsorted(r.end, "left")
        hit = np.flatnonzero(hi[a:b] >= r.strike) if r.direction == "reach" else np.flatnonzero(lo[a:b] <= r.strike)
        out.append(idx[a + hit[0]] if len(hit) else pd.NaT)
    return pd.Series(out, index=mk.index)


def load_deribit(der_dir: Path, days: list[pd.Timestamp]) -> pd.DataFrame:
    parts = []
    for d in days:
        f = der_dir / f"{d:%Y-%m-%d}.csv.gz"
        if f.exists():
            with gzip.open(f, "rt") as g:
                parts.append(pd.read_csv(g))
    if not parts:
        return pd.DataFrame(columns=["t", "instrument", "iv", "index"])
    df = pd.concat(parts, ignore_index=True)
    df["t"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df[["t", "instrument", "iv", "index"]]


def price_trades(tr: pd.DataFrame, der_dir: Path) -> pd.DataFrame:
    """Add D (digital beyond K), FAIR (2 x D), GBM touch, total variance and fit age to each trade."""
    tr = tr.sort_values("t").reset_index(drop=True)
    grid_t = tr["t"].dt.floor(GRID)
    out = {k: np.full(len(tr), np.nan) for k in ("D", "FAIR", "GBM", "w", "fit_age_min")}
    for day, rows in tr.groupby(tr["t"].dt.floor("D")).groups.items():
        der = load_deribit(der_dir, [day - pd.Timedelta(days=1), day])
        if der.empty:
            continue
        grid = pd.DatetimeIndex(sorted(set(grid_t[rows])))
        fits = pricing.grid_fits(der, grid)
        keys = sorted(fits)
        keys_np = np.array([k.tz_convert(None).to_datetime64() for k in keys], dtype="datetime64[ns]")
        for i in rows:
            t, g = tr.at[i, "t"], grid_t[i]
            j = np.searchsorted(keys_np, g.tz_convert(None).to_datetime64(), "right") - 1 if keys else -1
            if j < 0 or g - keys[j] > MAX_FIT_AGE:
                continue
            gk = keys[j]
            ref, fl = fits[gk]
            fl2 = []
            for ex, coef in fl:
                tau_g, tau_p = (ex - gk).total_seconds() / pricing.YEAR, (ex - t).total_seconds() / pricing.YEAR
                if tau_p > 0:
                    sc = tau_p / tau_g
                    fl2.append((tau_p, (coef[0] * sc, coef[1] * sc, coef[2] * sc)))
            if not fl2:
                continue
            t_end = (tr.at[i, "end"] - t).total_seconds() / pricing.YEAR
            s, k = tr.at[i, "spot"], tr.at[i, "strike"]
            d_up = pricing.digital_above(s, k, t_end, fl2, ref)
            w = pricing.total_variance(np.log(k / ref), t_end, fl2)
            dirn = tr.at[i, "direction"]
            out["D"][i] = d_up if dirn == "reach" else 1 - d_up
            out["FAIR"][i] = pricing.touch_reflection(dirn, d_up)
            out["GBM"][i] = pricing.touch_gbm(dirn, s, k, w)
            out["w"][i] = w
            out["fit_age_min"][i] = (t - gk).total_seconds() / 60
    for k, v in out.items():
        tr[k] = v
    return tr


def build(data: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    mk, tr, meta = load_markets(data / "polymarket")
    bars = download.load_klines(data / "binance")
    auto = mk["direction"] == "auto"
    j = bars.index.searchsorted(mk.loc[auto, "start"], "left") - 1
    s0 = bars["close"].to_numpy()[np.clip(j, 0, None)]
    mk.loc[auto, "direction"] = np.where(mk.loc[auto, "strike"].to_numpy() < s0, "dip", "reach")
    meta["two_sided_markets"] = int(auto.sum())
    mk["touch_at"] = first_touch(mk, bars)
    mk["binance_y"] = mk["touch_at"].notna().astype(float)
    meta["resolution_agreement"] = float((mk["binance_y"] == mk["y"]).mean())
    tr = tr.merge(mk, on="market", how="inner")
    meta["trades_downloaded"] = int(len(tr))
    tr["h"] = (tr["end"] - tr["t"]).dt.total_seconds() / 3600
    started = tr["t"] >= tr["start"]
    untouched = tr["touch_at"].isna() | (tr["t"] < tr["touch_at"])
    keep = started & untouched & (tr["h"] >= MIN_H) & (tr["p"] >= MIN_P) & (tr["p"] <= MAX_P)
    meta["trades_excluded"] = {"before_window": int((~started).sum()), "already_touched": int((started & ~untouched).sum()),
                               "price_or_horizon": int((started & untouched & ~keep).sum())}
    tr = tr[keep].copy()
    # Spot: close of the last completed Binance minute before the trade.
    close = bars["close"]
    j = close.index.searchsorted(tr["t"].dt.floor("min"), "left") - 1
    tr["spot"] = np.where(j >= 0, close.to_numpy()[np.clip(j, 0, None)], np.nan)
    tr["x"] = np.log(tr["strike"] / tr["spot"])
    tr = price_trades(tr, data / "deribit")
    meta["trades_priced"] = int(tr["FAIR"].notna().sum())
    tr["day"] = (tr["end"] - pd.Timedelta(minutes=1)).dt.tz_convert(ET).dt.tz_localize(None).dt.normalize()
    return tr[tr["FAIR"].notna()].reset_index(drop=True), mk, meta
