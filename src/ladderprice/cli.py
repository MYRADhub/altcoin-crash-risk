"""Command line entry points.

    python -m ladderprice.cli download-kalshi   # Kalshi 5 pm ET altcoin ladders into data/kalshi
    python -m ladderprice.cli download-market   # Binance klines and funding, Deribit DVOL, Fear & Greed
    python -m ladderprice.cli download-polymarket  # Polymarket SOL and XRP daily ladders into data/polymarket
    python -m ladderprice.cli run               # build prints, score every model, write results/
    python -m ladderprice.cli deck              # rebuild the presentation's data file
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RESULTS = ROOT / "results"


def run() -> None:
    import json

    from . import build, evaluate

    RESULTS.mkdir(parents=True, exist_ok=True)
    prints, meta = build.build(DATA)
    (DATA / "derived").mkdir(parents=True, exist_ok=True)
    prints.to_csv(DATA / "derived" / "prints.csv.gz", index=False, float_format="%.6f")
    evaluate.event_scores(prints, evaluate.MODELS).to_csv(RESULTS / "event_scores.csv", index=False, float_format="%.6f")
    M = evaluate.MODELS
    alts = prints[prints["series"].isin(["KXSOLD", "KXXRPD", "KXDOGED"])]
    poly = prints[prints["series"].str.startswith("POLY")]
    out = {"meta": meta, "primary": evaluate.score_set(alts, M, evaluate.PRIMARY),
           "per_coin": {s: evaluate.score_set(g, M, evaluate.PRIMARY) for s, g in alts.groupby("series")}}
    eth = prints[prints["series"] == "KXETHD"]
    if len(eth):
        out["eth_check"] = evaluate.score_set(eth, M + ["ETHOPT"], ["ETHOPT", "MKT", "OWN"])
        out["eth_check"]["corr_factor_ethopt"] = float(eth[["FACTOR", "ETHOPT"]].corr().iloc[0, 1])
    sens = {
        "equal weight per print": (alts, False),
        "horizon at least 3 hours": (alts[alts["h"] >= 3], True),
        "prices 10 to 90 cents": (alts[(alts["p"] >= 0.1) & (alts["p"] <= 0.9)], True),
        "without the first 90 days": (alts[alts["day"] >= alts["day"].min() + pd.Timedelta(days=90)], True),
    }
    out["sensitivity"] = {k: evaluate.score_set(d, M, evaluate.PRIMARY, weighted=w) for k, (d, w) in sens.items()}
    out["trading"] = {m: evaluate.trade_summary(evaluate.trade(alts, m)) for m in ("OWN", "BETA", "CRASH", "FACTOR")}
    out["trading_per_coin"] = {s: evaluate.trade_summary(evaluate.trade(g, "FACTOR")) for s, g in alts.groupby("series")}
    if len(eth):
        out["trading_eth"] = {m: evaluate.trade_summary(evaluate.trade(eth, m)) for m in ("FACTOR", "ETHOPT")}
    if len(poly):
        out["polymarket"] = {"pooled": evaluate.score_set(poly, M, evaluate.PRIMARY),
                             "per_coin": {s: evaluate.score_set(g, M, evaluate.PRIMARY) for s, g in poly.groupby("series")},
                             "trading": {m: evaluate.trade_summary(evaluate.trade(poly, m)) for m in ("OWN", "FACTOR")}}
    out["liquidity_usd_per_event"] = liquidity(prints)
    (RESULTS / "summary.json").write_text(json.dumps(out, indent=2, default=str))
    figure(prints, out, RESULTS / "results.png")
    p = out["primary"]
    print(json.dumps({"events": p["events"], "brier": p["brier"], "tests": p["tests"], "trading": out["trading"]}, indent=1, default=str))


NAMES = {"KXSOLD": "SOL", "KXXRPD": "XRP", "KXDOGED": "DOGE", "KXETHD": "ETH (check)", "POLY-SOL": "SOL Poly", "POLY-XRP": "XRP Poly"}


def liquidity(prints: pd.DataFrame) -> dict:
    """Median dollars traded per event over qualifying prints, by series."""
    d = prints.assign(usd=prints["count"] * prints["p"]).groupby(["series", "event"])["usd"].sum()
    return d.groupby("series").median().to_dict()


def figure(prints: pd.DataFrame, summary: dict, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    from . import evaluate

    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    alts = prints[prints["series"].isin(["KXSOLD", "KXXRPD", "KXDOGED"])]
    ax = axes[0, 0]
    liq = liquidity(prints)
    pts = [(k, v) for k, v in [("KXSOLD", summary["per_coin"].get("KXSOLD")), ("KXXRPD", summary["per_coin"].get("KXXRPD")),
                                 ("KXDOGED", summary["per_coin"].get("KXDOGED")), ("KXETHD", summary.get("eth_check"))]
           + list(summary.get("polymarket", {}).get("per_coin", {}).items()) if v]
    for k, v in pts:
        gap = 1000 * (v["brier"]["MKT"] - v["brier"]["OWN"])
        c = "#e37400" if k.startswith("POLY") else "#1a73e8"
        ax.scatter(liq[k], gap, s=60, color=c)
        ax.annotate(NAMES[k], (liq[k], gap), textcoords="offset points", xytext=(6, 4), fontsize=8)
    ax.set_xscale("log")
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xlabel("Median dollars traded per ladder (qualifying prints, log scale)")
    ax.set_ylabel("Market's Brier minus own-volatility model's, x1000")
    ax.set_title("Thinner ladders are priced worse (descriptive, after the fact)")
    ax = axes[0, 1]
    groups = [("KXSOLD", summary["per_coin"].get("KXSOLD")), ("KXXRPD", summary["per_coin"].get("KXXRPD")),
              ("KXDOGED", summary["per_coin"].get("KXDOGED")), ("KXETHD", summary.get("eth_check"))]
    if "polymarket" in summary:
        groups += [(k, v) for k, v in summary["polymarket"]["per_coin"].items()]
    groups = [(k, v) for k, v in groups if v]
    x = np.arange(len(groups))
    for i, (m, c) in enumerate((("OWN", "#9aa0a6"), ("FACTOR", "#1a73e8"))):
        ax.bar(x + (i - 0.5) * 0.36, [v["brier"][m] - groups[j][1]["brier"]["MKT"] for j, (k, v) in enumerate(groups)], 0.36, color=c,
               label={"OWN": "Own-volatility model", "FACTOR": "Factor model from BTC options"}[m])
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xticks(x, [NAMES[k] for k, _ in groups], fontsize=8)
    ax.set_ylabel("Brier score minus the market's (below 0 = better)")
    ax.set_title("Brier score against the market price (below 0 = beats the market)")
    ax.legend(fontsize=8, frameon=False)

    ax = axes[1, 0]
    for s, c in (("KXSOLD", "#e37400"), ("KXXRPD", "#1a73e8"), ("KXDOGED", "#0b8043")):
        tr = evaluate.trade(prints[prints["series"] == s], "FACTOR")
        if tr.empty:
            continue
        d = tr.groupby("day")[["pnl", "cost"]].sum().sort_index()
        ax.plot(pd.to_datetime(d.index), d["pnl"].cumsum() / 1000, color=c, label=f"{NAMES[s]}: {100 * d['pnl'].sum() / d['cost'].sum():+.1f}% per $")
    ax.axhline(0, color="black", lw=0.8)
    ax.set_ylabel("Cumulative profit, $ thousands")
    ax.set_title("Buy-when-cheap rule on Kalshi prints, after fees (optimistic fills)")
    ax.legend(fontsize=8, frameon=False)

    ax = axes[1, 1]
    eth = prints[prints["series"] == "KXETHD"].sample(min(4000, (prints["series"] == "KXETHD").sum()), random_state=0)
    if len(eth):
        ax.scatter(100 * eth["ETHOPT"], 100 * eth["FACTOR"], s=3, alpha=0.3, color="#1a73e8")
        ax.plot([0, 100], [0, 100], color="black", lw=0.8)
        ax.set_xlabel("From ETH's own options (DVOL), %")
        ax.set_ylabel("From BTC options through the factor model, %")
        ax.set_title(f"ETH check: correlation {summary['eth_check']['corr_factor_ethopt']:.3f}")
    fig.tight_layout()
    fig.savefig(path, dpi=150)


def main(argv: list[str]) -> None:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "download-kalshi":
        from . import kalshi

        kalshi.download_all(DATA / "kalshi", DATA)
    elif cmd == "download-polymarket":
        from . import polymarket

        polymarket.download_all(DATA / "polymarket")
    elif cmd == "run":
        run()
    elif cmd == "deck":
        from . import deck

        print(deck.build(ROOT))
    elif cmd == "download-market":
        from . import market

        market.download_all(DATA)
    else:
        raise SystemExit(f"unknown command {cmd!r}")


if __name__ == "__main__":
    main(sys.argv)
