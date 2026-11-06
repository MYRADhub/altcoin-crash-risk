"""Download Kalshi 5 pm ET altcoin ladders: market metadata and every trade, from the public Trade API v2.

One JSON file per event in data/kalshi/<EVENT>.json, so a rerun only fetches missing events.
Requests are spaced to stay at or under 3 per second.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.elections.kalshi.com/trade-api/v2"
SERIES = ["KXSOLD", "KXXRPD", "KXDOGED", "KXETHD"]
MIN_GAP = 0.34
_last = [0.0]


def get(path: str, params: dict | None = None, retries: int = 8) -> dict:
    url = f"{API}{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
    for attempt in range(retries):
        wait = MIN_GAP - (time.monotonic() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "research-script"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            time.sleep(min(2 ** attempt, 60))
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(min(2 ** attempt, 60))
    raise RuntimeError(f"failed: {url}")


def is_five_pm(event_ticker: str) -> bool:
    """Event tickers end in the ET hour of the close, e.g. KXSOLD-26OCT2817 closes at 5 pm ET."""
    return event_ticker.rsplit("-", 1)[-1][-2:] == "17"


def event_date(event_ticker: str) -> str | None:
    """'KXSOLD-26OCT2817' -> '2026-10-28'; None for tickers in another format."""
    code = event_ticker.rsplit("-", 1)[-1]
    months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    if len(code) != 9 or code[2:5] not in months or not (code[:2] + code[5:]).isdigit():
        return None
    return f"20{code[:2]}-{months.index(code[2:5]) + 1:02d}-{code[5:7]}"


def five_pm_events(series: str, end: str = "2026-10-31") -> list[str]:
    out, cursor = [], ""
    while True:
        params = {"series_ticker": series, "status": "settled", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        d = get("/events", params)
        out += [e["event_ticker"] for e in d.get("events", []) if is_five_pm(e["event_ticker"])]
        cursor = d.get("cursor")
        if not cursor or not d.get("events"):
            break
    return sorted(e for e in set(out) if (d := event_date(e)) is not None and d <= end)


def trades(ticker: str, historical: bool) -> list[dict]:
    out, cursor = [], ""
    while True:
        params = {"ticker": ticker, "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        d = get("/historical/trades" if historical else "/markets/trades", params)
        out += d.get("trades", [])
        cursor = d.get("cursor")
        if not cursor or not d.get("trades"):
            return out


BAND = 0.10
SPOT = {"KXSOLD": "SOLUSDT", "KXXRPD": "XRPUSDT", "KXDOGED": "DOGEUSDT", "KXETHD": "ETHUSDT"}


def download_event(event: str, dest: Path, spot=None) -> int:
    """Markets and trades of one event. With spot (a function of a UTC timestamp), trades are fetched only for
    strikes within BAND (log) of the spot price when the event lists."""
    f = dest / f"{event}.json"
    if f.exists():
        return 0
    # Markets settled before Kalshi's historical cutoff are served only by the /historical endpoints.
    historical = True
    markets = get("/historical/markets", {"event_ticker": event, "limit": 1000}).get("markets", [])
    if not markets:
        historical = False
        markets = get("/markets", {"event_ticker": event, "limit": 1000})["markets"]
    keep = ["ticker", "floor_strike", "cap_strike", "strike_type", "result", "volume_fp", "open_time", "close_time",
            "expiration_value"]
    rows = []
    for m in markets:
        r = {k: m.get(k) for k in keep}
        cs = m.get("custom_strike") or {}
        if r["strike_type"] == "custom" and cs.get("strike_type"):
            # Some series (DOGE) carry the strike in custom_strike instead of floor_strike.
            r["strike_type"] = cs["strike_type"]
            r["floor_strike"] = float(cs["floor_strike"]) if cs.get("floor_strike") else None
            r["cap_strike"] = float(cs["cap_strike"]) if cs.get("cap_strike") else None
        rows.append(r)
    import math

    import pandas as pd

    ref = spot(pd.Timestamp(rows[0]["open_time"])) if spot and rows else None
    n = 0
    for m in rows:
        k = float(m["floor_strike"]) if m["floor_strike"] is not None else None
        near = ref is None or (k is not None and k > 0 and abs(math.log(k / ref)) <= BAND)
        m["trades_fetched"] = bool(near)
        if near and float(m["volume_fp"] or 0) > 0:
            m["trades"] = [{"t": t["created_time"], "p": float(t["yes_price_dollars"]), "c": float(t["count_fp"]),
                            "side": t.get("taker_side")} for t in trades(m["ticker"], historical)]
            n += len(m["trades"])
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps({"event": event, "historical": historical, "band_ref": ref, "markets": rows}))
    tmp.rename(f)
    return n


def download_all(dest: Path, data: Path) -> None:
    from . import market

    dest.mkdir(parents=True, exist_ok=True)
    c1m = market.load_klines(data, "1m")
    for s in SERIES:
        px = c1m[SPOT[s]].dropna()

        def spot(ts, px=px):
            i = px.index.searchsorted(ts, side="right") - 1
            return float(px.iloc[i]) if i >= 0 else None

        events = five_pm_events(s)
        print(f"{s}: {len(events)} events, {events[0] if events else None} to {events[-1] if events else None}", flush=True)
        for i, e in enumerate(events):
            n = download_event(e, dest, spot)
            if i % 25 == 0:
                print(f"  {e} {i + 1}/{len(events)} trades {n}", flush=True)
