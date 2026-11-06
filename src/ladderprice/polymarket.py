"""Download Polymarket SOL and XRP daily "above K at 12:00 ET" ladders and their trades (public APIs).

Events come from gamma-api.polymarket.com by slug, trades from data-api.polymarket.com/v2/trades.
Only time, price, size and outcome of each trade are kept; no wallet or user fields are stored.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

GAMMA = "https://gamma-api.polymarket.com/events"
TRADES = "https://data-api.polymarket.com/v2/trades"
COINS = {"solana": "SOLUSDT", "xrp": "XRPUSDT"}
MIN_GAP = 0.25
_last = [0.0]


def get(url: str, retries: int = 6):
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
            if e.code in (400, 404, 410):
                raise
            time.sleep(min(2 ** attempt, 30))
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(min(2 ** attempt, 30))
    raise RuntimeError(f"failed: {url}")


def slug(coin: str, day: pd.Timestamp) -> str:
    return f"{coin}-above-on-{day.strftime('%B').lower()}-{day.day}-{day.year}"


def strike(question: str) -> float:
    """'Will the price of XRP be above $0.80 on November 1?' -> 0.8."""
    return float(re.search(r"above \$([\d,]+(?:\.\d+)?)", question).group(1).replace(",", ""))


def trades(condition_id: str) -> list[dict]:
    out, cursor = [], None
    while True:
        q = {"condition_id": condition_id, "limit": 500}
        if cursor:
            q["cursor"] = cursor
        r = get(f"{TRADES}?{urllib.parse.urlencode(q)}")
        out += [{"ts": t["timestamp"], "p_yes": t["price"] if t["outcome"] == "Yes" else 1 - t["price"], "size": t["size"],
                 "side": t["side"], "outcome": t["outcome"]} for t in r["data"]]
        cursor = r["pagination"].get("next_cursor")
        if not r["pagination"].get("has_more") or not cursor:
            return out


def download_all(dest: Path, start: str = "2026-01-01", end: str = "2026-10-31") -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for coin in COINS:
        n = 0
        for day in pd.date_range(start, end, freq="D"):
            s = slug(coin, day)
            f = dest / f"{s}.json"
            if f.exists():
                continue
            ev = get(f"{GAMMA}?slug={s}")
            if not ev:
                continue
            e = ev[0]
            mk = []
            for m in e["markets"]:
                prices = json.loads(m.get("outcomePrices") or "[]")
                if not m.get("closed") or len(prices) != 2:
                    continue
                mk.append({"question": m["question"], "strike": strike(m["question"]), "end": m["endDate"],
                           "yes_won": float(prices[0]) > 0.5, "volume": float(m.get("volume") or 0),
                           "trades": trades(m["conditionId"]) if float(m.get("volume") or 0) > 0 else []})
            f.write_text(json.dumps({"slug": s, "coin": coin, "start": e.get("startDate"), "end": e.get("endDate"), "markets": mk}))
            n += 1
        print(f"{coin}: {n} events", flush=True)
