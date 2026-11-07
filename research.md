# Pricing altcoin prediction-market ladders from BTC options

## The question

Kalshi and Polymarket list daily "price above K" ladders for altcoins such as SOL, XRP and DOGE. Unlike BTC and ETH, these coins have no liquid options market, so nothing anchors the ladder prices, and they trade 100 to 1,000 times less than the BTC ladder. Can a crypto factor model price them better than the market does? The model takes BTC's forward-looking volatility from the options market (Deribit DVOL), maps it to each altcoin through a beta that is steeper when BTC falls, and adjusts the altcoin's own risk by the style signals common in crypto factor models (funding crowding and the Fear & Greed regime).

## Prior work (verified 2026-11-06)

- Lee, Lee and Lee, "Cryptocurrency Prediction Markets through the Derivatives Lens: Evidence from Kalshi and Polymarket," SSRN 6748186, 2026. Reads BTC and ETH prediction-market contracts as digital options and extracts implied volatility surfaces; reports a larger variance risk premium on Polymarket than Kalshi.
- Mohanty and Krishnamachari, "Do Prediction Markets Forecast Cryptocurrency Volatility? Evidence from Kalshi Macro Contracts," arXiv 2604.01431, 2026. Kalshi macro contracts help forecast BTC and altcoin realized volatility.
- Corsi, "A Simple Approximate Long-Memory Model of Realized Volatility," Journal of Financial Econometrics 7(2), 2009, 174-196. The HAR model: daily, weekly and monthly realized volatility components.
- Ang, Chen and Xing, "Downside Risk," Review of Financial Studies 19(4), 2006, 1191-1239. Beta measured on market down days.
- Liu, Tsyvinski and Wu, "Common Risk Factors in Cryptocurrency," Journal of Finance 77(2), 2022, 1133-1177.
- Deribit DVOL index methodology (Deribit, public): a 30-day implied volatility index for BTC and ETH.

The gap: I found no work that prices altcoin prediction-market contracts, which have no options market, off BTC's options market through a cross-asset model.

## What I looked at before this plan

Data availability and liquidity only, no prices against outcomes:
- Kalshi KXSOLD, KXXRPD and KXDOGED (and KXETHD) list hourly events. All but one each day open one hour before they close. The 5 pm ET event lists about 25 hours ahead, like KXBTCD. In one sampled SOL 5 pm event, 36% of contracts traded more than an hour before the close. Settlement is the 60-second average of the CF Benchmarks real-time index before 5 pm ET.
- KXSOLD events start in December 2025 and KXXRPD in October 2025.
- Polymarket lists daily "above K at 12:00 ET" ladders for SOL and XRP, settled on the Binance 1-minute close, with about $5k to $27k of daily volume in sampled days from July to October 2026.
- Deribit's public API serves hourly DVOL for BTC and ETH.

## Test plan, fixed 2026-11-06 before any model was compared with any outcome

### Data

- **Kalshi.** Every KXSOLD, KXXRPD, KXDOGED and KXETHD event that closes at 5 pm ET, from the first such event through 2026-10-31: market metadata (strike, result) for every market, and every trade of every market with volume. Public Trade API v2, at most 3 requests per second.
- **Binance spot** 1-minute and 1-hour klines for SOLUSDT, XRPUSDT, DOGEUSDT, ETHUSDT and BTCUSDT from 2025-07-01 (public archive).
- **Deribit DVOL** hourly for BTC and ETH from 2025-07-01 (public API).
- **Binance USDT-M funding rates** for SOL, XRP, DOGE and ETH, and the **Alternative.me Fear & Greed index**.
- **Polymarket (secondary).** Every SOL and XRP daily "above K" event through 2026-10-31, with trades from the public data API.

### Unit of evaluation

A trade print on a qualifying Kalshi market with 1 to 24 hours left to the close and a yes price from 5 to 95 cents. The market's probability is the print's yes price. The outcome is the market's result. Spot is the Binance 1-minute close of the minute before the print. Moneyness is x = log(K / spot). The USDT/USD basis and the 60-second settlement average are ignored.

### Models of P(price at 5 pm ET > K)

All returns are log returns and all distributions are Student-t with 4 degrees of freedom (scale = standard deviation / sqrt(2)). Horizon h is the hours left to the close. Every input uses only data available before the print.

- **MKT.** The print's own price.
- **OWN.** The altcoin's own HAR volatility: daily variance = the mean of three estimates from hourly returns over the last 1, 7 and 30 days (24 times the mean squared hourly return). Scale over h hours = that daily standard deviation times sqrt(h / 24).
- **BETA.** Altcoin return = beta × BTC return + residual. BTC's daily standard deviation is k × DVOL / 100 / sqrt(365), using the last hourly DVOL before the print. k is a trailing calibration: the median absolute standardized BTC 5 pm-to-5 pm return over the previous 90 days, divided by its value for a unit-scale t(4) (0.7407), with at least 60 days (k = 1 before that). Beta is the OLS slope of hourly altcoin returns on hourly BTC returns over the last 30 days. The residual's daily standard deviation is the HAR estimate on hourly residuals. The probability integrates the residual's t(4) CDF over BTC's t(4) distribution.
- **CRASH.** BETA with two betas: one fitted on the hours BTC was below its 30-day hourly mean, applied to BTC falls, and one fitted on the other hours, applied to BTC rises.
- **FACTOR.** CRASH with the residual scale multiplied by c for the print's cell. The cell is the Fear & Greed regime (fear below 35, greed above 65, using the previous UTC day's value) crossed with funding crowding (the altcoin's 7-day mean funding above its own trailing 90-day median). c = median absolute standardized residual over earlier event days in the same cell within 365 days, divided by 0.7407, with at least 30 such days (c = 1 before that). A day's standardized residual is (altcoin 5 pm-to-5 pm return - beta × BTC's) divided by the residual scale at the previous 5 pm.

### Scores

- **Primary.** Brier score per print, averaged within each event, then across events, pooling SOL, XRP and DOGE (one event per coin and day). Three comparisons: FACTOR against MKT, OWN and BETA. Paired event differences, moving-block bootstrap over days (10-day blocks, 2,000 draws), Holm-adjusted over the three.
- **Secondary.** Each coin separately. Log score. Calibration by price bucket. AUC.
- **ETH check.** ETH has its own options. On KXETHD, FACTOR (mapped from BTC) is compared with ETHOPT, a t(4) on ETH's own DVOL with its own trailing k. If FACTOR is close to ETHOPT where ETH's options exist, mapping from BTC is a reasonable substitute where they do not.
- **Trading rule (secondary).** At each qualifying print, buy YES at the print price if model - price - 0.07 × price × (1 - price) is at least 0.04; buy NO by the same test on the NO side. Fill half the print's contracts, at most $200 per print, hold to settlement. Report return per dollar, the number of event days and a day-block bootstrap interval. This assumes the print price was available to us, which is optimistic.
- **Sensitivities.** Horizon of at least 3 hours. Prices from 10 to 90 cents. Dropping the first 90 days.
- **Polymarket replication (secondary).** The same models and scores on SOL and XRP daily ladders, with the horizon to 12:00 ET and the Binance 1-minute close as the outcome.

### Known limits, stated in advance

- Kalshi settles on CF Benchmarks indices; spot here is Binance USDT.
- Trade prints are not quotes: a print shows where someone traded, not where we could have traded.
- About one year of data per coin, with strongly correlated coins.
- Number of variants: the five models above. Anything added later is labeled exploratory.

**Amendment, 2026-11-06, before any score was computed.** An input check on the first 326 SOL events (spot, features and model probabilities only, no outcomes) found bursts of 1-contract prints in the first minutes after a ladder lists, at prices far from any sensible value (for example 64 cents for a strike 15% below spot). With equal weight per print these bursts would dominate some events and flatter every model against the market. The primary Brier and log scores therefore weight prints by contracts traded within each event, and events stay equally weighted. Equal weight per print is reported as a sensitivity. Nothing else changes.

**Amendment 2, 2026-11-06, before any score was computed.** Each event has 50 to 300 strikes and about 40 of them trade, so fetching every trade takes about 6 hours at 3 requests per second. Trades are fetched only for strikes within 10% (in log terms) of the Binance spot price when the event lists; other strikes keep their metadata and are flagged. This is the same band idea used for the BTC ladders in the earlier study, and it removes most of the far-from-spot prints described in the first amendment.

**Polymarket details, fixed 2026-11-06 before any Polymarket outcome was looked at.** Polymarket's v1 data API is retired, so trades come from data-api.polymarket.com/v2/trades. Ladders list about a week ahead and close at 12:00 ET, so prints qualify with 1 hour to 7 days left (not 24 hours) and a YES-equivalent price from 5 to 95 cents; a NO trade at price q counts as a YES price of 1 - q. Prints are weighted by shares within each event. The outcome is the market's own resolution. Model inputs are the same as for Kalshi (the BTC and residual scales grow with the square root of the horizon). The trading rule uses Polymarket's crypto taker fee, 0.07 × p × (1 - p) per share, the same formula as Kalshi.

## Follow-up: reversal in fear (fixed 2026-11-06, after the results above, before any reversal signal was computed)

The factor model above uses risk-side ideas from practitioner crypto factor models (beta, residual volatility, funding crowding, mood regimes). Those models also make a return-side claim: short-term reversal (recent losers beat recent winners) pays when the market is fearful and loses when it is greedy. This follow-up asks whether that claim moves the center of a ladder's price distribution enough to price contracts better, and whether it adds anything to the market price. It was planned after the primary results were known, so it is a separate, labeled test.

**Universe and signal.** Every Binance spot USDT pair in the public archive, including pairs delisted since (stablecoins, fiat, wrapped and leveraged tokens excluded), daily klines from 2024-01. A token is eligible on UTC day t if it has at least 170 daily returns in the 180 days before t and a median daily quote volume of at least $1M over the 30 days before t. The reversal signal on day t is -(close of day t-2 / close of day t-22 - 1), skipping the most recent day, cross-sectionally z-scored among eligible tokens and clipped at +-3. Days with fewer than 50 eligible tokens are skipped.

**Regime.** The trailing 30-day mean of the Fear & Greed index through day t-1: fear below 35, greed above 65, neutral otherwise.

**Slope.** Each day, the cross-sectional OLS slope g_t of the day's simple return on the signal z. The forecast slope for day t, b_t, is the mean of g_s over earlier days s < t within 365 days with the same regime label, with at least 30 such days (b_t = 0 otherwise). No sign is imposed; if reversal pays in fear, b is positive in fear.

**Models.**
- **REV.** FACTOR with the log-return distribution shifted by mu = b_t × z_coin,t × h / 24, where t is the print's UTC day and z_coin,t is the coin's own signal that day. The probability is FACTOR's evaluated at x - mu.
- **MKT+REV.** The market price plus the change the shift makes to the model: MKT + (REV - FACTOR), clipped to [0.001, 0.999]. This asks whether the signal adds to the market's own price.

**Primary tests.** On the Kalshi SOL, XRP and DOGE prints of the main study, with the same contract weighting, day-block bootstrap and filters: REV against FACTOR, and MKT+REV against MKT, Holm-adjusted over the two.

**Secondary.** Each coin; ETH; Polymarket; the trading rule with REV; the size of the shift (median absolute REV - FACTOR, in cents); in the universe over the test period, the mean daily slope in fear and in greed with a day-block bootstrap interval (does the regime pattern hold in these months at all); and the correlation of mu with the coin's realized log return from the print to the close.

**Expectation, stated in advance.** Reversal factors earn tenths of a percent a day between the top and bottom fifths of tokens, while a ladder coin moves several percent a day. The shift is likely to be under a cent at the money, and this test is likely to be underpowered. A null result here means the effect, if any, is too small for this horizon and sample, not that reversal does not exist.

**Result of the follow-up, and a lead.** REV and MKT+REV scored the same as FACTOR and MKT (see README). In an exploratory check not in the plan above, the coins' own signal pointed the expected way on the ladder days (positive slope in fear, negative in greed) with a size about ten times the universe average, but with intervals that include zero.

## Long check: does reversal in fear predict the ladder coins' daily moves? (fixed 2026-11-06, before any data before 2024 was downloaded)

The lead above came from the ladder period (2025-07-31 to 2026-10-31). This check uses only earlier data, 2020-03-01 to 2025-07-30, which the lead never saw.

- **Data.** The same Binance universe, signal, eligibility and regime label as the follow-up, with daily klines from 2019-09.
- **Coins.** SOL, XRP and DOGE, pooled (primary), and each alone (secondary).
- **Outcome.** The coin's log return over UTC day t. The signal is the coin's z on day t, known at the start of the day.
- **Model.** Pooled OLS of the return on z × fear, z × neutral and z × greed, with an intercept per regime.
- **Primary test.** The fear slope is above zero: one-sided p from a moving-block bootstrap over days (10-day blocks, 2,000 draws, coins resampled together by day).
- **Secondary.** Fear minus greed slope (two-sided); each coin; the same regression over every eligible token in the universe with the per-day cross-sectional mean removed (the factor itself, for context).
- **Economic bar, stated in advance.** At the money, a one-day t(4) with a 4% daily standard deviation has a density of about 13 per unit of log return, so a drift of mu changes the fair price by about 13 × mu. To clear Kalshi's 1.75-cent fee at 50 cents, mu must be at least about 0.13% a day; to clear the trading rule's 4-cent edge as well, about 0.43%. The lead is worth a ladder strategy only if the fear slope is significant and at least 0.13% per unit of z.

## Pilot: do crowding and mood signals predict the crowd's mistakes? (fixed 2026-11-06, before any of it was computed)

Exploratory pilot to decide whether a full study is worth it. Results go to the owner first and are not reported as findings.

**Question.** Crypto factor models measure crowding (perpetual funding) and mood (the Fear & Greed index). A prediction-market price is set by a crowd. Does the crowd's pricing error lean the way crowding and mood predict?

**Errors, per ladder (event), contract-weighted over qualifying prints as in the main study** (1 to 24 hours left, 5 to 95 cents):
- **Direction error D** = mean of (price - outcome). For "above K" contracts, D > 0 means YES was overpriced: the crowd was too bullish. This needs no model.
- **Width error W** = mean of s × (price - outcome), with s = +1 for strikes above spot at the print and -1 below. W > 0 means the crowd overpriced moves away from spot: its distribution was too wide (fearful).

**Signals, known before the ladder's day (UTC day before the close):** BTC perpetual funding, 7-day mean; the Fear & Greed index, 30-day mean. Each is standardized against its own previous 365 days (at least 90). Heat = the mean of the two standardized signals.

**Primary (BTC, Kalshi KXBTCD 5 pm ET ladders, December 2024 to September 2026; W from August 2025, when 1-minute spot data starts):**
1. The slope of D on heat is positive (hot, crowded, greedy markets make the crowd too bullish).
2. The slope of W on the standardized Fear & Greed is negative (fear makes the crowd's distribution too wide).

Day-block bootstrap (10-day blocks, 2,000 draws), Holm over the two.

**Secondary.** The same on SOL, XRP and DOGE pooled (coin funding instead of BTC's) and on ETH. Mean D and W in the top and bottom thirds of the signal, in cents, against Kalshi's fee of up to 1.75 cents: the gut check for whether a fade rule could pay.

**Caution, stated in advance.** All strikes of a ladder settle on one price, so each ladder is close to one observation: D is largely the day's BTC move against the crowd's expectation. Funding has been reported to predict crypto returns only weakly. A null is the likely outcome.

**Pilot result (2026-11-06).** Both primary tests were null: on 722 BTC ladders, heat did not predict the direction error (slope +0.24 cents per standard deviation, Holm p = 1.0), and Fear & Greed did not predict the width error (Holm p = 1.0). Among the secondaries, fear widened the overpricing on SOL, XRP and DOGE (-1.13 cents per standard deviation of the index, 95% interval -2.21 to -0.30, p = 0.006 unadjusted, one of four). The width error itself was positive everywhere: the crowd overpriced moves away from spot by 2.6 cents a contract on BTC, 4.9 on ETH and 5.3 on the three altcoins. An exploratory check not in the plan, taking the side against the move at each print after the taker fee, returned +1.3% per dollar on BTC (95% interval -0.3% to +3.1%), +3.4% on ETH (+1.9% to +4.7%) and +1.3% on the three altcoins (-1.1% to +3.8%). Trade prints do not say which side was the taker, so part of the width error may be the bid-ask spread paid by buyers of long shots.
