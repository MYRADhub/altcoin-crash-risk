"""Public market data: Binance spot klines and USDT-M funding, Deribit DVOL, Alternative.me Fear & Greed.

Sources:
- Binance public archive, https://data.binance.vision (spot klines, futures/um fundingRate).
- Deribit public API, get_volatility_index_data (hourly DVOL for BTC and ETH).
- Alternative.me Crypto Fear & Greed Index, https://api.alternative.me/fng/ (attribution required).
"""

from __future__ import annotations

import http.client
import io
import json
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ARCHIVE = "https://data.binance.vision/data"
SPOT = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
PERPS = ["ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
START = "2025-07"
END = "2026-10"
DERIBIT = "https://www.deribit.com/api/v2/public/get_volatility_index_data"
FNG_URL = "https://api.alternative.me/fng/?limit=0&format=json"


def _get(url: str, retries: int = 6) -> bytes:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "research-script"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            time.sleep(min(2 ** attempt, 30))
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException):
            time.sleep(min(2 ** attempt, 30))
    raise RuntimeError(f"failed: {url}")


def months(start: str = START, end: str = END) -> list[str]:
    return [p.strftime("%Y-%m") for p in pd.period_range(start, end, freq="M")]


def download_klines(dest: Path, interval: str) -> None:
    for sym in SPOT:
        d = dest / f"klines_{interval}" / sym
        d.mkdir(parents=True, exist_ok=True)
        for m in months():
            f = d / f"{sym}-{interval}-{m}.zip"
            if not f.exists():
                f.write_bytes(_get(f"{ARCHIVE}/spot/monthly/klines/{sym}/{interval}/{sym}-{interval}-{m}.zip"))


def download_funding(dest: Path) -> None:
    d = dest / "funding"
    d.mkdir(parents=True, exist_ok=True)
    for sym in PERPS:
        for m in months("2025-03"):
            f = d / f"{sym}-fundingRate-{m}.zip"
            if not f.exists():
                f.write_bytes(_get(f"{ARCHIVE}/futures/um/monthly/fundingRate/{sym}/{sym}-fundingRate-{m}.zip"))


def download_dvol(dest: Path) -> None:
    for cur in ("BTC", "ETH"):
        start = int(pd.Timestamp(f"{START}-01", tz="UTC").timestamp() * 1000)
        end = int((pd.Period(END, "M").end_time.tz_localize("UTC")).timestamp() * 1000)
        rows = []
        while start < end:
            stop = min(end, start + 900 * 3600 * 1000)
            d = json.loads(_get(f"{DERIBIT}?currency={cur}&start_timestamp={start}&end_timestamp={stop}&resolution=3600"))
            rows += d["result"]["data"]
            start = stop
            time.sleep(0.3)
        df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close"]).drop_duplicates("ts").sort_values("ts")
        df.to_csv(dest / f"dvol_{cur}.csv", index=False)


def download_all(data: Path) -> None:
    data.mkdir(parents=True, exist_ok=True)
    (data / "fng.json").write_bytes(_get(FNG_URL))
    download_dvol(data)
    download_funding(data)
    download_klines(data, "1h")
    download_klines(data, "1m")
    print("market data done", flush=True)


# ---------- loaders ----------


def _kline_frame(raw: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(raw), header=None)
    df = df[pd.to_numeric(df[0], errors="coerce").notna()]
    t = df[0].astype("int64").to_numpy()
    sec = np.where(t > 10 ** 14, t // 10 ** 6, t // 10 ** 3)
    return pd.DataFrame({"open_time": pd.to_datetime(sec, unit="s", utc=True), "close": df[4].astype(float).to_numpy()})


def load_klines(data: Path, interval: str) -> pd.DataFrame:
    """Close price by bar close time (UTC) and symbol. A bar opening at t closes at t + interval."""
    step = pd.Timedelta(interval.replace("m", "min"))
    cols = {}
    for sym in SPOT:
        parts = []
        for f in sorted((data / f"klines_{interval}" / sym).glob("*.zip")):
            with zipfile.ZipFile(f) as z:
                for n in z.namelist():
                    parts.append(_kline_frame(z.read(n)))
        df = pd.concat(parts).drop_duplicates("open_time").sort_values("open_time")
        cols[sym] = pd.Series(df["close"].to_numpy(), index=df["open_time"] + step)
    return pd.DataFrame(cols).sort_index()


def load_funding(data: Path) -> pd.DataFrame:
    """Funding rate per 8 hours, mean over the 7 UTC days before each date, by symbol (date index, UTC)."""
    cols = {}
    for sym in PERPS:
        parts = []
        for f in sorted((data / "funding").glob(f"{sym}-fundingRate-*.zip")):
            with zipfile.ZipFile(f) as z:
                for n in z.namelist():
                    df = pd.read_csv(io.BytesIO(z.read(n)), header=None)
                    if not str(df.iloc[0, 0]).isdigit():
                        df = df.iloc[1:]
                    parts.append(pd.DataFrame({"t": pd.to_datetime(df.iloc[:, 0].astype("int64") // 1000, unit="s"),
                                               "r": df.iloc[:, -1].astype(float).to_numpy()}))
        df = pd.concat(parts).drop_duplicates("t")
        daily = df.groupby(df["t"].dt.normalize())["r"].sum()
        daily = daily.reindex(pd.date_range(daily.index.min(), daily.index.max(), freq="D"))
        cols[sym] = (daily.rolling(7, min_periods=5).mean() / 3.0).shift(1)
    return pd.DataFrame(cols)


def load_dvol(data: Path, cur: str) -> pd.Series:
    """Hourly DVOL close (annualized %, by candle close time UTC)."""
    df = pd.read_csv(data / f"dvol_{cur}.csv")
    return pd.Series(df["close"].to_numpy(), index=pd.to_datetime(df["ts"], unit="ms", utc=True) + pd.Timedelta(hours=1)).sort_index()


def load_fng(data: Path) -> pd.Series:
    rows = json.loads((data / "fng.json").read_text())["data"]
    s = pd.Series({pd.to_datetime(int(r["timestamp"]), unit="s").normalize(): float(r["value"]) for r in rows}).sort_index()
    return s[~s.index.duplicated()]
