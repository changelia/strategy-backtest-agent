# How it works

A short tour of the engine for Python developers who are new to this project.
It explains the moving parts in plain English. Exact rules, limits and edge cases
live in the normative design record, [ARCHITECTURE.md](../ARCHITECTURE.md); each
section below links to the matching part of it. If this guide and ARCHITECTURE.md
ever disagree, ARCHITECTURE.md wins.

## 1. What the package is and is not

`strategy-backtest-agent` turns a fixed trading rule into a reproducible historical
research result. It is a single-symbol, long-only tool: one position at a time,
using all available cash, with no leverage and no short selling.

It is **not** a trading system. It never places orders, recommends investments or
predicts future returns. Backtesting does not predict future profitability, and
every research mode reports descriptive history only.

All signals, trades and financial results are deterministic Python operations for a
fixed validated strategy and candle history. AI is optional: it can parse a request
into a configuration and select grounded report explanations, but it never
calculates results. See
[Historical warm-up policy](../ARCHITECTURE.md#historical-warm-up-policy) and
[Parser defaults and API boundaries](../ARCHITECTURE.md#parser-defaults-and-api-boundaries).

## 2. The flow of one backtest

```text
plain-English request ──► AI parsing (optional, OpenAI) ─┐
                                                         ▼
explicit JSON config ─────────────────────────► validated rule DSL
                                                         │
                                                         ▼
                         history fetch: requested UTC window + warm-up candles
                                                         │
                                                         ▼
                         causal indicators, each series computed once
                                                         │
                                                         ▼
                         signal on completed candle N → fill at candle N+1 open,
                         with fee, spread and slippage
                                                         │
                                                         ▼
                         metrics (return, benchmark, drawdown, win rate, ...)
                                                         │
                                                         ▼
                         JSON result → terminal summary or saved report
```

1. **Request or config.** A plain-English request goes through the AI parser; an
   explicit JSON configuration skips AI entirely and needs no OpenAI key.
2. **Validation.** Python validates the whole rule tree, whatever its source.
   Unknown fields, unsupported features and ambiguous requests fail instead of being
   simplified.
3. **History.** The provider fetches the requested window plus enough earlier
   candles to initialize every indicator. Gaps and insufficient history are errors;
   no values are fabricated.
4. **Indicators.** Each unique indicator dependency is calculated once. The value
   at candle i depends only on closes (and, for ATR, highs and lows) at or before i.
5. **Execution.** Signals are evaluated on completed candles and executed at the
   next open, with modeled costs.
6. **Metrics and output.** The existing metrics module summarizes the run, and the
   result is printed or saved as JSON, then optionally rendered as a report.

See [Validation and indicator preparation](../ARCHITECTURE.md#validation-and-indicator-preparation),
[Execution and compatibility](../ARCHITECTURE.md#execution-and-compatibility) and
[Strategy DSL reference](../ARCHITECTURE.md#strategy-dsl-reference).

### The rule language in one paragraph

Operands are the completed candle close (`price`), finite constants (`value`) and
indicators: RSI, SMA, EMA, MACD, Bollinger Bands and ATR. Comparisons are `<`, `<=`,
`>` and `>=`, combined with nested `and` / `or` groups. A strategy has an entry rule
and an exit rule, at most 20 comparisons and depth at most 5. NOT and crossover
events are unsupported: `SMA 20 > SMA 50` is a level comparison, while
`SMA 20 crosses above SMA 50` is rejected. An unavailable or nonfinite operand makes
its comparison false. See [Strategy DSL reference](../ARCHITECTURE.md#strategy-dsl-reference)
and [Advanced indicator conventions](../ARCHITECTURE.md#advanced-indicator-conventions).

## 3. Layers and where they live

All paths are under `src/strategy_backtest_agent/`.

| Layer | Modules | Role |
| --- | --- | --- |
| Public client and CLI | `client.py`, `cli.py`, `services.py`, `init_cli.py`, `doctor.py`, `execution_cli.py`, `demo.py` | `BacktestClient` and the `strategy-backtest` command: parse, run, research modes, templates, diagnostics, reports; synthetic demo candles |
| Research modes | `comparison/`, `validation/`, `sensitivity/`, `costs/`, `walk_forward/` | Each has models, an engine, a formatter and a CLI; engines orchestrate the core and never recalculate trades or metrics |
| Engine core | `backtester.py`, `execution.py`, `metrics.py`, `indicators.py`, `models.py`, `strategy.py` | The only code that computes financial numbers: next-open execution, fills and fees, equity, metrics, indicator series |
| Rule DSL | `rules/` | Rule models and validation, indicator specs and warm-up, the evaluator and its indicator cache, history fetching, deterministic formatting |
| Data provider | `market_data.py` | `MarketDataProvider` protocol and `BinanceMarketData` |
| AI | `ai/` | OpenAI structured-output parsing and prompts; creates the OpenAI client that report interpretation also reuses |
| Reports | `reports/` | Input adapters, consistency validation, evidence extraction, Markdown/JSON rendering, optional constrained AI and offline HTML |

## 4. Execution, costs, metrics and warm-up

### Timing

A signal using completed candle N executes at the **open of candle N+1**, for both
entry and exit. A signal on the last candle cannot execute. Any position still open
at the end is liquidated at the final close; this is a simulation boundary, not a
signal. Open positions evaluate the exit rule and flat portfolios evaluate the
entry rule, so at most one action executes at each open. See
[Candle boundaries and accounting](../ARCHITECTURE.md#candle-boundaries-and-accounting).

### Costs

Three costs apply to every fill:

- **Fee** per side, as a fraction (for example `0.001`).
- **Spread**: the full bid/ask spread in basis points; half is applied on each side.
- **Slippage**: adverse, per side, in basis points.

For a reference price P, with a = (spread_bps / 2 + slippage_bps) / 10000, a buy
fills at P × (1 + a) and a sell at P × (1 − a). The fee is then charged on the fill.
Spread and slippage are already inside the fill prices; reported spread and
slippage amounts are attribution and must not be deducted a second time. OHLC
prices act as mid-price proxies, so a modeled fill may lie outside the candle's
high/low. See [Deterministic execution costs](../ARCHITECTURE.md#deterministic-execution-costs-v070)
and [Accounting, marking and benchmark](../ARCHITECTURE.md#accounting-marking-and-benchmark).

### Metrics

| Metric | Meaning |
| --- | --- |
| Total return | `(final balance / initial balance - 1) * 100` |
| Buy & Hold | Buy at the first evaluation open, sell at the last close, with the same costs |
| Win rate | Positive net-PnL trades / all completed trades, as a percentage |
| Max drawdown | Largest peak-to-trough equity decline, as a nonpositive percentage |
| Profit factor | Sum of positive net PnL / absolute sum of negative net PnL |

Equity is sampled at every candle open and close, so drawdown cannot see intrabar
highs and lows. Undefined is not zero: no trades gives a null win rate and profit
factor, and no losing trades gives a null profit factor. Initial balance plus all
net trade PnLs equals the final balance. See [Metrics](../ARCHITECTURE.md#metrics).

### Warm-up

Before the evaluation window, the engine fetches enough completed candles to
initialize the indicators. The requirement is the maximum over all referenced
indicators:

| Indicator | Prior completed candles |
| --- | --- |
| RSI(p) | p + 1 |
| SMA(p) | p |
| EMA(p) | 5 × p |
| MACD(fast, slow, signal) | 10 × (slow + signal) |
| Bollinger(p) | p |
| ATR(p) | 20 × p |
| Only price/constants | 0 |

Warm-up candles initialize indicators only. They never generate signals or trades
and never enter equity or the Buy & Hold benchmark. These counts are fixed finite
approximations, not exact infinite-history indicators, and small residual seed
differences can change signals near thresholds. See
[Historical warm-up policy](../ARCHITECTURE.md#historical-warm-up-policy) and
[Warm-up, dependency identity and metadata](../ARCHITECTURE.md#warm-up-dependency-identity-and-metadata).

### The two seed policies

Where an indicator series starts (its seed) is part of the result:

- **Common legacy seed** — comparison and validation. RSI, SMA and EMA share one
  lookback equal to the maximum legacy warm-up across all strategies, so adding a
  strategy with a longer RSI/EMA/SMA period can move the seed and change signals of
  unchanged strategies. Advanced indicators (MACD, Bollinger, ATR) use individual
  anchors here.
- **Dependency-local anchors** — sensitivity, costs and walk-forward. Each indicator
  starts exactly its own warm-up before the first evaluation (or Train) open, so
  adding a longer-period variant or strategy cannot move another indicator's seed.

Results for the same strategy can therefore differ between commands; the reports
record the anchors used. Legacy single-strategy RSI runs keep their original
in-range initialization. See
[Shared history, initialization and indicators](../ARCHITECTURE.md#shared-history-initialization-and-indicators)
and [Warm-up, dependency identity and metadata](../ARCHITECTURE.md#warm-up-dependency-identity-and-metadata).

## 5. The six research modes

Every mode reuses the same DSL, provider, indicators, backtester and metrics. Each
makes one history fetch, and every backtest inside it starts with fresh cash and no
position; segments, folds, variants and scenarios never share cash, positions or
signals.

| Mode (CLI) | Question it answers | Segment evaluated | It never |
| --- | --- | --- | --- |
| Single backtest (`strategy-backtest`, `ai`) | How did one fixed rule behave? | The requested evaluation window | Predicts or recommends |
| Comparison (`compare`) | How did 2–5 rules behave on identical history? | The evaluation window, shared by all strategies | Builds a composite score or picks a winner; ranking uses one chosen metric |
| Validation (`validate`) | What changed on held-out data? | Chronological Train, then Test, for 1–5 strategies | Ranks, selects or optimizes strategies |
| Sensitivity (`sensitivity`) | How do results move across a declared parameter grid? | Train only; Test is reserved and never evaluated | Optimizes, selects or recommends a variant |
| Costs (`costs`) | How much did modeled costs matter? | Train only, 2–8 declared scenarios against a zero-spread/slippage baseline | Sorts scenarios or picks a winner |
| Walk-forward (`walk-forward`) | How did fixed rules behave across rolling or expanding folds? | Train and Test per fold; aggregates use Test only | Re-optimizes per fold or carries positions across folds |

A few rules worth knowing:

- **Validation** splits the evaluation candles chronologically at
  `floor(N × train_ratio)` (default 0.70). Test indicators keep earlier history for
  initialization, but Test starts with fresh cash, and the last Train signal cannot
  execute in Test.
- **Sensitivity** expands 1–3 dimensions into at most 25 variants in a stable order
  and describes neighbors; its labels are heuristics, not robustness scores.
- **Walk-forward** needs at least two complete folds, rejects silent truncation and
  can add a stitched out-of-sample index built from fold endpoints, not a
  continuous portfolio.
- Holdout validity depends on freezing rules before looking at Test; the software
  cannot prove the data was unseen.

See [Strategy comparison](../ARCHITECTURE.md#strategy-comparison),
[Chronological out-of-sample validation](../ARCHITECTURE.md#chronological-out-of-sample-validation),
[Deterministic parameter sensitivity](../ARCHITECTURE.md#deterministic-parameter-sensitivity),
[Shared research engines and cost scenarios](../ARCHITECTURE.md#shared-research-engines-and-cost-scenarios)
and [Fixed-strategy walk-forward analysis](../ARCHITECTURE.md#fixed-strategy-walk-forward-analysis).

## 6. Reports

`strategy-backtest report --input <file>` and the client's report methods read one
existing JSON result. They never call a data provider or the backtester and never
recompute an indicator or trade.

- **Validation.** Inputs are untrusted and bounded (for example 16 MiB and depth 32).
  An explicit adapter identifies each supported result type; ambiguous shapes are
  rejected rather than guessed. Accounting, segment bounds and summaries are checked
  for consistency.
- **Evidence.** Metrics are copied with stable IDs, JSON source paths, units and
  context. Percent and percentage points are kept separate, monetary costs use the
  quote currency, and undefined metrics stay null. Sensitivity and cost results are
  labeled Train-only.
- **Formats.** Markdown, strict JSON and, in unreleased source, offline HTML. The
  HTML renderer uses no scripts or external assets, and HTML cannot be combined with
  AI interpretation.
- **Optional AI.** With `--ai`, the model only selects from approved explanation and
  research-question codes for deterministic observations. Unknown references, free
  prose, invented numbers, advice and forecasts reject the interpretation. If AI is
  unavailable or rejected, the full deterministic report is still produced.
- **Safe output.** Files are written atomically and never overwrite an existing
  destination or the input; symlinked directories and parent traversal are rejected.

See [Evidence-grounded reports](../ARCHITECTURE.md#evidence-grounded-reports-v10-feature)
and [Optional interpretation and trust boundaries](../ARCHITECTURE.md#optional-interpretation-and-trust-boundaries).

## 7. Trust boundaries and limitations

**Trust boundaries**

- Only the Python engine computes financial numbers. AI parses requests and selects
  grounded explanations; it never calculates results, ranks strategies or runs code.
- Config mode never imports the AI parser and needs no OpenAI key. OpenAI requests
  use `store=False`, a 30-second timeout and no automatic retries.
- No prompt, credential or raw provider response reaches JSON output or errors.
- No arbitrary expressions, generated code or dynamic code execution are used.
- The CLI loads `.env` once without overriding shell values; library calls do not
  load files implicitly.

**Main limitations**

- Full fills, unlimited liquidity and constant modeled costs; no order book, market
  impact, partial fills, funding or taxes.
- Drawdown sees only candle opens and closes, and financial arithmetic uses floats.
- Finite RSI/EMA/MACD/ATR initialization is an approximation, and seed policies
  differ between commands.
- Exact replay needs a fixed `evaluation_end` and identical candles. Binance can
  revise history; the recorded SHA256 detects changes but cannot recover prices.
- Natural-language parsing can be wrong even when validation succeeds; review the
  parsed configuration before relying on results.
- Unsupported: stop loss, take profit, leverage, shorts, crossover events, multiple
  symbols, automatic optimization, live trading and predictions.

See [Parser defaults and API boundaries](../ARCHITECTURE.md#parser-defaults-and-api-boundaries),
[CLI environment configuration](../ARCHITECTURE.md#cli-environment-configuration) and
[Reproducibility and limitations](../ARCHITECTURE.md#reproducibility-and-limitations).
