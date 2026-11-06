/* Ladder pricing deck. Loaded after deck-data.js and ladder.js. Every result comes from DeckData.
   Colors: red = the market price, grey = the coin's own volatility, blue = the factor model from BTC options. */
(() => {
const { Controls, Chips, Stats, chart, q } = Viewer.kit;
const L = Ladder;
const D = DeckData;
const P = D.primary;
const COINS = ['KXDOGED', 'KXXRPD', 'KXSOLD'];
const SHORT = { KXSOLD: 'SOL', KXXRPD: 'XRP', KXDOGED: 'DOGE', KXETHD: 'ETH', 'POLY-SOL': 'SOL Poly', 'POLY-XRP': 'XRP Poly' };

const f3 = (v) => v.toFixed(3);
const f4 = (v) => v.toFixed(4);
const pc = (v, d = 1) => `${(v * 100).toFixed(d)}%`;
const signed = (v, d = 1) => `${v < 0 ? '-' : '+'}${Math.abs(v).toFixed(d)}`;
const pval = (p) => (p < 0.001 ? '< 0.001' : p.toFixed(3));
const usd = (v) => `$${Math.round(v).toLocaleString('en-US')}`;
const listHtml = (items) => `<div class="lists">${items.map(([a, b]) => `<div><b>${a}</b>${b}</div>`).join('')}</div>`;

/* A row of chips where exactly one is on. */
const pick = (host, label, opts, onPick, start = 0) => {
  host.innerHTML = `<span class="chips-label">${label}</span>${opts.map(([n], i) => `<button class="chip ${i === start ? 'on' : ''}" type="button" data-i="${i}">${n}</button>`).join('')}`;
  host.addEventListener('click', (e) => {
    const b = e.target.closest('.chip');
    if (!b) return;
    [...host.querySelectorAll('.chip')].forEach((x) => x.classList.toggle('on', x === b));
    onPick(opts[+b.dataset.i][1]);
  });
};

const ex = D.example;
const exIn = ex.inputs;
const marketEdge = (v) => v.brier.MKT - v.brier.OWN;

const slides = [
  {
    id: 'start', title: 'Can a simple model beat the crowd on altcoin bets?',
    html: `<div class="hero"><div class="kicker">Kalshi and Polymarket price ladders, tested on public data</div><h1><span class="c-repo">Altcoin bets</span><span class="c-fut">have no options</span><span class="c-cash">to price them from.</span></h1><p>Kalshi sells daily bets on where SOL, XRP and DOGE will close. Nothing anchors their prices. This deck tests whether a model built from BTC's options market prices them better than the people trading them.</p><div><button class="chip big on" data-next type="button">Start</button></div><div class="keys"><span><kbd>←</kbd><kbd>→</kbd>Move</span><span><kbd>O</kbd>All slides</span><span><kbd>T</kbd>Theme</span><span><kbd>F</kbd>Fullscreen</span></div></div>`,
  },
  {
    id: 'ladder', kicker: 'The product', title: 'A ladder is a row of yes-or-no bets on one price',
    body: `<p>Every day Kalshi lists contracts like <b>"Will XRP be above $2.80 at 5 pm ET?"</b> at many prices K. Each pays $1 if yes and $0 if no. So a contract's price is the crowd's chance, in cents.</p>
      <p>Line up the contracts by strike and you get a curve: near 100 cents for strikes far below today's price, near 0 for strikes far above. How fast the curve drops depends on how much the coin is expected to move before 5 pm.</p>
      <p>The dots are real trades in one XRP ladder on ${ex.date}, about ${ex.hours} hours before the close. The line is a model curve. Move the slider to change the expected move.</p>`,
    lab: `<div class="controls"></div><div class="stats"></div><div class="chart"></div><div class="note">Left to right: strike compared with the price at the time of the trade.</div>`,
    init(root) {
      const stats = Stats(q(root, '.stats'));
      const r = () => {
        const sd = ctl.vals.s / 100;
        const xs = Array.from({ length: 61 }, (_, i) => -0.12 + i * 0.004);
        chart(q(root, '.chart'), {
          alt: 'Price of each contract against its strike', h: 250, x: [-12, 12], y: [0, 100], xl: 'Strike vs current price, %', xf: (v) => v.toFixed(0), yl: 'Price, cents', yf: (v) => v.toFixed(0),
          series: [{ p: xs.map((x) => [x * 100, L.pOwn(x, sd * Math.sqrt(ex.hours / 24)) * 100]), c: 'cash', w: 2.5 }],
          pts: ex.pts.map((p) => ({ x: p[0] * 100, y: p[1] * 100, r: 3, c: 'bad' })),
        });
        stats([['Expected daily move', sd * 100, (v) => `${v.toFixed(1)}%`, 'cash'], ['Hours left', String(ex.hours)], ['Trades shown', String(ex.pts.length)]]);
      };
      const ctl = Controls(q(root, '.controls'), [{ k: 's', id: 'l-s', label: 'Expected daily move of XRP (standard deviation)', min: 1, max: 10, step: 0.1, val: exIn.own_sd * 100, fmt: (v) => `${v.toFixed(1)}%`, tone: 'cash' }], r);
      return r;
    },
  },
  {
    id: 'problem', kicker: 'The problem', title: 'Altcoin ladders are thin, and nothing anchors them',
    body: `<p>For BTC and ETH, a big options market tells you how much traders expect the price to move. Ladder prices can be checked against it. SOL, XRP and DOGE have no real options market, so their ladders are priced by the crowd alone.</p>
      <p>They are also thin. The bars show the median dollars traded per daily ladder in the trades this study uses. ETH trades about ${Math.round(D.liquidity.KXETHD / D.liquidity.KXDOGED)} times more than DOGE.</p>
      <p>Thin markets with no anchor are where you would expect bad prices. That is the bet this project tests.</p>`,
    lab: `<div class="chart"></div><div class="stats"></div>`,
    init(root) {
      const stats = Stats(q(root, '.stats'));
      return () => {
        const ks = ['KXETHD', 'KXSOLD', 'POLY-SOL', 'KXXRPD', 'POLY-XRP', 'KXDOGED'];
        chart(q(root, '.chart'), {
          alt: 'Dollars traded per ladder', h: 250, x: [-0.6, ks.length - 0.4], y: [0, 27000], xl: '', xf: () => '', yl: 'Median $ per ladder', yf: (v) => `${(v / 1000).toFixed(0)}k`,
          bars: ks.map((k, i) => ({ x: i, y: D.liquidity[k], w: 34, c: k === 'KXETHD' ? 'repo' : k.startsWith('POLY') ? 'muted' : 'fut' })),
          labels: ks.flatMap((k, i) => [{ x: i, y: 0, dy: 16, a: 'middle', t: SHORT[k], c: 'muted' }, { x: i, y: D.liquidity[k], dy: -8, a: 'middle', t: usd(D.liquidity[k]) }]),
        });
        stats([['ETH (has options)', usd(D.liquidity.KXETHD), null, 'repo'], ['SOL', usd(D.liquidity.KXSOLD), null, 'fut'], ['DOGE', usd(D.liquidity.KXDOGED), null, 'fut']]);
      };
    },
  },
  {
    id: 'model', kicker: 'The idea', title: 'Borrow BTC\'s options market and map it to the altcoin',
    body: `<p>The model builds a fair price in three steps, each from a known idea in crypto risk:</p>
      <p><b>1. BTC's expected move</b> comes from its options market (Deribit's DVOL index), corrected by how its past forecasts did.</p>
      <p><b>2. The altcoin follows BTC</b> by its beta, the average move per 1% BTC move. Altcoins follow more tightly when BTC falls, so falls get a steeper beta.</p>
      <p><b>3. The altcoin's own risk</b> is added on top, scaled up or down by market mood (Fear & Greed) and futures crowding, the way factor models do.</p>
      <p>The sliders start at the real inputs for the XRP ladder on the previous slide. Try a steeper down-beta or a jumpier mood and watch the curve move.</p>`,
    lab: `<div class="controls"></div><div class="stats"></div><div class="chart"></div>`,
    init(root) {
      const stats = Stats(q(root, '.stats'));
      const r = () => {
        const v = ctl.vals;
        const hs = Math.sqrt(ex.hours / 24);
        const xs = Array.from({ length: 41 }, (_, i) => -0.12 + i * 0.006);
        const model = (x) => L.pMapped(x, (v.b / 100) * hs, v.d, v.u, (v.r / 100) * v.c * hs, 101) * 100;
        chart(q(root, '.chart'), {
          alt: 'Model price curve against real trades', h: 230, x: [-12, 12], y: [0, 100], xl: 'Strike vs current price, %', xf: (t) => t.toFixed(0), yl: 'Price, cents', yf: (t) => t.toFixed(0),
          series: [{ p: xs.map((x) => [x * 100, model(x)]), c: 'cash', w: 2.5 }],
          pts: ex.pts.map((p) => ({ x: p[0] * 100, y: p[1] * 100, r: 2.6, c: 'bad' })),
        });
        stats([['5% below today', model(-0.05), (t) => `${t.toFixed(0)}¢`, 'cash'], ['At today\'s price', model(0), (t) => `${t.toFixed(0)}¢`, 'cash'], ['5% above', model(0.05), (t) => `${t.toFixed(0)}¢`, 'cash']]);
      };
      const ctl = Controls(q(root, '.controls'), [
        { k: 'b', id: 'm-b', label: 'BTC daily move from options', min: 0.8, max: 5, step: 0.05, val: exIn.btc_sd * 100, fmt: (t) => `${t.toFixed(2)}%`, tone: 'repo' },
        { k: 'd', id: 'm-d', label: 'Beta when BTC falls', min: 0.5, max: 2.5, step: 0.05, val: exIn.beta_down, fmt: f3, tone: 'fut' },
        { k: 'u', id: 'm-u', label: 'Beta when BTC rises', min: 0.5, max: 2.5, step: 0.05, val: exIn.beta_up, fmt: f3, tone: 'fut' },
        { k: 'r', id: 'm-r', label: 'Altcoin\'s own daily risk', min: 0.5, max: 6, step: 0.05, val: exIn.res_sd * 100, fmt: (t) => `${t.toFixed(2)}%` },
        { k: 'c', id: 'm-c', label: 'Mood and crowding multiplier', min: 0.5, max: 1.6, step: 0.05, val: exIn.c, fmt: (t) => `${t.toFixed(2)}×`, tone: 'cash' },
      ], r);
      return r;
    },
  },
  {
    id: 'test', kicker: 'How it was tested', title: 'Every trade, every model, one score',
    body: `<p>The test used <b>${P.prints.toLocaleString('en-US')} trades</b> in ${P.events.toLocaleString('en-US')} Kalshi ladders for SOL, XRP and DOGE, from August 2025 to October 2026. Each trade happened 1 to 24 hours before the 5 pm close.</p>
      <p>For each trade, every model gives its own chance using only data from before the trade, and the trade price is the market's chance. After 5 pm we know what happened.</p>
      <p>The score is the <b>Brier score</b>: (chance - outcome) squared, where the outcome is 1 or 0. Lower is better. Saying 90% when it happens scores 0.01. Saying 90% when it does not scores 0.81.</p>
      <p>The plan, the five models and the tests were written down before any score was computed.</p>`,
    lab: listHtml([
      ['Market', 'The trade price itself.'],
      ['Own volatility', 'The coin\'s own recent moves (last 1, 7 and 30 days). The simplest honest model.'],
      ['Beta', 'BTC\'s options, times the coin\'s beta, plus the coin\'s own risk.'],
      ['Crash beta', 'The same, with a steeper beta for BTC falls.'],
      ['Factor model', 'Crash beta, with the coin\'s own risk scaled by mood and crowding.'],
    ]),
  },
  {
    id: 'scoreboard', kicker: 'Result 1', title: 'The models beat the market',
    body: `<p>Bars show how much better each model scored than the market, averaged over the ${P.events.toLocaleString('en-US')} ladders. Higher bars mean more accurate than the market.</p>
      <p>The market scored <b>${f4(P.brier.MKT)}</b>. The factor model scored <b>${f4(P.brier.FACTOR)}</b>, better by ${f4(-P.tests.MKT.est)} (95% range ${f4(-P.tests.MKT.hi)} to ${f4(-P.tests.MKT.lo)}, adjusted p-value ${pval(P.tests.MKT.p_holm)}).</p>
      <p>That held in every check fixed in advance: with equal weight per trade, with at least 3 hours to the close, with prices from 10 to 90 cents, and without the first 90 days.</p>`,
    deep: `<p>Each trade is weighted by contracts traded within its ladder, because the first minutes after a ladder lists contain bursts of 1-contract trades at nonsense prices. With equal weight per trade the gap is ${f4(-D.sens['equal weight per print'].tests.MKT.est)}, adjusted p ${pval(D.sens['equal weight per print'].tests.MKT.p_holm)}. The ranges come from resampling blocks of 10 days.</p>`,
    lab: `<div class="chart"></div><div class="stats"></div>`,
    init(root) {
      const stats = Stats(q(root, '.stats'));
      return () => {
        const ms = [['OWN', 'Own vol', 'muted'], ['BETA', 'Beta', 'cash'], ['CRASH', 'Crash beta', 'cash'], ['FACTOR', 'Factor', 'cash']];
        const gain = (k) => (P.brier.MKT - P.brier[k]) * 1000;
        chart(q(root, '.chart'), {
          alt: 'How much each model beat the market', h: 240, x: [-0.6, ms.length - 0.4], y: [0, 10], xl: '', xf: () => '', yl: 'Better than the market, Brier ×1000', yf: (v) => v.toFixed(0),
          bars: ms.map(([k, , c], i) => ({ x: i, y: gain(k), w: 40, c })),
          labels: ms.flatMap(([k, n], i) => [{ x: i, y: 0, dy: 16, a: 'middle', t: n, c: 'muted' }, { x: i, y: gain(k), dy: -8, a: 'middle', t: gain(k).toFixed(1) }]),
        });
        stats([['Market', P.brier.MKT, f4, 'bad'], ['Factor model', P.brier.FACTOR, f4, 'cash'], ['Adjusted p', pval(P.tests.MKT.p_holm), null, 'good']]);
      };
    },
  },
  {
    id: 'liquidity', kicker: 'Result 2', title: 'The thinner the ladder, the worse the market prices it',
    body: `<p>Split by coin and venue, the gap between the market and the models follows how much money trades. Each dot is one ladder type. Up means the market lost to the coin's own-volatility model by more.</p>
      <p>On DOGE, about ${usd(D.liquidity.KXDOGED)} per ladder, the market lost by the most. On SOL, about ${usd(D.liquidity.KXSOLD)}, it was roughly a tie. On ETH, about ${usd(D.liquidity.KXETHD)}, <b>the market beat every model</b>.</p>
      <p>This pattern was noticed after the results, with six points, so treat it as a strong hint rather than a proven law.</p>`,
    lab: `<div class="chart"></div><div class="table-wrap"><table></table></div>`,
    init(root) {
      return () => {
        const rows = [...COINS.map((k) => [k, D.perCoin[k]]), ['KXETHD', D.eth], ['POLY-SOL', D.poly['POLY-SOL']], ['POLY-XRP', D.poly['POLY-XRP']]];
        const lx = (v) => Math.log10(v);
        chart(q(root, '.chart'), {
          alt: 'Market mispricing against dollars traded', h: 220, x: [2.2, 4.6], y: [-3, 15], xl: 'Median $ per ladder (log scale)', xf: (v) => usd(10 ** v), yl: 'Market minus model, ×1000', yf: (v) => v.toFixed(0), zero: 1,
          pts: rows.map(([k, v]) => ({ x: lx(D.liquidity[k]), y: marketEdge(v) * 1000, r: 6, c: k.startsWith('POLY') ? 'repo' : k === 'KXETHD' ? 'good' : 'fut' })),
          labels: rows.map(([k, v]) => ({ x: lx(D.liquidity[k]), y: marketEdge(v) * 1000, dx: 9, dy: 4, t: SHORT[k] })),
        });
        q(root, 'table').innerHTML = `<tr><th>Ladder</th><th>$ per ladder</th><th>Market</th><th>Own vol</th><th>Factor</th></tr>${rows.map(([k, v]) => `<tr><td>${SHORT[k]}</td><td>${usd(D.liquidity[k])}</td><td>${f4(v.brier.MKT)}</td><td>${f4(v.brier.OWN)}</td><td>${f4(v.brier.FACTOR)}</td></tr>`).join('')}`;
      };
    },
  },
  {
    id: 'eth', kicker: 'Result 3', title: 'Where options exist, BTC\'s options work just as well',
    body: `<p>ETH has its own options market, so it is a fair check. Each dot is one ETH trade. Left to right: the chance from ETH's own options. Up and down: the chance from BTC's options through the factor model.</p>
      <p>They agree almost perfectly (correlation <b>${D.eth.corr.toFixed(3)}</b>) and score the same: ${f4(D.eth.brier.FACTOR)} against ${f4(D.eth.brier.ETHOPT)}. So for a coin without options, mapping from BTC is a reasonable stand-in.</p>
      <p>On ETH, though, the market itself scored best (${f4(D.eth.brier.MKT)}). With enough money trading, the crowd prices well.</p>`,
    lab: `<div class="chart"></div>`,
    init(root) {
      return () => chart(q(root, '.chart'), {
        alt: 'ETH probabilities from BTC options against ETH options', h: 270, x: [0, 100], y: [0, 100], xl: 'From ETH\'s own options, %', xf: (v) => v.toFixed(0), yl: 'From BTC\'s options, %', yf: (v) => v.toFixed(0),
        series: [{ p: [[0, 0], [100, 100]], c: 'ink', w: 1.2, d: '5 4' }],
        pts: D.ethPts.map(([a, b]) => ({ x: a * 100, y: b * 100, r: 2, c: 'cash' })),
      });
    },
  },
  {
    id: 'layers', kicker: 'Result 4, the honest part', title: 'The fancy layers added nothing',
    body: `<p>The factor model beat the market, but so did the simplest model: the coin's own recent volatility. It scored <b>${f4(P.brier.OWN)}</b>, slightly better than the factor model's ${f4(P.brier.FACTOR)} (adjusted p ${pval(P.tests.OWN.p_holm)}).</p>
      <p>The steeper crash beta and the mood and crowding scaling did not beat plain beta either (adjusted p ${pval(P.tests.BETA.p_holm)}).</p>
      <p>Why: over 1 to 24 hours, the coin's own recent moves already say how jumpy it is. BTC's options add a view of the next month, which matters little for tomorrow afternoon. The market's mistake is simple, and a simple model is enough to catch it.</p>`,
    lab: `<div class="table-wrap"><table></table></div>`,
    init(root) {
      return () => {
        const rows = [['Market', 'MKT'], ['Own volatility', 'OWN'], ['Beta', 'BETA'], ['Crash beta', 'CRASH'], ['Factor model', 'FACTOR']];
        q(root, 'table').innerHTML = `<tr><th>Forecast</th><th>All three</th>${COINS.map((k) => `<th>${SHORT[k]}</th>`).join('')}</tr>${rows.map(([n, k]) => {
          const best = (v) => Math.min(...rows.map(([, kk]) => v.brier[kk]));
          return `<tr><td>${n}</td><td style="${P.brier[k] === best(P) ? 'color:var(--good);font-weight:600' : ''}">${f4(P.brier[k])}</td>${COINS.map((c) => `<td style="${D.perCoin[c].brier[k] === best(D.perCoin[c]) ? 'color:var(--good);font-weight:600' : ''}">${f4(D.perCoin[c].brier[k])}</td>`).join('')}</tr>`;
        }).join('')}`;
      };
    },
  },
  {
    id: 'money', kicker: 'Does it pay?', title: 'A buy-when-cheap rule made money after fees, mostly on XRP',
    body: `<p>The rule: at each trade, buy the side the model prices at least 4 cents above the price plus Kalshi's fee. Take half of what traded, at most $200 a trade, and hold to 5 pm.</p>
      <p>Over all three coins it returned <b>${pc(D.trading.FACTOR.return)}</b> per dollar (95% range ${pc(D.trading.FACTOR.lo)} to ${pc(D.trading.FACTOR.hi)}). XRP made ${pc(D.tradingCoin.KXXRPD.return)}, DOGE ${pc(D.tradingCoin.KXDOGED.return)} and SOL ${pc(D.tradingCoin.KXSOLD.return)}.</p>
      <p><b>The catch:</b> this assumes we could trade at prices someone else already got. Real results would be lower. It shows the gap is big enough to survive fees, not that this is a ready strategy.</p>`,
    lab: `<div class="chips"></div><div class="stats"></div><div class="chart"></div>`,
    init(root) {
      const stats = Stats(q(root, '.stats'));
      let k = 'KXXRPD';
      const r = () => {
        const s = D.pnl[k].map(([d, v]) => [L.dayNumber(d), v]);
        const t = D.tradingCoin[k];
        chart(q(root, '.chart'), {
          alt: 'Cumulative profit of the rule', h: 230, x: [s[0][0], s[s.length - 1][0]], y: [Math.min(0, ...s.map((p) => p[1])) - 1, Math.max(...s.map((p) => p[1])) * 1.1 + 1], xl: '', xf: L.dayLabel, yl: 'Profit, $ thousands', yf: (v) => v.toFixed(0), zero: 1,
          series: [{ p: s, c: 'cash', w: 2.5 }],
        });
        stats([['Return per $', t.return * 100, (v) => `${signed(v)}%`, t.return > 0 ? 'good' : 'bad'], ['95% range', `${pc(t.lo)} to ${pc(t.hi)}`], ['Days traded', String(t.days)]]);
      };
      pick(q(root, '.chips'), 'Coin:', [['XRP', 'KXXRPD'], ['DOGE', 'KXDOGED'], ['SOL', 'KXSOLD']], (v) => { k = v; r(); });
      return r;
    },
  },
  {
    id: 'poly', kicker: 'A second venue', title: 'Polymarket shows the same direction, with less data',
    body: `<p>Polymarket lists daily SOL and XRP ladders that settle at noon ET. There are only ${D.poly.pooled.events} of them, from May to October 2026.</p>
      <p>The models again scored better than the market (${f4(D.poly.pooled.brier.FACTOR)} against ${f4(D.poly.pooled.brier.MKT)}), with the bigger gap on the thinner XRP ladders. With five months of data the gap is not statistically clear (adjusted p ${pval(D.poly.pooled.tests.MKT.p_holm)}), and the trading rule broke even (${pc(D.tradingPoly.FACTOR.return)}).</p>`,
    lab: `<div class="table-wrap"><table></table></div>`,
    init(root) {
      return () => {
        q(root, 'table').innerHTML = `<tr><th>Polymarket</th><th>Ladders</th><th>Market</th><th>Own vol</th><th>Factor</th></tr>${['POLY-SOL', 'POLY-XRP'].map((k) => `<tr><td>${SHORT[k]}</td><td>${D.poly[k].events}</td><td>${f4(D.poly[k].brier.MKT)}</td><td>${f4(D.poly[k].brier.OWN)}</td><td>${f4(D.poly[k].brier.FACTOR)}</td></tr>`).join('')}`;
      };
    },
  },
  {
    id: 'together', kicker: 'Summary', title: 'What this says',
    body: `<p><b>1. Thin altcoin ladders are mispriced.</b> On Kalshi's XRP and DOGE ladders, a simple model beat the market clearly, and the gap was large enough to pay after fees on paper.</p>
      <p><b>2. Money fixes prices.</b> The more traded, the better the crowd did. On ETH the market beat every model.</p>
      <p><b>3. BTC's options can stand in for a missing options market.</b> On ETH the BTC-based price matched ETH's own options almost exactly.</p>
      <p><b>4. Factor-model extras did not help</b> at this horizon. The coin's own recent volatility was enough.</p>`,
    lab: listHtml([
      ['Most solid', 'Models beat the market on Kalshi XRP and DOGE ladders, across every check.'],
      ['Solid but limited', 'The ETH check: BTC options match ETH options. One coin, one year.'],
      ['Hints only', 'The liquidity pattern (seen after the fact) and the trading profits (optimistic fills).'],
    ]),
  },
  {
    id: 'limits', kicker: 'Limits', title: 'What this cannot tell you', solo: true,
    lab: listHtml([
      ['About one year', 'Each coin has about a year of ladders, and the coins move together.'],
      ['Trades are not quotes', 'A trade shows where someone else traded, not a price we could have had.'],
      ['All three coins fell', 'Every model that assumes no drift was hurt by the falling market, the market too.'],
      ['Settlement prices differ', 'Kalshi settles on CF Benchmarks indices; the models use Binance prices.'],
      ['Three runs, one reported', 'Two earlier runs were incomplete because of download bugs (DOGE). Nothing in the plan changed.'],
    ]),
  },
  {
    id: 'quiz', kicker: 'Check yourself', title: 'Four quick questions', solo: true,
    lab: `<div class="quiz-q"></div><div class="opts"></div><div class="note" hidden></div><div class="quiz-foot"><span class="tag"></span><button class="chip big on" type="button" hidden>Next question</button></div>`,
    init(root) {
      const qs = [
        { q: 'A contract "XRP above $2.80 at 5 pm" trades at 30 cents. What does the crowd think?', o: ['XRP will be at $2.80', 'About a 30% chance XRP closes above $2.80', 'XRP will rise 30%'], a: 1, w: 'A $1-if-yes contract priced at 30 cents is the crowd saying about 30%.' },
        { q: 'Which ladder did the market price best?', o: ['DOGE, the thinnest', 'ETH, the most traded', 'They were all the same'], a: 1, w: 'On ETH, with about $20,000 a ladder, the market beat every model. On DOGE, with about $300, it lost to all of them.' },
        { q: 'Why does the ETH check matter?', o: ['ETH is the biggest altcoin', 'ETH has its own options, so we can see whether BTC options give the same answer', 'ETH fell the most'], a: 1, w: 'Where real options exist, the BTC-based price matched them. That supports using BTC for coins without options.' },
        { q: 'Did the crash beta and mood scaling improve the model?', o: ['Yes, a lot', 'No, the coin\'s own recent volatility did as well', 'They made it worse than the market'], a: 1, w: 'At a 1-to-24-hour horizon the simple own-volatility model was as good or slightly better.' },
      ];
      let i = 0;
      let score = 0;
      const next = q(root, '.quiz-foot button');
      const show = () => {
        const x = qs[i];
        q(root, '.quiz-q').textContent = x.q;
        q(root, '.opts').innerHTML = x.o.map((t, j) => `<button class="opt" type="button" data-a="${j}">${t}</button>`).join('');
        q(root, '.note').hidden = true;
        next.hidden = true;
        q(root, '.tag').textContent = `Question ${i + 1} of ${qs.length}  ·  Score ${score}`;
      };
      q(root, '.opts').addEventListener('click', (e) => {
        const b = e.target.closest('.opt');
        if (!b || b.disabled) return;
        const x = qs[i];
        const ok = +b.dataset.a === x.a;
        if (ok) score += 1;
        [...q(root, '.opts').children].forEach((o, j) => { o.disabled = true; if (j === x.a) o.classList.add('right'); });
        if (!ok) b.classList.add('wrong');
        const n = q(root, '.note');
        n.hidden = false;
        n.className = `note ${ok ? 'ok' : 'alert'}`;
        n.textContent = `${ok ? 'Correct.' : 'Not quite.'} ${x.w}`;
        q(root, '.tag').textContent = `Question ${i + 1} of ${qs.length}  ·  Score ${score}`;
        next.hidden = false;
        next.textContent = i < qs.length - 1 ? 'Next question' : 'Restart quiz';
      });
      next.addEventListener('click', () => {
        if (i < qs.length - 1) i += 1;
        else { i = 0; score = 0; }
        show();
      });
      show();
    },
  },
  {
    id: 'decoder', kicker: 'Reference', title: 'Decoder', solo: true,
    lab: `<input class="search" type="search" id="term-search" placeholder="Search terms, such as beta or Brier" aria-label="Search terms"><div class="terms"></div>`,
    init(root) {
      const terms = [
        ['Ladder', 'A row of yes-or-no contracts on one price at many levels, such as "XRP above K at 5 pm" for many K.'],
        ['Kalshi', 'A US-regulated exchange for event contracts that pay $1 if something happens.'],
        ['Polymarket', 'A prediction market where the same kind of contracts trade.'],
        ['Strike', 'The price level K in a contract.'],
        ['Print', 'One trade on the exchange: a time, a price and a number of contracts.'],
        ['Options market', 'A market for contracts that pay off on big moves. Its prices show how much traders expect a price to move.'],
        ['DVOL', 'Deribit\'s index of the move that BTC (or ETH) options expect over the next 30 days.'],
        ['Beta', 'How much a coin moves for each 1% BTC move.'],
        ['Crash beta', 'A beta measured on BTC down moves. Altcoins usually follow BTC more tightly on the way down.'],
        ['Factor model', 'A model that describes a coin by a few traits, such as its beta and its own risk, and adjusts them by conditions like mood.'],
        ['Fear & Greed index', 'A daily 0-to-100 score of crypto market mood.'],
        ['Funding crowding', 'When buyers of perpetual futures pay a lot to hold them, many traders are betting the same way.'],
        ['Volatility (HAR)', 'How much a price moves, measured from the last 1, 7 and 30 days of moves.'],
        ['Brier score', 'Average of (chance - outcome) squared. Lower is better.'],
        ['p-value', 'Roughly, how likely a gap this big would be by chance. Small means unlikely to be chance.'],
        ['Holm adjustment', 'A correction to p-values when several comparisons are tested at once.'],
        ['Taker fee', 'Kalshi\'s fee for trading against a resting order: 0.07 × p × (1 - p) per contract.'],
      ];
      const box = q(root, '.terms');
      const paint = (f) => {
        const s = f.trim().toLowerCase();
        const hits = terms.filter(([a, b]) => `${a} ${b}`.toLowerCase().includes(s));
        box.innerHTML = hits.length ? hits.map(([a, b]) => `<div class="term"><b>${a}</b>${b}</div>`).join('') : '<div class="empty">No matching terms. Try "beta" or "ladder".</div>';
      };
      q(root, '.search').addEventListener('input', (e) => paint(e.target.value));
      paint('');
    },
  },
  {
    id: 'talk', kicker: 'Talk to a quant', title: 'Questions worth asking', solo: true,
    lab: `<div class="chips" id="talk-tabs"></div><div class="lists"></div>`,
    init(root) {
      const tabs = q(root, '#talk-tabs');
      const sets = [
        ['Questions to ask', [
          ['Benchmarks', 'For a 1-to-24-hour digital, what volatility do you use: daily, intraday, or the order book?'],
          ['Liquidity', 'Is there a volume level above which the crowd reliably beats simple models?'],
          ['Missing options', 'Would you trust a BTC-options mapping for longer-dated altcoin contracts, where the coin\'s own history says less?'],
        ]],
        ['Mistakes to avoid', [
          ['"A model that beats the market is a strategy."', 'Scores are not fills. Thin markets give little size, and trade prices are not quotes.'],
          ['"More layers make a better model."', 'Here, the simplest model was as good as the full factor model.'],
          ['"Crowd prices are always efficient."', 'Only when enough money trades. On thin ladders they were not.'],
        ]],
      ];
      const show = (i) => {
        [...tabs.children].forEach((c, j) => c.classList.toggle('on', i === j));
        q(root, '.lists').innerHTML = sets[i][1].map(([a, b]) => `<div><b>${a}</b>${b}</div>`).join('');
      };
      tabs.innerHTML = sets.map((s) => `<button class="chip big" type="button">${s[0]}</button>`).join('');
      [...tabs.children].forEach((b, i) => b.addEventListener('click', () => show(i)));
      show(0);
    },
  },
];

Viewer.present(slides);
})();
