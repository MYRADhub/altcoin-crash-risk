import numpy as np
import pandas as pd

from touchmkt import evaluate as E


def test_block_mean_detects_planted_premium_and_not_noise():
    rng = np.random.default_rng(0)
    days = np.repeat(np.arange(200), 2)
    hit = E.test_mean(0.03 + rng.normal(0, 0.05, 400), days)
    null = E.test_mean(rng.normal(0, 0.05, 400), days)
    assert hit["p"] < 0.01 and hit["lo"] > 0 and null["p"] > 0.05 and null["lo"] < 0 < null["hi"]


def test_holm_is_monotone_and_capped():
    t = E.holm({"a": {"p": 0.01}, "b": {"p": 0.04}, "c": {"p": 0.5}})
    assert t["a"]["p_holm"] == 0.03 and t["b"]["p_holm"] == 0.08 and t["c"]["p_holm"] == 0.5


def test_event_means_weight_by_shares():
    tr = pd.DataFrame({"event": ["e"] * 2, "day": [1, 1], "kind": ["daily"] * 2, "size": [3.0, 1.0], "v": [1.0, 5.0]})
    assert E.event_means(tr, ["v"])["v"].iloc[0] == 2.0


def test_trade_rule_buys_cheap_side_after_fee():
    tr = pd.DataFrame({"FAIR": [0.6, 0.2, 0.52], "p": [0.5, 0.3, 0.5], "y": [1.0, 0.0, 1.0], "size": [10.0, 10.0, 10.0],
                       "day": [1, 1, 1], "kind": ["daily"] * 3, "direction": ["reach"] * 3})
    t = E.trade(tr)
    assert list(t["side"]) == ["yes", "no"]  # the 2-cent gap on the third does not clear the fee plus edge
    fee = 0.07 * 0.25
    assert abs(t["pnl"].iloc[0] - 5 * (1 - 0.5 - fee)) < 1e-12
