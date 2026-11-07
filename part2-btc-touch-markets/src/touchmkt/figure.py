"""results/results.png from results/summary.json and results/kalshi_violations_exploratory.json.

    python -m touchmkt.figure
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    s = json.loads((ROOT / "results" / "summary.json").read_text())
    v = json.loads((ROOT / "results" / "kalshi_violations_exploratory.json").read_text())
    fig, ax = plt.subplots(2, 2, figsize=(13, 9))

    a = ax[0, 0]
    for key, name, c in (("p", "Polymarket price", "#d93025"), ("FAIR", "Options value (2 x digital)", "#1a73e8")):
        cal = s["calibration"][key]
        a.plot([b["mean_price"] for b in cal], [b["win_rate"] for b in cal], "o-", color=c, label=name)
    a.plot([0, 1], [0, 1], color="black", lw=0.8)
    a.set_xlabel("Price or fair value")
    a.set_ylabel("Share of contracts that touched")
    a.set_title("Calibration: the crowd is at least as well calibrated as the options value")
    a.legend(frameon=False, fontsize=8)

    a = ax[0, 1]
    fairs = [("primary", "2 x digital (primary)"), ("GBM barrier", "Barrier formula"), ("digital lower bound", "Finish beyond (lower bound)")]
    x = np.arange(len(fairs))
    for i, (d, c) in enumerate((("reach", "#1a73e8"), ("dip", "#e37400"))):
        vals, lo, hi = [], [], []
        for k, _ in fairs:
            t = (s["primary"] if k == "primary" else s["sensitivity"][k])[f"{d} premium"]
            vals.append(100 * t["est"]); lo.append(100 * (t["est"] - t["lo"])); hi.append(100 * (t["hi"] - t["est"]))
        a.bar(x + (i - 0.5) * 0.36, vals, 0.36, yerr=[lo, hi], color=c, label=f"{d.capitalize()} markets", capsize=3)
    a.axhline(0, color="black", lw=0.8)
    a.set_xticks(x, [n for _, n in fairs], fontsize=8)
    a.set_ylabel("Market price minus fair value, cents")
    a.set_title("The crowd sits between the two option models")
    a.legend(frameon=False, fontsize=8)

    a = ax[1, 0]
    labels = ["<2%", "2-5%", "5-10%", "10-20%", ">20%"]
    for i, (d, c) in enumerate((("reach", "#1a73e8"), ("dip", "#e37400"))):
        ts = [s["by_distance"].get(f"{l}|{d}") for l in labels]
        a.errorbar(np.arange(5) + (i - 0.5) * 0.15, [100 * t["est"] for t in ts],
                   yerr=[[100 * (t["est"] - t["lo"]) for t in ts], [100 * (t["hi"] - t["est"]) for t in ts]], fmt="o", color=c,
                   label=f"{d.capitalize()} markets", capsize=3)
    a.axhline(0, color="black", lw=0.8)
    a.set_xticks(np.arange(5), labels)
    a.set_xlabel("Distance of the strike from spot")
    a.set_ylabel("Market minus 2 x digital, cents")
    a.set_title("Against the primary value, by distance")
    a.legend(frameon=False, fontsize=8)

    a = ax[1, 1]
    steps = [("Price below the bound\nafter fees", v["violations"]), ("Within 60 s,\nBTC flat", v["within_60s_and_flat"]),
             ("On tradeable\nsides", v["all_three"])]
    a.bar(range(3), [n for _, n in steps], color=["#9aa0a6", "#9aa0a6", "#d93025"], width=0.55)
    for i, (_, n) in enumerate(steps):
        a.text(i, n + 4, str(n), ha="center")
    a.set_xticks(range(3), [l for l, _ in steps], fontsize=8)
    a.set_ylabel("Paired trades")
    kb = s["kalshi_bound"]
    a.set_title(f"Touch vs Kalshi 'beyond at 5 pm': {kb['pairs']:,} pairs")
    fig.tight_layout()
    fig.savefig(ROOT / "results" / "results.png", dpi=150)


if __name__ == "__main__":
    main()
