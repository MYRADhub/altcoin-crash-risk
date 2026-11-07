# BTC touch markets: research notes and test plan

## Field

**Core problem.** Prediction markets now sell short-dated BTC bets in two shapes. A *terminal* contract pays if BTC is above K at a fixed time (Kalshi's daily ladders, Polymarket's "Bitcoin above K on date"). A *touch* contract pays if BTC trades at K at any moment in a window (Polymarket's "What price will Bitcoin hit" series, resolved on Binance BTC/USDT 1-minute highs and lows). In options language these are digital options and one-touch barrier options. Options desks price one-touches every day; prediction-market crowds price them by intuition.

**Key ideas.**
- A terminal contract is a cash-or-nothing digital. Its fair price is minus the slope of the call price in the strike, so it depends on the volatility smile, not just one volatility.
- A touch contract is a one-touch. For a driftless continuous price, the reflection principle gives P(touch K) = 2 × P(finish beyond K): every path that ends beyond K touched it, and for every path that touched and ended beyond, the mirrored path touched and ended short. Drift, skew and jumps move the ratio below or above 2 a little.
- A model-free bound: P(touch K by T) ≥ P(beyond K at any time t ≤ T in the window). A market that prices touching below finishing beyond is an arbitrage, up to settlement-source differences.
- The favorite-longshot bias: on Kalshi, cheap contracts win less often than their prices imply, more so for prices accepted by takers ([Bürgi, Deng and Whelan 2025](https://www.ucd.ie/economics/t4media/WP2025_19.pdf)).

**State of the art.** Kalshi and Polymarket crypto terminal contracts have been read as digital options and compared with options-implied probabilities ([Lee, Lee and Lee 2026, International Review of Financial Analysis 119](https://www.sciencedirect.com/science/article/abs/pii/S1057521926003601); [arXiv 2606.19517](https://arxiv.org/html/2606.19517) for Polymarket thresholds against Binance options). Several public projects compare Kalshi's BTC ladders with Deribit and find gaps of a few cents that mostly vanish after costs ([implied-odds-research](https://github.com/tavelarocque/implied-odds-research), [edgebook PR 31](https://github.com/milesiscool/edgebook/pull/31)). For touch markets I found one informal analysis of a single monthly Polymarket contract hedged with IBIT options ([podshopguy, "Polymarket overprices volatility"](https://podshopguy.substack.com/p/polymarket-overprices-volatility)) and no systematic study.

**Open problems.** Whether crowds understand path dependence; how large the touch premium is against options; whether it varies with mood and crowding.

**Public data.** Polymarket Gamma API (events, rules) and data API v2 (trades); Deribit history API (every option trade with its implied volatility, free); Binance public archive (1-minute klines); Kalshi Trade API v2; Alternative.me Fear & Greed; Binance funding rates.

**Firm-size lens.** A small firm can trade these markets directly at retail size; capacity is the limit. A large desk would care about the touch premium as evidence of how retail prices path risk.

**Beginner mistakes.** Treating a touch market like a terminal one; using one volatility instead of the smile; ignoring that Deribit options expire at 08:00 UTC while the touch window ends elsewhere; counting already-touched contracts; ignoring that every strike in one event shares one price path.

## Test plan (fixed 2026-11-06, before any data was downloaded)

### Data
- **Polymarket touch events**: every closed event in the daily (series 10200), weekly (10151) and monthly (10016) "What price will Bitcoin hit" series, with each market's question, rules and trades (data API v2). Strike and direction ("reach" or "dip") are parsed from the question, and the window from the rules. The annual event is excluded.
- **Deribit**: every BTC option trade (history API) from the first touch event's start to 2026-11-06, keeping expiries within 40 days of the trade.
- **Binance** BTCUSDT 1-minute klines (high, low, close) over the same period.
- **Kalshi** KXBTCD 5 pm ET ladders over the same period, trades within 8% of spot.
- Fear & Greed index and BTCUSDT funding.

### Unit
A Polymarket trade on a touch market with the window already started, at least 1 hour left, a YES-equivalent price from 3 to 97 cents (a NO trade at q counts as 1 - q), and the barrier not yet touched by the Binance 1-minute high or low up to the minute before the trade. Trades are weighted by shares within each event.

### Fair value from Deribit
For each trade, Deribit trades in the previous 60 minutes on the two expiries bracketing the window end. Per expiry, a quadratic smile in log-moneyness is fitted to total implied variance (at least 8 trades on at least 4 strikes with |log-moneyness| ≤ 0.3; otherwise the last fit up to 6 hours old). Total variance at the strike is interpolated linearly in time to the window end. The forward is the Deribit index price (rates ignored; horizons are at most a month). The digital D = P(beyond K at the window end) is minus the derivative of the Black-Scholes call price with smile volatility, by central difference.

- **FAIR (primary)** = min(1, 2 × D), the reflection value.
- **Sensitivities**: the closed-form barrier probability under geometric Brownian motion with the smile volatility at K; and D itself, the lower bound.

### Primary tests (Holm over three)
1. **Reach premium**: market price minus FAIR on "reach" markets, share-weighted within each event, events equally weighted. Two-sided, moving-block bootstrap over days (10-day blocks, 2,000 draws).
2. **Dip premium**: the same on "dip" markets.
3. **Accuracy**: Brier score of the market price against FAIR on the same trades, paired by event, same bootstrap.

### Secondary
- By series (daily, weekly, monthly) and by distance from spot.
- **Arbitrage bound against Kalshi**: for daily events, each Polymarket trade is paired with the last Kalshi KXBTCD trade within 5 minutes on the same day's 5 pm ET ladder, at the nearest Kalshi strike at or beyond K. A violation is a Kalshi price above the Polymarket touch price by more than both taker fees plus 1 cent. Report the count, size and how long violations last. Settlement sources differ (Binance 1-minute extremes vs CF Benchmarks), so a violation is near-arbitrage, not certain.
- **Mood and crowding**: the event-level premium on reach minus dip, regressed on the 30-day Fear & Greed mean and the 7-day BTC funding mean, each standardized against its previous 365 days (known the day before the event).
- **Trading rule**: buy the side priced at least 4 cents below FAIR after the taker fee 0.07 × p × (1 - p); half the trade's shares, at most $200 per trade, held to resolution; return per dollar with a day-block bootstrap.
- Calibration of market and FAIR by price bucket.

### Known limits, stated in advance
- Strikes in one event share one price path, so the effective sample is the number of event-days, not trades.
- Trade prints are not quotes; the side of the taker is recorded but the spread is not.
- 2 × D is exact only for a driftless continuous price; jumps make touching less likely than 2 × D, so FAIR leans high for distant strikes.
- Variants: FAIR and two sensitivities. Anything added later is labeled exploratory.

**Amendment, 2026-11-06, while downloads were running and before any data was looked at.** For speed, smiles are fitted on a 10-minute grid, each from the Deribit trades of the previous 60 minutes, and a Polymarket trade uses the latest fit at or before it (so its option data is 0 to 70 minutes old). Spot is the Binance BTCUSDT 1-minute close before the trade, because the touch markets resolve on Binance; the smile is read at log(K / Deribit index at fit time). When the window ends before the first fitted expiry, total variance is scaled down in proportion to time (constant volatility from now to that expiry).

## Attempts log

- **Run 1** (2026-11-06) crashed while loading: 20 weekly markets had no end date of their own. Fix: fall back to the event's end date. No results were computed.
- **Run 2** crashed at the Kalshi check (a time-zone comparison) after the build. No results were written or read.
- **Run 3** completed, and its results were read. A data check that was planned anyway (does the Binance-derived outcome match Polymarket's resolution, and were all rule wordings recognized?) then found three data bugs: 269 markets with two window wordings the parser did not know (a 5:00 AM ET weekly start, and monthly windows "from the creation of this market"); a strike parser that read the "M" of a following month name as millions (66 weekly markets); and window ends taken from the scheduled end time, which is an hour off around clock changes. In five 2024 monthly markets, "reach" strikes below the starting price resolve on the low, so their side is set by the strike's position against spot at the window start. After the fixes, 3 markets remain unparsed and the Binance outcome matches Polymarket's on 5,359 of 5,360 markets (the exception is a June 2026 monthly market, reach $72,500, that Binance shows touched at $73,841 but that resolved No). The model, tests and filters did not change. Run 3's headline numbers, for disclosure: reach premium +2.25 cents, dip +1.78 cents against FAIR, both Holm p = 0.002.
- **Run 4**: the reported run.
- **Kalshi bound on full data** (run 4 trades reused once Kalshi finished): 262 violations among 129,997 paired trades, on 53 of 228 days, median 6 cents after both fees.
- **Exploratory check, added after seeing the violations: are they executable?** Kept only pairs at most 60 seconds apart, with Binance moving less than 0.1% between them, and on the sides one would trade against (a Kalshi print where the taker sold the leg we need to sell, and a Polymarket print where the taker bought the touch). 143 violations pass the first two filters and none pass all three. Most violations pair a Polymarket print where someone sold the touch (the bid) with a Kalshi print where someone bought (the ask): they are the two venues' spreads, not a free trade. Over the whole sample, before the time and price filters, only 3 violations were on executable sides.
