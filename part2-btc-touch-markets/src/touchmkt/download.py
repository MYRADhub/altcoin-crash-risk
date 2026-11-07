"""Public data downloads. Plan: research.md, "Data".

Sources:
- Polymarket Gamma API (events, rules) and data API v2 (trades). Only time, price, size, side and outcome are kept;
  no wallet or user fields are stored.
- Deribit history API, public/get_last_trades_by_currency_and_time (every BTC option trade with its implied volatility).
- Binance public archive, https://data.binance.vision (BTCUSDT 1-minute klines, USDT-M funding).
- Kalshi Trade API v2 (KXBTCD 5 pm ET ladders), at most 3 requests per second.
- Alternative.me Fear & Greed index (attribution required).
"""

from __future__ import annotations

import gzip
import http.client
import io
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

GAMMA = "https://gamma-api.polymarket.com"
PM_TRADES = "https://data-api.polymarket.com/v2/trades"
SERIES = {"daily": 10200, "weekly": 10151, "monthly": 10016}
DERIBIT = "https://history.deribit.com/api/v2/public/get_last_trades_by_currency_and_time"
ARCHIVE = "https://data.binance.vision/data"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
FNG_URL = "https://api.alternative.me/fng/?limit=0&format=json"
START, END = "2024-10-01", "2026-11-06"
MAX_EXPIRY_DAYS = 40
MIN_FREE_GB = 5.0


def check_disk(path: Path) -> None:
    """Stop a download before the disk fills up."""
    import shutil

    free = shutil.disk_usage(path).free / 1e9
    if free < MIN_FREE_GB:
        raise SystemExit(f"stopping: only {free:.1f} GB free on the disk")


class Getter:
    """JSON GET with retries and a minimum gap between requests."""

    def __init__(self, min_gap: float):
        self.min_gap, self.last = min_gap, 0.0

    def __call__(self, url: str, retries: int = 8, raw: bool = False):
        for attempt in range(retries):
            wait = self.min_gap - (time.monotonic() - self.last)
            if wait > 0:
                time.sleep(wait)
            self.last = time.monotonic()
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "research-script"})
                with urllib.request.urlopen(req, timeout=60) as r:
                    body = r.read()
                return body if raw else json.loads(body)
            except urllib.error.HTTPError as e:
                if e.code in (400, 404, 410, 422):
                    raise
                time.sleep(min(2 ** attempt, 60))
            except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException):
                time.sleep(min(2 ** attempt, 60))
        raise RuntimeError(f"failed: {url}")


# ---------------------------------------------------------------- Polymarket

QUESTION = re.compile(r"(reach|dip to|hit)\s*\$?\s*([\d,]+(?:\.\d+)?)\s*([kKmM](?![a-zA-Z]))?", re.I)


def parse_question(q: str) -> tuple[str, float] | None:
    """'Will Bitcoin reach $114K before July 14?' -> ('reach', 114000.0); 'dip to $80,000' -> ('dip', 80000.0)."""
    m = QUESTION.search(q)
    if not m:
        return None
    v = float(m.group(2).replace(",", ""))
    mult = {"k": 1e3, "m": 1e6}.get((m.group(3) or "").lower(), 1.0)
    return ("dip" if m.group(1).lower().startswith("dip") else "reach"), v * mult


def pm_trades(get: Getter, condition_id: str) -> list[dict]:
    out, cursor = [], None
    while True:
        q = {"condition_id": condition_id, "limit": 500}
        if cursor:
            q["cursor"] = cursor
        r = get(f"{PM_TRADES}?{urllib.parse.urlencode(q)}")
        out += [{"ts": t["timestamp"], "p_yes": t["price"] if t["outcome"] == "Yes" else 1 - t["price"], "size": t["size"],
                 "side": t["side"], "outcome": t["outcome"]} for t in r["data"]]
        cursor = r["pagination"].get("next_cursor")
        if not r["pagination"].get("has_more") or not cursor:
            return out


def pm_events(get: Getter, series_id: int) -> list[dict]:
    out, off = [], 0
    while True:
        ev = get(f"{GAMMA}/events?{urllib.parse.urlencode({'series_id': series_id, 'closed': 'true', 'limit': 100, 'offset': off})}")
        out += ev
        off += 100
        if len(ev) < 100:
            return out


def download_polymarket(dest: Path) -> None:
    get = Getter(0.25)
    dest.mkdir(parents=True, exist_ok=True)
    for kind, sid in SERIES.items():
        events = pm_events(get, sid)
        n = 0
        for e in events:
            f = dest / f"{kind}-{e['slug']}.json"
            check_disk(dest)
            if f.exists() or re.search(r"hit-in-20\d\d$", e["slug"]):  # the annual event is excluded
                continue
            mk = []
            for m in e.get("markets", []):
                parsed = parse_question(m.get("question", ""))
                prices = json.loads(m.get("outcomePrices") or "[]")
                if parsed is None or not m.get("closed") or len(prices) != 2:
                    continue
                vol = float(m.get("volume") or 0)
                mk.append({"question": m["question"], "direction": parsed[0], "strike": parsed[1],
                           "start": m.get("startDate"), "end": m.get("endDate"), "description": (m.get("description") or "")[:1500],
                           "yes_won": float(prices[0]) > 0.5, "volume": vol,
                           "trades": pm_trades(get, m["conditionId"]) if vol > 0 else []})
            tmp = f.with_suffix(".tmp")
            tmp.write_text(json.dumps({"slug": e["slug"], "kind": kind, "title": e.get("title"), "start": e.get("startDate"),
                                       "end": e.get("endDate"), "markets": mk}))
            tmp.rename(f)
            n += 1
        print(f"polymarket {kind}: {len(events)} events listed, {n} new", flush=True)


# ---------------------------------------------------------------- Deribit

def _expiry(instrument: str) -> pd.Timestamp | None:
    """'BTC-26SEP25-106000-P' -> 2025-09-26 08:00 UTC."""
    try:
        return pd.to_datetime(instrument.split("-")[1], format="%d%b%y").tz_localize("UTC") + pd.Timedelta(hours=8)
    except (IndexError, ValueError):
        return None


def download_deribit(dest: Path, start: str = START, end: str = END) -> None:
    """One gzip CSV per UTC day: ts_ms, instrument, iv, index_price, price, amount, direction (short expiries only)."""
    get = Getter(0.06)
    dest.mkdir(parents=True, exist_ok=True)
    for day in pd.date_range(start, end, freq="D", tz="UTC"):
        f = dest / f"{day:%Y-%m-%d}.csv.gz"
        if f.exists():
            continue
        check_disk(dest)
        t0, t1 = int(day.timestamp() * 1000), int((day + pd.Timedelta(days=1)).timestamp() * 1000) - 1
        rows, seen, cur = [], set(), t0
        while True:
            q = {"currency": "BTC", "kind": "option", "start_timestamp": cur, "end_timestamp": t1, "count": 1000, "sorting": "asc"}
            r = get(f"{DERIBIT}?{urllib.parse.urlencode(q)}")["result"]
            for t in r["trades"]:
                if t["trade_id"] in seen:
                    continue
                seen.add(t["trade_id"])
                ex = _expiry(t["instrument_name"])
                if ex is None or (ex - pd.Timestamp(t["timestamp"], unit="ms", tz="UTC")).days > MAX_EXPIRY_DAYS:
                    continue
                rows.append((t["timestamp"], t["instrument_name"], t.get("iv"), t.get("index_price"), t.get("price"),
                             t.get("amount"), t.get("direction")))
            if not r.get("has_more") or not r["trades"]:
                break
            nxt = r["trades"][-1]["timestamp"]
            cur = nxt if nxt > cur else cur + 1
        tmp = f.with_suffix(".tmp")
        with gzip.open(tmp, "wt") as g:
            pd.DataFrame(rows, columns=["ts", "instrument", "iv", "index", "price", "amount", "direction"]).to_csv(g, index=False)
        tmp.rename(f)
        if day.day == 1:
            print(f"deribit {day:%Y-%m}: {len(rows)} trades on the 1st", flush=True)


# ---------------------------------------------------------------- Binance, funding, Fear & Greed

def download_binance(dest: Path) -> None:
    get = Getter(0.0)
    (dest / "klines").mkdir(parents=True, exist_ok=True)
    (dest / "funding").mkdir(parents=True, exist_ok=True)
    months = [p.strftime("%Y-%m") for p in pd.period_range(START[:7], "2026-10", freq="M")]
    for m in months:
        f = dest / "klines" / f"BTCUSDT-1m-{m}.zip"
        if not f.exists():
            f.write_bytes(get(f"{ARCHIVE}/spot/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-{m}.zip", raw=True))
    for d in pd.date_range("2026-11-01", END, freq="D"):
        f = dest / "klines" / f"BTCUSDT-1m-{d:%Y-%m-%d}.zip"
        if not f.exists():
            try:
                f.write_bytes(get(f"{ARCHIVE}/spot/daily/klines/BTCUSDT/1m/BTCUSDT-1m-{d:%Y-%m-%d}.zip", raw=True))
            except urllib.error.HTTPError:
                pass
    for m in [p.strftime("%Y-%m") for p in pd.period_range("2023-10", "2026-10", freq="M")]:
        f = dest / "funding" / f"BTCUSDT-fundingRate-{m}.zip"
        if not f.exists():
            f.write_bytes(get(f"{ARCHIVE}/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-{m}.zip", raw=True))
    (dest / "fng.json").write_bytes(get(FNG_URL, raw=True))
    print("binance klines, funding and fear & greed done", flush=True)


def load_klines(dest: Path) -> pd.DataFrame:
    """BTCUSDT 1-minute bars indexed by open time (UTC): high, low, close."""
    parts = []
    for f in sorted((dest / "klines").glob("*.zip")):
        with zipfile.ZipFile(f) as z:
            for n in z.namelist():
                df = pd.read_csv(io.BytesIO(z.read(n)), header=None)
                df = df[pd.to_numeric(df[0], errors="coerce").notna()]
                t = df[0].astype("int64").to_numpy()
                sec = np.where(t > 10 ** 14, t // 10 ** 6, t // 10 ** 3)
                parts.append(pd.DataFrame({"t": pd.to_datetime(sec, unit="s", utc=True), "high": df[2].astype(float).to_numpy(),
                                           "low": df[3].astype(float).to_numpy(), "close": df[4].astype(float).to_numpy()}))
    return pd.concat(parts).drop_duplicates("t").set_index("t").sort_index()


# ---------------------------------------------------------------- Kalshi

def kalshi_event_date(ticker: str) -> str | None:
    code = ticker.rsplit("-", 1)[-1]
    months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    if len(code) != 9 or code[2:5] not in months or not (code[:2] + code[5:]).isdigit() or code[-2:] != "17":
        return None
    return f"20{code[:2]}-{months.index(code[2:5]) + 1:02d}-{code[5:7]}"


def download_kalshi(dest: Path, spot: pd.Series, band: float = 0.08, start: str = START, end: str = END) -> None:
    get = Getter(0.34)
    dest.mkdir(parents=True, exist_ok=True)
    events, cursor = [], ""
    while True:
        params = {"series_ticker": "KXBTCD", "status": "settled", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        d = get(f"{KALSHI}/events?{urllib.parse.urlencode(params)}")
        events += [e["event_ticker"] for e in d.get("events", [])]
        cursor = d.get("cursor")
        if not cursor or not d.get("events"):
            break
    events = sorted(e for e in set(events) if (dt := kalshi_event_date(e)) and start <= dt <= end)
    print(f"kalshi KXBTCD: {len(events)} 5 pm events", flush=True)

    def trades(ticker: str, historical: bool) -> list[dict]:
        out, cur = [], ""
        while True:
            p = {"ticker": ticker, "limit": 1000}
            if cur:
                p["cursor"] = cur
            r = get(f"{KALSHI}/{'historical/trades' if historical else 'markets/trades'}?{urllib.parse.urlencode(p)}")
            out += r.get("trades", [])
            cur = r.get("cursor")
            if not cur or not r.get("trades"):
                return out

    for i, ev in enumerate(events):
        f = dest / f"{ev}.json"
        if f.exists():
            continue
        historical = True
        markets = get(f"{KALSHI}/historical/markets?{urllib.parse.urlencode({'event_ticker': ev, 'limit': 1000})}").get("markets", [])
        if not markets:
            historical = False
            markets = get(f"{KALSHI}/markets?{urllib.parse.urlencode({'event_ticker': ev, 'limit': 1000})}")["markets"]
        rows = []
        for m in markets:
            if m.get("strike_type") != "greater" or m.get("floor_strike") is None:
                continue
            r = {k: m.get(k) for k in ("ticker", "floor_strike", "result", "volume_fp", "open_time", "close_time")}
            ot = pd.Timestamp(r["open_time"])
            i0 = spot.index.searchsorted(ot, side="right") - 1
            ref = float(spot.iloc[i0]) if i0 >= 0 else None
            near = ref is not None and abs(math.log(float(r["floor_strike"]) / ref)) <= band
            r["trades_fetched"] = bool(near)
            if near and float(r["volume_fp"] or 0) > 0:
                r["trades"] = [{"t": t["created_time"], "p": float(t["yes_price_dollars"]), "c": float(t["count_fp"]),
                                "side": t.get("taker_side")} for t in trades(r["ticker"], historical)]
            rows.append(r)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps({"event": ev, "historical": historical, "markets": rows}))
        tmp.rename(f)
        if i % 50 == 0:
            print(f"  kalshi {ev} {i + 1}/{len(events)}", flush=True)
