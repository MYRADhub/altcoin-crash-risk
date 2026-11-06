"""Daily klines for every Binance spot USDT pair, including delisted ones, for the reversal follow-up.

Source: https://data.binance.vision (Binance public archive, spot monthly klines). The bucket listing
includes pairs that no longer trade, so the universe on each day is the one that existed that day.
Files are cached as the original monthly zips under data/universe/<SYMBOL>/.
"""

from __future__ import annotations

import io
import re
import urllib.parse
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from .market import _get

BUCKET = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
FILES = "https://data.binance.vision"
PREFIX = "data/spot/monthly/klines/"
START, END = "2019-09", "2026-10"
FOLLOWUP_START = "2024-01-01"  # the ladder-period follow-up uses data from here only

STABLE_OR_PEGGED = {
    "USDC", "BUSD", "TUSD", "USDP", "PAX", "DAI", "FDUSD", "UST", "USTC", "USDS", "USDSB",
    "SUSD", "GUSD", "EUR", "GBP", "AUD", "TRY", "BRL", "RUB", "NGN", "UAH", "BIDR", "IDRT",
    "BKRW", "ZAR", "AEUR", "EURI", "USDE", "USD1", "XUSD", "BFUSD", "RLUSD", "PYUSD", "USDQ",
    "PAXG", "XAUT", "WBTC", "WBETH", "BETH", "BNSOL", "BBTC", "U", "RWUSD", "USDSOLD",
}
LEVERAGED = re.compile(r"(UP|DOWN|BULL|BEAR)$")
# Tokenized stocks and ETFs listed in 2026 end in "B" (AAPLB, SPYB); excluded when first listed in 2026.
EQUITY_LIKE = re.compile(r"^[A-Z]{2,6}B$")


def is_token(symbol: str) -> bool:
    """True for a USDT pair whose base is a crypto token (not a stablecoin, fiat, wrapper or leveraged token)."""
    if not symbol.endswith("USDT") or len(symbol) <= 4:
        return False
    base = symbol[:-4]
    if base in STABLE_OR_PEGGED:
        return False
    return not (LEVERAGED.search(base) and base not in {"JUP", "SUP"})


def _list(prefix: str, delimiter: str | None) -> tuple[list[str], list[str]]:
    keys: list[str] = []
    prefixes: list[str] = []
    marker = ""
    while True:
        q = {"prefix": prefix, "max-keys": "1000"}
        if delimiter:
            q["delimiter"] = delimiter
        if marker:
            q["marker"] = marker
        xml = _get(f"{BUCKET}?{urllib.parse.urlencode(q)}").decode()
        page_keys = re.findall(r"<Key>([^<]+)</Key>", xml)
        page_prefixes = re.findall(r"<Prefix>([^<]+)</Prefix>", xml)[1:]
        keys += page_keys
        prefixes += page_prefixes
        if "<IsTruncated>true</IsTruncated>" not in xml:
            break
        nxt = re.search(r"<NextMarker>([^<]+)</NextMarker>", xml)
        marker = nxt.group(1) if nxt else (page_keys or page_prefixes)[-1]
    return keys, prefixes


def _month(key: str) -> str:
    m = re.search(r"-(\d{4}-\d{2})\.zip$", key)
    return m.group(1) if m else ""


def download(dest: Path, workers: int = 16) -> int:
    _, prefixes = _list(PREFIX, "/")
    symbols = [p[len(PREFIX):].rstrip("/") for p in prefixes]
    symbols = [s for s in symbols if is_token(s)]

    def one(sym: str) -> int:
        keys, _ = _list(f"{PREFIX}{sym}/1d/", None)
        keys = [k for k in keys if k.endswith(".zip") and START <= _month(k) <= END]
        if not keys:
            return 0
        if EQUITY_LIKE.match(sym[:-4]) and min(_month(k) for k in keys) >= "2026-01":
            return 0
        out = dest / sym
        out.mkdir(parents=True, exist_ok=True)
        n = 0
        for k in keys:
            f = out / k.rsplit("/", 1)[1]
            if f.exists() and f.stat().st_size > 0:
                continue
            try:
                f.write_bytes(_get(f"{FILES}/{urllib.parse.quote(k)}"))
                n += 1
            except (RuntimeError, OSError) as e:
                failed.append(f"{k}: {e}")
        return n

    failed: list[str] = []
    dest.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(workers) as pool:
        n = sum(pool.map(one, symbols))
    print(f"{len(symbols)} USDT token pairs listed, {n} new monthly files, {len(failed)} failed (rerun to retry)")
    for f in failed:
        print("  failed:", f)
    return n


def _frame(raw: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(raw), header=None)
    df = df[pd.to_numeric(df[0], errors="coerce").notna()]
    t = df[0].astype("int64").to_numpy()
    sec = np.where(t > 10 ** 14, t // 10 ** 6, t // 10 ** 3)
    return pd.DataFrame({"day": pd.to_datetime(sec, unit="s").normalize(), "close": df[4].astype(float).to_numpy(),
                         "qvol": df[7].astype(float).to_numpy()})


def load(dest: Path, start: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Daily close and quote volume panels (UTC day of the bar's open, by symbol), from `start` if given."""
    close, qvol = {}, {}
    for d in sorted(p for p in dest.iterdir() if p.is_dir()):
        parts = []
        for f in sorted(d.glob("*.zip")):
            with zipfile.ZipFile(f) as z:
                for n in z.namelist():
                    parts.append(_frame(z.read(n)))
        if not parts:
            continue
        df = pd.concat(parts).drop_duplicates("day").set_index("day").sort_index()
        if start:
            df = df[df.index >= start]
        if df.empty:
            continue
        close[d.name], qvol[d.name] = df["close"], df["qvol"]
    return pd.DataFrame(close).sort_index(), pd.DataFrame(qvol).sort_index()
