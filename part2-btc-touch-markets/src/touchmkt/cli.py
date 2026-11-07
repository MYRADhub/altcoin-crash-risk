"""Command line entry points.

    python -m touchmkt.cli download-binance     # BTCUSDT 1-minute klines, funding, Fear & Greed
    python -m touchmkt.cli download-polymarket  # daily, weekly and monthly "What price will Bitcoin hit" events and trades
    python -m touchmkt.cli download-deribit     # every short-dated BTC option trade, one file per day
    python -m touchmkt.cli download-kalshi      # KXBTCD 5 pm ET ladders (after download-binance)
    python -m touchmkt.cli run                  # price every trade, run every test, write results/
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RESULTS = ROOT / "results"


def run(reuse: bool = False) -> None:
    import json

    import numpy as np
    import pandas as pd

    from . import build, evaluate, secondary

    RESULTS.mkdir(parents=True, exist_ok=True)
    derived = DATA / "derived" / "trades.csv.gz"
    if reuse and derived.exists():
        tr = pd.read_csv(derived)
        for c in ("t", "start", "end", "touch_at"):
            tr[c] = pd.to_datetime(tr[c], utc=True, format="ISO8601")
        tr["day"] = pd.to_datetime(tr["day"])
        meta = json.loads((DATA / "derived" / "meta.json").read_text())
    else:
        tr, mk, meta = build.build(DATA)
        derived.parent.mkdir(parents=True, exist_ok=True)
        tr.to_csv(derived, index=False, float_format="%.6f")
        (DATA / "derived" / "meta.json").write_text(json.dumps(meta))
    out = {"meta": meta, "events": int(tr["event"].nunique()), "markets": int(tr["market"].nunique()), "trades": int(len(tr)),
           "by_kind_events": tr.groupby("kind")["event"].nunique().to_dict(),
           "primary": evaluate.primary(tr)}
    out["sensitivity"] = {"GBM barrier": evaluate.primary(tr, "GBM"), "digital lower bound": evaluate.primary(tr, "D")}
    out["by_kind"] = evaluate.premium_table(tr, "kind")
    tr["dist"] = pd.cut(tr["x"].abs(), [0, 0.02, 0.05, 0.1, 0.2, 5], labels=["<2%", "2-5%", "5-10%", "10-20%", ">20%"])
    out["by_distance"] = evaluate.premium_table(tr, "dist")
    w = tr["size"].to_numpy()
    out["calibration"] = {m: evaluate.calibration(tr[m].to_numpy(), tr["y"].to_numpy(), w) for m in ("p", "FAIR")}
    out["trading"] = {f: evaluate.trade_summary(evaluate.trade(tr, f)) for f in ("FAIR", "GBM")}
    out["trading_by_kind"] = {k: evaluate.trade_summary(evaluate.trade(g)) for k, g in tr.groupby("kind")}
    out["mood"] = secondary.mood(tr, secondary.signals(DATA / "binance"))
    if (DATA / "kalshi").exists():
        out["kalshi_bound"] = secondary.kalshi_bound(tr, secondary.load_kalshi(DATA / "kalshi"))
    out["fit_age_minutes_median"] = float(np.median(tr["fit_age_min"]))
    (RESULTS / "summary.json").write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps({k: out[k] for k in ("meta", "events", "trades", "by_kind_events", "primary")}, indent=1, default=str))


def main(argv: list[str]) -> None:
    from . import download as dl

    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "download-binance":
        dl.download_binance(DATA / "binance")
    elif cmd == "download-polymarket":
        dl.download_polymarket(DATA / "polymarket")
    elif cmd == "download-deribit":
        dl.download_deribit(DATA / "deribit")
    elif cmd == "download-kalshi":
        dl.download_kalshi(DATA / "kalshi", dl.load_klines(DATA / "binance")["close"])
    elif cmd == "run":
        run(reuse="--reuse" in argv)
    else:
        raise SystemExit(f"unknown command {cmd!r}")


if __name__ == "__main__":
    main(sys.argv)
