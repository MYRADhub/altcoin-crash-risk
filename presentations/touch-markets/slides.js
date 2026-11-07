/* Touch-market deck. Loaded after deck-data.js and touch.js. Every result comes from DeckData.
   Colors: red (bad) = the Polymarket price, teal (cash) = the options value (2 x digital), coral (fut) = the barrier formula, grey = finishing beyond. */
(() => {
const { Controls, Chips, Stats, chart, q } = Viewer.kit;
const T = Touch;
const D = DeckData;
const P = D.premium;

const pc = (v, d = 0) => `${(v * 100).toFixed(d)}%`;
const cents = (v, d = 1) => `${v < 0 ? '-' : '+'}${Math.abs(v * 100).toFixed(d)}¢`;
const pval = (p) => (p < 0.001 ? '< 0.001' : p.toFixed(3));
const listHtml = (items) => `<div class="lists">${items.map(([a, b]) => `<div><b>${a}</b>${b}</div>`).join('')}</div>`;
const pick = (host, label, opts, onPick, start = 0) => {
  host.innerHTML = `<span class="chips-label">${label}</span>${opts.map(([n], i) => `<button class="chip ${i === start ? 'on' : ''}" type="button" data-i="${i}">${n}</button>`).join('')}`;
  host.addEventListener('click', (e) => {
    const b = e.target.closest('.chip');
    if (!b) return;
    [...host.querySelectorAll('.chip')].forEach((x) => x.classList.toggle('on', x === b));
    onPick(opts[+b.dataset.i][1]);
  });
};

const slides = [
  {
    id: 'start', title: 'Does the crowd know touching is twice as likely?',
    html: `<div class="hero"><div class="kicker">Polymarket, Deribit and Kalshi, tested on public data</div><h1><span class="c-repo">Will Bitcoin hit $X?</span><span class="c-cash">Options desks price that bet.</span><span class="c-fut">So does a crowd.</span></h1><p>Polymarket sells bets that pay if Bitcoin touches a price at any moment in a day, week or month. About $1.2 billion has traded on them. This deck checks whether the crowd prices them like the options market would.</p><div><button class="chip big on" data-next type="button">Start</button></div><div class="keys"><span><kbd>←</kbd><kbd>→</kbd>Move</span><span><kbd>O</kbd>All slides</span><span><kbd>T</kbd>Theme</span><span><kbd>F</kbd>Fullscreen</span></div></div>`,
  },
  {
    id: 'touch', kicker: 'The idea', title: 'Touching a price is not the same as finishing there',
    body: `<p>"Will the tide <b>reach</b> the pier today?" is a different question from "will the water be <b>above</b> the pier at 5 pm?". The first only needs one moment; the second needs the right moment.</p>
      <p>For a price that wanders randomly, touching a level is about <b>twice as likely</b> as finishing beyond it. The grey line is the chance of finishing beyond each strike, the teal line is twice that, and the dashed red line is the exact formula for a random walk.</p>
      <p>Move the sliders, or pick a market length.</p>`,
    deep: '<p>Both curves assume no drift and no jumps. They are the textbook values an options desk starts from; real desks adjust for the volatility smile, which is what this project does with Deribit data.</p>',
    lab: `<div class="chips" id="t-pre"></div><div class="controls"></div><div class="stats"></div><div class="chart"></div>`,
    init(root) {
      const stats = Stats(q(root, '.stats'));
      const r = () => {
        const { d, v, n } = ctl.vals;
        const vol = v / 100;
        const xs = Array.from({ length: 121 }, (_, i) => -0.15 + i * 0.0025).filter((x) => Math.abs(x) > 1e-9);
        chart(q(root, '.chart'), {
          alt: 'Chance of touching and of finishing beyond each strike', h: 230, x: [-15, 15], y: [0, 100], xl: 'Strike vs today\'s price, %', xf: (t) => t.toFixed(0), yl: 'Chance, %', yf: (t) => t.toFixed(0),
          series: [
            { p: xs.map((x) => [x * 100, T.finishBeyond(x, vol, n) * 100]), c: 'muted', w: 2 },
            { p: xs.map((x) => [x * 100, T.touchReflect(x, vol, n) * 100]), c: 'cash', w: 2.5 },
            { p: xs.map((x) => [x * 100, T.touchGBM(x, vol, n) * 100]), c: 'fut', w: 1.5, d: '5 4' },
          ],
          v: [{ x: d, c: 'ink' }],
        });
        const x = d / 100;
        stats([['Finish beyond', T.finishBeyond(x, vol, n) * 100, (t) => `${t.toFixed(1)}%`, 'muted'],
          ['Touch (2 x)', T.touchReflect(x, vol, n) * 100, (t) => `${t.toFixed(1)}%`, 'cash'],
          ['Touch (formula)', T.touchGBM(x, vol, n) * 100, (t) => `${t.toFixed(1)}%`, 'fut']]);
      };
      const ctl = Controls(q(root, '.controls'), [
        { k: 'd', id: 't-d', label: 'Strike vs today\'s price', min: -12, max: 12, step: 0.5, val: 3, fmt: (t) => `${t > 0 ? '+' : ''}${t.toFixed(1)}%`, tone: 'ink' },
        { k: 'v', id: 't-v', label: 'Expected daily move (volatility)', min: 1, max: 6, step: 0.1, val: 2.5, fmt: (t) => `${t.toFixed(1)}%`, tone: 'cash' },
        { k: 'n', id: 't-n', label: 'Days in the window', min: 0.5, max: 30, step: 0.5, val: 1, fmt: (t) => `${t.toFixed(1)}`, tone: 'fut' },
      ], r);
      Chips(q(root, '#t-pre'), 'Market', [['Daily', { n: 1, d: 3 }], ['Weekly', { n: 7, d: 6 }], ['Monthly', { n: 30, d: 12 }]], ctl);
      return r;
    },
  },
  {
    id: 'why2', kicker: 'Why twice', title: 'Every path that finishes beyond has a mirror that touched and turned back',
    body: `<p>Take any path that touches the line and then ends above it. Flip everything after the touch upside down: you get a path that touched and ended below. The two are equally likely.</p>
      <p>So for each "touched and finished above" there is one "touched and finished below". Touches come out at about twice the finishes.</p>
      <p>The paths here are <b>simulated</b>, not real. Add jumps to break the rule: a jump can leap over the line without a touch-and-return, and the ratio drops below 2.</p>`,
    lab: `<div class="chips" id="w-mode"></div><div class="stats"></div><div class="chart"></div><div class="note">Simulated paths (synthetic). Red: touched the line. Grey: never touched.</div>`,
    init(root) {
      const stats = Stats(q(root, '.stats'));
      let mode = { jumpEvery: 0, jumpSize: 0, vol: 0.03 };
      let seed = 7;
      const r = () => {
        const dist = 0.03;
        const s = T.simulate({ n: 3000, steps: 200, vol: mode.vol, days: 1, dist, seed, jumpEvery: mode.jumpEvery, jumpSize: mode.jumpSize, keep: 40 });
        chart(q(root, '.chart'), {
          alt: 'Simulated price paths and the touch line', h: 230, x: [0, 1], y: [-10, 10], xl: 'Time through the day', xf: (t) => `${Math.round(t * 24)}h`, yl: 'Move, %', yf: (t) => t.toFixed(0),
          series: [...s.paths.map((p) => ({ p: p.p.map(([t, x]) => [t, x * 100]), c: p.hit ? 'bad' : 'muted', w: 1, o: p.hit ? 0.8 : 0.35 })),
            { p: [[0, dist * 100], [1, dist * 100]], c: 'ink', w: 1.5, d: '5 4' }],
        });
        stats([['Touched', s.touched * 100, (t) => `${t.toFixed(1)}%`, 'bad'], ['Finished above', s.finished * 100, (t) => `${t.toFixed(1)}%`, 'muted'],
          ['Ratio', s.touched / Math.max(s.finished, 1e-9), (t) => `${t.toFixed(2)}×`, 'cash']]);
      };
      pick(q(root, '#w-mode'), 'Paths', [['Smooth', { jumpEvery: 0, jumpSize: 0, vol: 0.03 }], ['With jumps', { jumpEvery: 60, jumpSize: 0.035, vol: 0.015 }], ['New draw', null]], (m) => {
        if (m) mode = m;
        else seed += 1;
        r();
      });
      return r;
    },
  },
  {
    id: 'market', kicker: 'The market', title: 'A busy crowd selling barrier options',
    body: `<p>Polymarket lists BTC touch markets every day, every week and every month: "Will Bitcoin reach $120,000 on August 15?", "Will Bitcoin dip to $80,000 in September?". Each event has 10 to 50 strikes.</p>
      <p>They resolve on Binance's one-minute highs and lows. I rebuilt every outcome from Binance data and matched Polymarket's on ${pc(D.agreement, 2)} of markets.</p>`,
    lab: `<div class="stats"></div>${listHtml([['Daily', `${D.byKind.daily} events, from August 2025`], ['Weekly', `${D.byKind.weekly} events, from July 2025`], ['Monthly', `${D.byKind.monthly} events, from October 2024`]])}`,
    init(root) {
      const stats = Stats(q(root, '.stats'));
      return () => stats([['Events', D.events, (t) => Math.round(t).toLocaleString('en-US'), 'ink'], ['Trades tested', D.trades / 1e6, (t) => `${t.toFixed(2)}M`, 'bad'], ['Traded on them', '$1.2B', null, 'cash']]);
    },
  },
  {
    id: 'fair', kicker: 'How it was tested', title: 'Price every trade the way an options desk would',
    body: `<p>Deribit is the main BTC options exchange, and its public history includes every trade with its implied volatility. For each Polymarket trade I took the last hour of Deribit trades, fitted the volatility smile, and read off the chance BTC finishes beyond the strike.</p>
      <p>Twice that is the fair value of the touch bet. The barrier formula is a second opinion; the finish chance itself is a hard floor, because finishing beyond means it touched.</p>
      <p>Trades count only while the window is open, at least an hour remains, and the price has not already touched the strike.</p>`,
    lab: listHtml([['Fair value 1 (planned)', 'Twice the options chance of finishing beyond the strike.'], ['Fair value 2', 'The exact touch formula for a random walk, with the smile\'s volatility at the strike.'], ['Floor', 'The chance of finishing beyond. No touch price should be below it.'], ['Score', 'Price minus fair value, and Brier score against what happened. Fixed in a written plan before downloading any data.']]),
  },
  {
    id: 'calibration', kicker: 'Result 1', title: 'The crowd is as accurate as the options market',
    body: `<p>Group contracts by price and check how often they touched. On a perfectly honest scale the dots sit on the diagonal.</p>
      <p>The crowd's dots (red) sit on it: contracts near 57 cents touched 57% of the time. The options value (teal) runs a little low in the middle. Brier scores: crowd <b>${D.brier.market.toFixed(4)}</b>, options <b>${D.brier.fair.toFixed(4)}</b>, not a significant difference (p ${pval(P.primary.brier.p)}).</p>`,
    lab: `<div class="chips" id="c-pick"></div><div class="chart"></div>`,
    init(root) {
      let show = ['p', 'FAIR'];
      const r = () => {
        chart(q(root, '.chart'), {
          alt: 'Calibration of the crowd and the options value', h: 260, x: [0, 100], y: [0, 100], xl: 'Price or fair value, cents', xf: (t) => t.toFixed(0), yl: 'Touched, %', yf: (t) => t.toFixed(0),
          series: [{ p: [[0, 0], [100, 100]], c: 'muted', w: 1, d: '4 4' },
            ...show.map((k) => ({ p: D.calibration[k].map(([a, b]) => [a * 100, b * 100]), c: k === 'p' ? 'bad' : 'cash', w: 2 }))],
          pts: show.flatMap((k) => D.calibration[k].map(([a, b]) => ({ x: a * 100, y: b * 100, c: k === 'p' ? 'bad' : 'cash', r: 4, ring: true }))),
        });
      };
      pick(q(root, '#c-pick'), 'Show', [['Both', ['p', 'FAIR']], ['Crowd', ['p']], ['Options value', ['FAIR']]], (v) => { show = v; r(); });
      return r;
    },
  },
  {
    id: 'premium', kicker: 'Result 2', title: 'The crowd sits between two textbook answers',
    body: `<p>The planned test: is the crowd's price above or below the options fair value? Against twice the finish chance it is <b>${cents(P.primary.reach.est)}</b> on up markets (adjusted p ${pval(P.primary.reach.p)}). Against the exact formula it is <b>${cents(P['GBM barrier'].reach.est)}</b>.</p>
      <p>The two option answers disagree by more than the crowd disagrees with either. So "the crowd is rich" or "cheap" depends on the model. It is well above the floor, so it is not treating touches like finishes.</p>`,
    lab: `<div class="chips" id="p-dir"></div><div class="chart"></div><div class="stats"></div>`,
    init(root) {
      const stats = Stats(q(root, '.stats'));
      let dir = 'reach';
      const keys = [['primary', '2 x digital', 'cash'], ['GBM barrier', 'Formula', 'fut'], ['digital lower bound', 'Floor', 'muted']];
      const r = () => {
        chart(q(root, '.chart'), {
          alt: 'Crowd price minus each fair value', h: 230, x: [-0.6, 2.6], y: [-7, 14], zero: true, xl: '', xf: () => '', yl: 'Crowd minus fair value, cents', yf: (t) => t.toFixed(0),
          bars: keys.map(([k, , c], i) => ({ x: i, y: P[k][dir].est * 100, w: 44, c })),
          labels: keys.flatMap(([k, n], i) => [{ x: i, y: -7, dy: 16, a: 'middle', t: n, c: 'muted' }, { x: i, y: P[k][dir].est * 100, dy: P[k][dir].est >= 0 ? -8 : 16, a: 'middle', t: cents(P[k][dir].est) }]),
        });
        stats([['Vs 2 x digital', cents(P.primary[dir].est), null, 'cash'], ['Vs formula', cents(P['GBM barrier'][dir].est), null, 'fut'], ['Vs floor', cents(P['digital lower bound'][dir].est), null, 'muted']]);
      };
      pick(q(root, '#p-dir'), 'Markets', [['Reach (up)', 'reach'], ['Dip (down)', 'dip']], (v) => { dir = v; r(); });
      return r;
    },
  },
  {
    id: 'mood', kicker: 'Result 3', title: 'Mood and crowding do not move the crowd\'s pricing',
    body: `<p>Crypto factor models track crowding (what futures traders pay to stay long) and mood (the Fear & Greed index). If the crowd gets carried away, its touch prices should lean up in greedy, crowded weeks.</p>
      <p>They do not. No slope is significant: the closest is funding on dip markets, p ${pval(D.mood['dip on fund_z'].p)}. The difference between up and down premiums does not move with mood (p ${pval(D.mood['asym on fng_z'].p)}) or crowding (p ${pval(D.mood['asym on fund_z'].p)}).</p>`,
    lab: `<div class="stats"></div>`,
    init(root) {
      const stats = Stats(q(root, '.stats'));
      return () => stats([['Up minus down, mood', pval(D.mood['asym on fng_z'].p), null, 'muted'], ['Up minus down, crowding', pval(D.mood['asym on fund_z'].p), null, 'muted'], ['Trading rule', `${pc(D.trading.ret, 1)} (range ${pc(D.trading.lo, 0)} to ${pc(D.trading.hi, 0)})`, null, 'muted']]);
    },
  },
  {
    id: 'arb', kicker: 'Result 4', title: 'The "free money" against Kalshi was two spreads',
    body: `<p>Kalshi sells "BTC above K at 5 pm" for the same day. If BTC is above K at 5 pm it has touched K, so the touch price should never be lower. In ${D.kalshi.violations} of ${D.kalshi.pairs.toLocaleString('en-US')} paired trades it was, by more than both fees.</p>
      <p>Then the checks: trades within a minute of each other with BTC flat left ${D.kalshi.flat}. Requiring prints on the sides you could actually trade against left <b>${D.kalshi.executable}</b>. Each "violation" was a cheap sale on one venue next to an expensive purchase on the other.</p>`,
    deep: '<p>The side check was added after the violations were seen, so it is labeled exploratory. Prints show where someone traded, not the full order book; with quotes, a few tiny windows might remain.</p>',
    lab: `<div class="chart"></div>`,
    init(root) {
      return () => {
        const steps = [['Below the bound', D.kalshi.violations, 'muted'], ['Same minute, BTC flat', D.kalshi.flat, 'muted'], ['Tradeable sides', D.kalshi.executable, 'bad']];
        chart(q(root, '.chart'), {
          alt: 'Kalshi violations after each check', h: 240, x: [-0.6, 2.6], y: [0, 300], xl: '', xf: () => '', yl: 'Paired trades', yf: (t) => t.toFixed(0),
          bars: steps.map(([, n, c], i) => ({ x: i, y: n, w: 56, c })),
          labels: steps.flatMap(([l, n], i) => [{ x: i, y: 0, dy: 16, a: 'middle', t: l, c: 'muted' }, { x: i, y: n, dy: -8, a: 'middle', t: String(n) }]),
        });
      };
    },
  },
  {
    id: 'together', kicker: 'Summary', title: 'What this says',
    body: `<p><b>1. The crowd understands path risk.</b> On a market trading about $1 million a day, retail prices for touch bets are as accurate as the options market's.</p>
      <p><b>2. No mispricing big enough to trade.</b> The crowd sits inside the range of reasonable fair values, with a small long-shot tilt that is smaller than the fee.</p>
      <p><b>3. No cross-venue arbitrage</b> once you check which side of the spread each trade hit.</p>
      <p>Together with thin altcoin ladders, where simple models did beat the crowd, the pattern is: <b>enough money makes the crowd good.</b></p>`,
    lab: listHtml([['Most solid', 'Calibration and accuracy: 326 events, outcomes rebuilt from Binance.'], ['Model-dependent', 'Whether the crowd is a cent or two rich or cheap.'], ['Exploratory', 'The executable-sides check on the Kalshi violations.']]),
  },
  {
    id: 'limits', kicker: 'Limits', title: 'What this cannot tell you', solo: true,
    lab: listHtml([
      ['One path per window', 'All strikes in an event share one BTC path, so the real sample is events, not trades. Monthly rests on 23.'],
      ['Two venues, two prices', 'Touch markets use Binance one-minute wicks; Deribit options use a multi-exchange index.'],
      ['Trades are not quotes', 'A trade shows where someone traded, not the spread you would pay.'],
      ['Data fixes after a look', 'Run 3\'s numbers were seen before three parsing bugs were fixed. They are disclosed; the model and tests did not change.'],
    ]),
  },
  {
    id: 'quiz', kicker: 'Check yourself', title: 'Four quick questions', solo: true,
    lab: `<div class="quiz-q"></div><div class="opts"></div><div class="note" hidden></div><div class="quiz-foot"><span class="tag"></span><button class="chip big on" type="button" hidden>Next question</button></div>`,
    init(root) {
      const qs = [
        { q: 'BTC has a 15% chance of finishing above $110,000 tomorrow. Roughly what should "Will BTC reach $110,000 tomorrow?" cost?', o: ['About 15 cents', 'About 30 cents', 'About 7 cents'], a: 1, w: 'Touching is about twice as likely as finishing beyond, so about 30 cents.' },
        { q: 'Why can jumps make touching less than twice as likely?', o: ['Jumps make prices fall', 'A jump can leap over the level without the touch-and-return the mirror argument needs', 'Jumps only happen at night'], a: 1, w: 'The mirror trick needs the path to cross the level smoothly.' },
        { q: 'A touch market trades at 20 cents while finishing beyond the same strike trades at 25 cents. What is that?', o: ['Normal', 'A price that breaks a no-arbitrage bound', 'A long-shot bias'], a: 1, w: 'Finishing beyond means it touched, so the touch can never be worth less.' },
        { q: 'Why were the Kalshi "violations" not free money?', o: ['Fees were too high', 'They paired a cheap sale on one venue with an expensive purchase on the other', 'Kalshi cancelled them'], a: 1, w: 'They were bid on one side and ask on the other: the two spreads.' },
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
    lab: `<input class="search" type="search" id="term-search" placeholder="Search terms, such as touch or smile" aria-label="Search terms"><div class="terms"></div>`,
    init(root) {
      const terms = [
        ['Touch market', 'A bet that pays if a price trades at a level at any moment in a window. In options language, a one-touch.'],
        ['Finish beyond (digital)', 'A bet that pays if the price is beyond a level at one fixed time.'],
        ['Reflection principle', 'For a smooth random walk, touching a level is twice as likely as finishing beyond it.'],
        ['Barrier formula', 'The exact touch probability for a random walk with constant volatility.'],
        ['Implied volatility', 'The move an option price implies. Deribit reports it with every trade.'],
        ['Volatility smile', 'Implied volatility differs by strike. For BTC, lower strikes usually cost more.'],
        ['Deribit', 'The largest BTC options exchange.'],
        ['Polymarket', 'A prediction market. Its BTC touch markets resolve on Binance one-minute candles.'],
        ['Kalshi', 'A US-regulated event-contract exchange with daily BTC "above K at 5 pm" ladders.'],
        ['No-arbitrage bound', 'A price relation that must hold or someone can lock in a profit. Here: touch is worth at least finish-beyond.'],
        ['Bid and ask', 'The best prices to sell and to buy. A trade at the bid and one at the ask can look like a gap that is really just the spread.'],
        ['Calibration', 'Whether 30-cent contracts happen about 30% of the time.'],
        ['Brier score', 'Average of (price - outcome) squared. Lower is better.'],
        ['Long-shot bias', 'Cheap contracts win less often than their price suggests.'],
        ['Funding rate', 'What perpetual-futures longs pay shorts. High means crowded longs.'],
        ['Fear & Greed index', 'A daily 0-to-100 score of crypto market mood.'],
      ];
      const box = q(root, '.terms');
      const paint = (f) => {
        const s = f.trim().toLowerCase();
        const hits = terms.filter(([a, b]) => `${a} ${b}`.toLowerCase().includes(s));
        box.innerHTML = hits.length ? hits.map(([a, b]) => `<div class="term"><b>${a}</b>${b}</div>`).join('') : '<div class="empty">No matching terms. Try "touch" or "smile".</div>';
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
          ['Fair value', 'For a one-day BTC one-touch, would you use twice the smile digital, a local-volatility price, or something fitted to realized wicks?'],
          ['Efficiency', 'Is a $1-million-a-day crowd market deep enough that you would expect it to be efficient?'],
          ['Venue risk', 'How much would single-exchange wicks change a touch price compared with an index?'],
        ]],
        ['Mistakes to avoid', [
          ['"Crowds misprice path risk."', 'Not here: the crowd priced touches well above finishes and was well calibrated.'],
          ['"A price gap across venues is arbitrage."', 'Check which side of the spread each trade hit first.'],
          ['"The model says the crowd is rich."', 'Two standard models disagree by more than the gap.'],
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
