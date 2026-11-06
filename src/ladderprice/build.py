"""Turn the downloaded ladders into scored prints: each qualifying trade with every model's probability."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import market, pricing, reversal, universe

ET = "America/New_York"
COINS = {"KXSOLD": "SOLUSDT", "KXXRPD": "XRPUSDT", "KXDOGED": "DOGEUSDT", "KXETHD": "ETHUSDT"}
MIN_H, MAX_H = 1.0, 24.0
MIN_P, MAX_P = 0.05, 0.95
FEAR, GREED = 35.0, 65.0
CELLS = [f"{r}|{c}" for r in ("fear", "neutral", "greed") for c in ("crowded", "calm")]


def load_prints(kalshi_dir: Path) -> pd.DataFrame:
    rows = []
    for f in sorted(kalshi_dir.glob("*.json")):
        ev = json.loads(f.read_text())
        series = ev["event"].split("-")[0]
        for m in ev["markets"]:
            if (m["strike_type"] != "greater" or not m.get("trades") or m["result"] not in ("yes", "no")
                    or not m.get("trades_fetched", False)):
                continue
            close = pd.Timestamp(m["close_time"])
            for t in m["trades"]:
                rows.append((ev["event"], series, m["ticker"], float(m["floor_strike"]), close, t["t"], t["p"], t["c"],
                             1.0 if m["result"] == "yes" else 0.0))
    df = pd.DataFrame(rows, columns=["event", "series", "ticker", "strike", "close", "t", "p", "count", "y"])
    df["t"] = pd.to_datetime(df["t"], utc=True, format="ISO8601")
    df["close"] = pd.to_datetime(df["close"], utc=True)
    df["h"] = (df["close"] - df["t"]).dt.total_seconds() / 3600
    df["day"] = df["close"].dt.tz_convert(ET).dt.tz_localize(None).dt.normalize()
    return df


POLY = {"solana": ("POLY-SOL", "SOLUSDT"), "xrp": ("POLY-XRP", "XRPUSDT")}
POLY_MAX_H = 168.0


def load_poly_prints(poly_dir: Path) -> pd.DataFrame:
    rows = []
    for f in sorted(poly_dir.glob("*.json")):
        ev = json.loads(f.read_text())
        series, _ = POLY[ev["coin"]]
        for m in ev["markets"]:
            close = pd.Timestamp(m["end"])
            for t in m["trades"]:
                rows.append((ev["slug"], series, m["question"], float(m["strike"]), close, pd.Timestamp(int(t["ts"]), unit="s", tz="UTC"),
                             float(t["p_yes"]), float(t["size"]), 1.0 if m["yes_won"] else 0.0))
    df = pd.DataFrame(rows, columns=["event", "series", "ticker", "strike", "close", "t", "p", "count", "y"])
    if df.empty:
        return df
    df["close"] = pd.to_datetime(df["close"], utc=True)
    df["h"] = (df["close"] - df["t"]).dt.total_seconds() / 3600
    df["day"] = df["close"].dt.tz_convert(ET).dt.tz_localize(None).dt.normalize()
    return df


def asof(series: pd.Series, times: pd.Series) -> np.ndarray:
    """Last value of series at or before each time (series indexed by UTC timestamps)."""
    s = series.dropna()
    idx = s.index.searchsorted(pd.DatetimeIndex(times), side="right") - 1
    out = np.where(idx >= 0, s.to_numpy()[np.clip(idx, 0, None)], np.nan)
    return out


def five_pm_closes(close_1m: pd.DataFrame, days: pd.DatetimeIndex) -> pd.DataFrame:
    t = pd.DatetimeIndex([d.tz_localize(ET) + pd.Timedelta(hours=17) for d in days]).tz_convert("UTC")
    return pd.DataFrame(close_1m.reindex(t).to_numpy(), index=days, columns=close_1m.columns)


def regime(v: float) -> str | None:
    if not np.isfinite(v):
        return None
    return "fear" if v < FEAR else "greed" if v > GREED else "neutral"


def build(data: Path) -> tuple[pd.DataFrame, dict]:
    prints = load_prints(data / "kalshi")
    n_all = len(prints)
    prints = prints[(prints["h"] >= MIN_H) & (prints["h"] <= MAX_H) & (prints["p"] >= MIN_P) & (prints["p"] <= MAX_P)].copy()
    if (data / "polymarket").exists():
        pp = load_poly_prints(data / "polymarket")
        if len(pp):
            pp = pp[(pp["h"] >= MIN_H) & (pp["h"] <= POLY_MAX_H) & (pp["p"] >= MIN_P) & (pp["p"] <= MAX_P)]
            prints = pd.concat([prints, pp], ignore_index=True)
    c1m = market.load_klines(data, "1m")
    c1h = market.load_klines(data, "1h")
    r1h = np.log(c1h / c1h.shift(1))
    dvol = {c: market.load_dvol(data, c) for c in ("BTC", "ETH")}
    fund = market.load_funding(data)
    fng = market.load_fng(data)

    days = pd.date_range("2025-07-01", "2026-10-31", freq="D")
    px5 = five_pm_closes(c1m, days)
    r_day = np.log(px5 / px5.shift(1))
    start5 = pd.DatetimeIndex([d.tz_localize(ET) + pd.Timedelta(hours=17) for d in days - pd.Timedelta(days=1)]).tz_convert("UTC")

    def k_series(cur: str, sym: str) -> pd.Series:
        sd = asof(dvol[cur], pd.Series(start5)) / 100 / np.sqrt(365)
        z = (r_day[sym] / (sd / pricing.T_SD)).abs()
        return pricing.trailing_scale(z)

    k = {"BTC": k_series("BTC", "BTCUSDT"), "ETH": k_series("ETH", "ETHUSDT")}

    # Reversal follow-up (research.md, "Follow-up: reversal in fear"): signal, daily slopes, regime-matched forecast slope.
    rev = None
    if (data / "universe").exists():
        uc, uv = universe.load(data / "universe", universe.FOLLOWUP_START)
        rz, rret = reversal.signals(uc, uv)
        g = reversal.daily_slopes(rz, rret)
        labels = reversal.regime_labels(fng)
        rev = {"z": rz, "b": reversal.forecast_slopes(g, labels), "g": g, "labels": labels}

    out = []
    meta = {"prints_downloaded": int(n_all), "prints_qualifying": int(len(prints))}
    groups = list(COINS.items()) + list(POLY.values())
    feats_cache = {}
    for series, sym in groups:
        p = prints[prints["series"] == series].copy()
        if p.empty:
            continue
        if sym not in feats_cache:
            feats_cache[sym] = pricing.hourly_features(r1h[sym], r1h["BTCUSDT"])
        feats = feats_cache[sym]
        # Day-level standardized residuals and cells, for the FACTOR scale table.
        f5 = feats.reindex(start5)
        e = r_day[sym].to_numpy() - f5["beta"].to_numpy() * r_day["BTCUSDT"].to_numpy()
        z = pd.Series(np.abs(e / (f5["res_sd"].to_numpy() / pricing.T_SD)), index=days)
        fl = fng.reindex(pd.date_range(fng.index.min(), fng.index.max(), freq="D"))
        f7 = fund[sym]
        crowd_ref = f7.shift(1).rolling(90, min_periods=60).median()

        def cell_at(times: pd.Series) -> list[str | None]:
            utc_day = times.dt.tz_convert("UTC").dt.tz_localize(None).dt.normalize()
            reg = [regime(v) for v in fl.reindex(utc_day - pd.Timedelta(days=1)).to_numpy()]
            fv, ref = f7.reindex(utc_day).to_numpy(), crowd_ref.reindex(utc_day).to_numpy()
            crowd = ["crowded" if a > b else "calm" if np.isfinite(a) and np.isfinite(b) else None for a, b in zip(fv, ref)]
            return [f"{r}|{c}" if r and c else None for r, c in zip(reg, crowd)]

        day_cells = pd.Series(cell_at(pd.Series(start5)), index=days)
        table = pricing.cell_table(z, day_cells, CELLS)

        spot = asof(c1m[sym], p["t"])
        p["x"] = np.log(p["strike"].to_numpy() / spot)
        hs = np.sqrt(p["h"].to_numpy() / 24)
        for col in ("own_sd", "beta", "beta_down", "beta_up", "res_sd"):
            p[col] = asof(feats[col], p["t"])
        kb = k["BTC"].reindex(p["day"]).fillna(1.0).to_numpy()
        p["btc_sd"] = kb * asof(dvol["BTC"], p["t"]) / 100 / np.sqrt(365)
        p["cell"] = cell_at(p["t"])
        p["c"] = [table.at[d, c] if c in table.columns and d in table.index else 1.0 for d, c in zip(p["day"], p["cell"])]
        ok = np.isfinite(p[["x", "own_sd", "beta", "res_sd", "btc_sd"]].to_numpy()).all(axis=1)
        meta[f"{series}_missing_inputs"] = int((~ok).sum())
        p = p[ok].copy()
        hs = np.sqrt(p["h"].to_numpy() / 24)
        x = p["x"].to_numpy()
        bsd = p["btc_sd"].to_numpy() * hs
        rsd = p["res_sd"].to_numpy() * hs
        p["MKT"] = p["p"]
        p["OWN"] = pricing.p_own(x, p["own_sd"].to_numpy() * hs)
        p["BETA"] = pricing.p_mapped(x, bsd, p["beta"].to_numpy(), p["beta"].to_numpy(), rsd)
        p["CRASH"] = pricing.p_mapped(x, bsd, p["beta_down"].to_numpy(), p["beta_up"].to_numpy(), rsd)
        p["FACTOR"] = pricing.p_mapped(x, bsd, p["beta_down"].to_numpy(), p["beta_up"].to_numpy(), rsd * p["c"].to_numpy())
        p["r_to_close"] = np.log(asof(c1m[sym], p["close"]) / asof(c1m[sym], p["t"]))
        if rev is not None:
            utc_day = p["t"].dt.tz_convert("UTC").dt.tz_localize(None).dt.normalize()
            zc = rev["z"][sym].reindex(utc_day).to_numpy() if sym in rev["z"].columns else np.full(len(p), np.nan)
            meta[f"{series}_missing_reversal"] = int((~np.isfinite(zc)).sum())
            p["rev_z"] = np.nan_to_num(zc)
            p["rev_b"] = rev["b"].reindex(utc_day).fillna(0.0).to_numpy()
            p["regime"] = rev["labels"].reindex(utc_day).to_numpy()
            p["mu"] = p["rev_b"].to_numpy() * p["rev_z"].to_numpy() * p["h"].to_numpy() / 24
            p["REV"] = pricing.p_mapped(x - p["mu"].to_numpy(), bsd, p["beta_down"].to_numpy(), p["beta_up"].to_numpy(),
                                        rsd * p["c"].to_numpy())
            p["MKTREV"] = np.clip(p["MKT"] + p["REV"] - p["FACTOR"], 0.001, 0.999)
        if sym == "ETHUSDT":
            ke = k["ETH"].reindex(p["day"]).fillna(1.0).to_numpy()
            p["ETHOPT"] = pricing.p_own(x, ke * asof(dvol["ETH"], p["t"]) / 100 / np.sqrt(365) * hs)
        out.append(p)
    meta["k_btc_median"] = float(k["BTC"].median())
    if rev is not None:
        meta["reversal"] = {"slopes": rev["g"], "labels": rev["labels"], "b": rev["b"]}
    return pd.concat(out, ignore_index=True), meta
