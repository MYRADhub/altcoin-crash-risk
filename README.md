# Pricing altcoin prediction markets from BTC options

Kalshi lists a daily ladder of contracts for SOL, XRP and DOGE: "will the price be above K at 5 pm ET?" These coins have no liquid options market, so nothing anchors the ladder prices, and they trade 5 to 70 times less than the ETH ladder. I asked whether a crypto factor model can price them better than the market. The model takes BTC's forward-looking volatility from the options market, maps it to each altcoin through a beta that is steeper when BTC falls, and adjusts the altcoin's own risk by funding crowding and the Fear & Greed regime.

**Answer.**
- **Models beat the market on the thin ladders.** Over 1,117 Kalshi ladders from August 2025 to October 2026, the factor model's Brier score was 0.130 against the market's 0.138 (Holm p = 0.002). The gap is large for XRP and DOGE and close to zero for SOL. It held in every sensitivity check.
- **The thinner the ladder, the worse the market prices it.** On DOGE, about $290 trades per ladder, and the market lost to every model. On ETH, about $20,600 trades per ladder, and the market beat every model.
- **BTC options are a working substitute for missing options.** On ETH, which does have options, the BTC-based factor model priced contracts almost exactly like ETH's own options (correlation 0.998, no significant score difference).
- **But the factor layers added nothing.** The altcoin's own recent volatility did as well or slightly better (p = 0.066 after adjustment). The steeper down-beta and the funding and mood adjustments did not improve on plain beta.
- **Money.** Buying on Kalshi whenever the model priced a contract at least 4 cents above the trade price plus the fee returned +4.7% per dollar (95% interval 1.1% to 8.8%): +8.6% on XRP, +7.0% on DOGE and +0.8% on SOL. This assumes we could have traded at each printed price, which is optimistic.

![Liquidity and mispricing, scores against the market, the trading rule, and the ETH check](results/results.png)

The plan, every model and every test were written in `research.md` before any model was compared with any outcome. Two amendments, both made before any score, are dated there.

## Why it matters

Prediction markets now list daily price ladders for many coins, but only BTC and ETH have options markets to anchor a fair value. For BTC and ETH, reading these contracts as digital options is established ([Lee, Lee and Lee 2026](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6748186)). Crypto factor models, from market, size and momentum ([Liu, Tsyvinski and Wu 2022](https://doi.org/10.1111/jofi.13119)) to practitioner models with residual volatility, funding and sentiment regimes, are built to describe risk. This project tests whether such a model can serve as a pricing engine where no options exist. I found no prior work that prices altcoin prediction-market contracts this way.

## Data

All public, downloaded 2026-11-06:
- **Kalshi** KXSOLD, KXXRPD, KXDOGED and KXETHD events closing at 5 pm ET, with market metadata and trades from the public Trade API v2. Settlement is the 60-second average of the CF Benchmarks real-time index before 5 pm ET. Trades were fetched for strikes within 10% of spot when the ladder listed.
- **Polymarket** SOL and XRP daily "above K at 12:00 ET" ladders, May to October 2026, with trades from the public data API v2 (time, price, size and outcome only).
- **Binance** spot 1-minute and 1-hour klines for BTC, ETH, SOL, XRP and DOGE, and USDT-M funding rates ([public archive](https://data.binance.vision)).
- **Deribit DVOL**, BTC's and ETH's 30-day implied volatility index, hourly (public API).
- **Alternative.me Fear & Greed index**, daily.

## Method

A **print** is a Kalshi trade with 1 to 24 hours left to the close and a price from 5 to 95 cents. Each print's price is the market's probability. Every model gives its own probability for the same contract at the same moment, using only data from before the print:

| Model | Probability that the coin closes above K |
| --- | --- |
| Market | The trade price |
| Own volatility | The coin's own recent volatility (HAR: 1, 7 and 30 days of hourly returns), fat-tailed Student-t |
| Beta | BTC's distribution from its options (DVOL, rescaled by the past 90 days' realized moves), times the coin's 30-day beta to BTC, plus the coin's own residual risk |
| Crash beta | The same, with a steeper beta for BTC falls than for rises |
| Factor model | Crash beta, with the residual risk scaled by what past days in the same Fear & Greed regime and funding-crowding state looked like |

Scores: Brier score per print, weighted by contracts within each ladder, then averaged across ladders. Comparisons use a bootstrap over blocks of 10 days and a Holm adjustment over three primary tests.

## Results

**Primary test: SOL, XRP and DOGE on Kalshi** (1,117 ladders, 455 days, 193,247 prints).

| Model | Brier score | Factor model minus this | 95% interval | Holm p |
| --- | ---: | ---: | ---: | ---: |
| Market | 0.1377 | -0.0075 | -0.0105 to -0.0042 | 0.002 |
| Own volatility | 0.1293 | +0.0010 | +0.0001 to +0.0019 | 0.066 |
| Beta | 0.1299 | +0.0004 | -0.0001 to +0.0008 | 0.093 |
| Crash beta | 0.1302 | | | |
| Factor model | 0.1303 | | | |

**By coin and venue.** "Market edge" is the market's Brier score minus the own-volatility model's; positive means the market was worse.

| Ladder | Ladders | Median $ per ladder | Market | Own volatility | Factor model | Market edge | Factor vs market, p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DOGE, Kalshi | 428 | 290 | 0.1418 | 0.1288 | 0.1305 | +0.0129 | 0.006 |
| XRP, Kalshi | 374 | 1,980 | 0.1363 | 0.1274 | 0.1274 | +0.0088 | 0.003 |
| SOL, Kalshi | 315 | 4,140 | 0.1340 | 0.1321 | 0.1333 | +0.0019 | 0.67 |
| ETH, Kalshi (check) | 456 | 20,560 | 0.1327 | 0.1338 | 0.1357 | -0.0011 | market better, 0.018 |
| XRP, Polymarket | 158 | 1,260 | 0.1213 | 0.1102 | 0.1094 | +0.0111 | 0.36 |
| SOL, Polymarket | 158 | 1,800 | 0.0974 | 0.0949 | 0.0962 | +0.0025 | 0.46 |

The ordering by liquidity is descriptive and was noticed after the results; it was not a planned test. With six points, two venues and correlated coins, it is a pattern to check, not a finding.

**ETH check.** On ETH the factor model, built from BTC's options, and ETHOPT, built from ETH's own options, scored 0.1357 and 0.1359 (difference -0.0002, 95% interval -0.0010 to 0.0006). Their probabilities correlate at 0.998. Where an options market exists, mapping from BTC loses nothing, so the mapping is a fair stand-in where none exists. On ETH, though, the market beat every model.

**Sensitivities** (fixed in advance; factor model minus market, Holm p):

| Variant | Difference | Holm p |
| --- | ---: | ---: |
| Equal weight per print | -0.0061 | 0.002 |
| At least 3 hours to the close | -0.0075 | 0.002 |
| Prices from 10 to 90 cents | -0.0083 | 0.002 |
| Without the first 90 days | -0.0076 | 0.002 |

**Trading rule (secondary).** At each print, buy the side the model prices at least 4 cents above the price plus Kalshi's taker fee (0.07 × p × (1 - p)). Take half the print's contracts, at most $200 per print, and hold to settlement.

| Venue and coin | Return per dollar | 95% interval | Days traded | Profit | Capital used over the period |
| --- | ---: | ---: | ---: | ---: | ---: |
| Kalshi, all three (factor model) | +4.7% | +1.1% to +8.8% | 453 | $57k | $1.21M |
| Kalshi, all three (own volatility) | +4.5% | +1.0% to +8.1% | 454 | $58k | $1.30M |
| XRP | +8.6% | +3.8% to +13.5% | 372 | $45k | $0.52M |
| DOGE | +7.0% | +0.5% to +13.1% | 422 | $8k | $0.11M |
| SOL | +0.8% | -4.5% to +5.9% | 314 | $5k | $0.57M |
| ETH (check) | +2.5% | -0.4% to +5.5% | 455 | $59k | $2.30M |
| Polymarket SOL and XRP | -0.4% | -6.2% to +5.0% | 159 | -$1k | $0.23M |

This rule trades at prices that someone else already got, so real returns would be lower. It shows that the scoring gap is large enough to matter after fees, mainly on XRP.

## Limitations and what did not work

- **The factor adjustments did not help.** Steeper down-betas, funding crowding and the Fear & Greed regime did not beat plain beta, and nothing beat the coin's own recent volatility. Over a 1-to-24-hour horizon the coin's own price history already carries the information, and BTC's options add nothing to it.
- **About a year of data** per coin, and the three coins move together. All three fell over the sample, which hurt every forecast that assumes no drift.
- **Prints are not quotes.** A print shows where someone traded, not a price we could have had. The trading results are an upper bound.
- **Settlement basis.** Kalshi settles on CF Benchmarks indices; the models use Binance USDT prices.
- **Polymarket** has only five months of ladders, and its results are not significant.

**Attempts log.** The plan was fixed before any score. Two amendments followed, both before any score, after input checks: weighting prints by contracts, because of bursts of 1-contract prints at nonsense prices right after a ladder lists, and fetching trades only for strikes within 10% of spot, to keep the download near two hours at 3 requests per second. The scoring ran three times. The first two runs were incomplete because of download bugs: DOGE's strikes sit in a different API field, and a zero strike crashed the downloader. In the first run DOGE was missing entirely, and in the second it was partial. The reported numbers are from the third run, with the plan unchanged. DOGE ladders before August 2025, before the price data starts, were dropped as planned.

## Reproduce

```bash
uv sync
uv run python -m ladderprice.cli download-market      # Binance klines and funding, Deribit DVOL, Fear & Greed (about 150 MB)
uv run python -m ladderprice.cli download-kalshi      # Kalshi ladders and trades, about 2 hours at 3 requests per second
uv run python -m ladderprice.cli download-polymarket  # Polymarket SOL and XRP ladders, about 15 minutes
uv run python -m ladderprice.cli run                  # writes results/ in about 10 minutes
uv run python -m ladderprice.cli deck                 # rebuilds the presentation's data file
uv run pytest
npm start                                             # the slide deck at http://127.0.0.1:4173/
```

## Where I would like feedback

1. Is the coin's own recent volatility really the right benchmark at a 1-to-24-hour horizon, or would a market maker use something faster, such as intraday realized volatility or the order book?
2. Do you see the same liquidity pattern in other thin prediction-market ladders, and is there a volume level above which the crowd reliably beats simple models?
3. Where options do not exist, would you trust a BTC-options mapping (which matched ETH's own options here) for longer horizons, where the coin's own history says less?
