# Strategy Backtest Agent

**Describe a trading strategy in plain English. Backtest it against real historical market data.**

Strategy Backtest Agent turns single-symbol, long-only trading rules into validated
strategies and tests them on Binance historical candles. OpenAI interprets your
request; Python calculates indicators, signals, trades, fees, and performance metrics.
Use the CLI to explore a strategy or export JSON for your own research tools.

Current release: **v1.0.0 — Evidence-Grounded AI Research Reports**.
Release tag and package version: **v1.0.0**. See [CHANGELOG.md](CHANGELOG.md).

## Quick Start

Requires Python 3.12+, Poetry 2.x, an OpenAI API key for AI mode, and network access
to OpenAI and Binance public market data.

```bash
git clone https://github.com/changelia/strategy-backtest-agent.git
cd strategy-backtest-agent
poetry install
export OPENAI_API_KEY="your_openai_api_key_here"

poetry run strategy-backtest ai \
  'Backtest BTCUSDT on 1h for 90 days. Buy when RSI 14 < 30 and price > EMA 200. Sell when RSI 14 > 70 or price < EMA 50. Start with $10,000.'
```

The command displays the parsed strategy and backtest results. Review the parsed
rules: natural-language interpretation can be wrong even when validation succeeds.
AI requests send your text to OpenAI and incur API usage charges. Both AI strategy
parsing and report interpretation default to `gpt-4.1-mini`. `OPENAI_MODEL` overrides
the default for both features; the selected model must support Responses and Structured Outputs.
Never include secrets in strategy requests. See configuration below for shell and `.env` settings.

Try the deterministic offline demo without credentials or network access:

```bash
poetry run strategy-backtest --demo --days 30
```

The demo is a reproducibility and CLI example, not a profitability example.
The default 180-day run returns -98.77% (45 losing trades); this matches v0.9.0
exactly under the fixed synthetic candles and existing RSI/execution rules.

## Example Output

Actual output from the 30-day offline demo above. The prices are **synthetic**, not
historical BTCUSDT data; these results are not evidence of real-market performance.

```text
Strategy Backtest
────────────────────────────────
Symbol: BTCUSDT
Timeframe: 1h
Period: 30 days
Data: synthetic offline demo (720 candles)
Range (candle opens, UTC): 2024-06-01 00:00:00+00:00 → 2024-06-30 23:00:00+00:00

Strategy: RSI
RSI Period: 14
Entry RSI: < 30
Exit RSI: > 70
Fee per side: 0.1%

Results (quote currency)
Initial Balance: 10,000.00
Final Balance: 4,725.85
Total Return: -52.74%
Buy & Hold: +1.00%
Trades: 8
Winning Trades: 0
Losing Trades: 8
Win Rate: +0.00%
Max Drawdown: -52.87%
Profit Factor: 0.00
```

## Configuration

The CLI automatically loads `.env` from the current directory or nearest parent
once at startup, before dispatching any command. For example:

```dotenv
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4.1-mini
```

Existing shell variables always take precedence (`override=False`). You can still
configure both values with `export`; no `.env` is required. `.env` is already
ignored by Git—never commit credentials. Offline reports and demo need no API key.

## Compare Strategies

Compare 2–5 strategies on the same symbol, timeframe, historical window, initial
balance, and fee. Each strategy runs its own independent portfolio.

```bash
poetry run strategy-backtest compare \
  'Compare RSI 25/70, RSI 30/70 and SMA 20/50 on BTCUSDT over 90 days'
```

Or use a validated JSON config without an OpenAI key (Binance access required):

```bash
poetry run strategy-backtest compare --config examples/comparison.json
poetry run strategy-backtest compare --config examples/comparison.json --json
poetry run strategy-backtest compare --config examples/comparison.json --sort max_drawdown
```

The [example config](examples/comparison.json) sets a fixed UTC end time. Data is
fetched once, and shared indicators are calculated once. All comparison strategies,
including legacy RSI configurations, use the same prior-history warm-up. This can
produce different results from single-strategy legacy RSI runs.

The table shows returns, excess return, drawdown, trades, win rate, and profit factor.
**Excess return** is strategy return minus buy-and-hold return, in percentage points.
Sort by `total_return` (default), `excess_return`, `max_drawdown`, or `profit_factor`.
Less negative drawdown ranks higher; undefined metrics rank last, with ties broken
by strategy ID. A null profit factor is not infinity. Rankings describe historical
results and do not predict which strategy will perform best in the future.

Comparison JSON contains `configuration`, `shared_data`, `buy_and_hold_return_percent`,
`results`, `ranking_criterion`, and ranked strategy IDs in `ranking`. It records the
resolved UTC window, warm-up policy, definitions, and a candle-history digest. A fixed
end makes the requested window repeatable; exact reproduction requires the same data.
Multi-symbol comparisons and per-strategy overrides of shared trading settings are rejected.

## Train/Test Validation

Validate 1–5 fixed strategies on chronological Train and Test segments:

```bash
poetry run strategy-backtest validate \
  'Validate RSI 30/70 and SMA 20/50 on BTCUSDT over 180 days using a 70/30 train/test split'
poetry run strategy-backtest validate --config examples/validation.json
poetry run strategy-backtest validate --config examples/validation.json --json
```

Config mode needs no OpenAI credentials. The [example](examples/validation.json)
sets a fixed UTC end. One shared fetch includes the maximum indicator warm-up.
Train receives the first `floor(completed evaluation candles × train_ratio)` candles;
Test receives all remaining candles. Default ratio is 0.70, allowed range 0.50–0.90.
Each segment needs at least two candles; insufficient history is rejected.

Each segment starts flat with its own initial cash. Prior candles initialize causal
indicators only. The first signal uses the first completed segment candle and executes
at the next segment open. Final-candle signals never cross the split; open positions
liquidate at their own segment's final close. No trades or equity carry into Test.
Exact UTC boundaries, candle counts, warm-up and a full-history SHA256 are recorded.

**Test is Held-out evaluation.** Select and freeze strategies before examining Test;
repeated inspection or choosing strategies using Test contaminates the holdout.
The return gap is `Test return − Train return`, in percentage points. It is descriptive:
durations differ and total returns are not normalized. No winner or robustness score
is assigned. A single holdout cannot establish robustness or future profitability.
Parameter optimization is unsupported; use `walk-forward` for multiple fixed-strategy windows.

JSON contains `configuration`, `shared_data`, `split`, per-strategy `results` with
independent Train/Test metrics and trades, `return_gap_pp`, and `methodology_warnings`.
Undefined metrics are `null`; JSON stdout contains no progress messages.
Fixed boundaries make the window repeatable; exact replay requires unchanged candles,
including warm-up. See [ARCHITECTURE.md](ARCHITECTURE.md#chronological-out-of-sample-validation)
for boundary policy and initialization limitations.

## Walk-Forward Analysis

Evaluate 1–5 **fixed, predeclared** strategies on multiple chronological Train/Test
windows, with fresh capital in every segment:

```bash
poetry run strategy-backtest walk-forward --config examples/walk-forward.json
poetry run strategy-backtest walk-forward --config examples/walk-forward.json --json
poetry run strategy-backtest walk-forward \
  'Run rolling walk-forward analysis of RSI 30/70 and SMA 20/50 on BTCUSDT on 1h over 360 days with 120-day Train and 30-day Test windows'
```

Config mode needs no OpenAI key. Rolling Train windows have fixed lengths; expanding
Train windows retain the first evaluation candle and grow each fold. Durations are
whole days converted to exact candle counts. Step defaults to Test length; smaller
steps are rejected to prevent overlapping Test windows. At least two complete folds
are required, with a configurable limit (default 50, hard maximum 100). Excess folds
are rejected; incomplete final windows are excluded and trailing candles reported.

Reports include per-fold results, costs and net Buy & Hold, plus Test-only medians,
ranges, trade counts and positive/outperforming fold counts. Optional `stitch_oos`
compounds normalized independent Test returns into a **fold-endpoint index** starting
at 100. It requires contiguous Test windows and represents no position continuity or
continuous portfolio drawdown. All segments use the same declared execution costs.

Multiple OOS periods reveal variation across historical windows, but do not guarantee
robustness or future profitability. Train is diagnostic: no parameter optimization,
adaptive selection or winner ranking occurs. Choosing strategies after inspecting
this history undermines independent held-out evidence. See
[ARCHITECTURE.md](ARCHITECTURE.md#fixed-strategy-walk-forward-analysis) for initialization,
boundaries and aggregate definitions.

## Parameter Sensitivity

Explore how fixed numerical choices change historical results on **Train only**:

```bash
poetry run strategy-backtest sensitivity \
  'Analyze nearby RSI 30/70 thresholds on BTCUSDT over 180 days'
poetry run strategy-backtest sensitivity --config examples/sensitivity.json
poetry run strategy-backtest sensitivity --config examples/sensitivity.json --json
```

Config mode needs no OpenAI key. [RSI](examples/sensitivity.json),
[SMA](examples/sensitivity-sma.json), and [EMA](examples/sensitivity-ema.json)
examples use fixed UTC ends. The existing DSL is the base strategy. Specify exact
paths, including `entry.conditions.0.left.period` for nested rules:

```json
{"path": "entry.right.value", "values": [25, 30, 35]}
{"path": "entry.left.period", "coupled_paths": ["exit.left.period"],
 "range": {"start": 10, "stop": 20, "step": 5}}
{"path": "exit.right.value", "nearby": {}}
```

Each line above is a separate parameter specification. Choose exactly one source:
explicit values, an inclusive stepped range, or nearby values. Nearby defaults are
base±5 for RSI thresholds and base±1 for indicator periods; other constants require
an explicit step. Periods must remain integers. Invalid combinations fail the entire
grid; values are never clipped or discarded. Limits: three dimensions, 25 variants,
and existing DSL complexity. Candidate order controls output and neighbor adjacency.
Repeated indicators stay independent unless their exact paths are explicitly coupled.

The default 70/30 chronological split reserves Test without evaluating it. All variants
use the same Train boundaries, one maximum-warm-up fetch, fresh cash, fees and
Train final-close liquidation. Each indicator uses its own fixed prior-history window
anchored to Train start, so adding longer grid periods cannot change existing seeds.
RSI/EMA initialization remains finite; JSON records each indicator's initialization
boundary. Test candles never reach indicators or backtests.
Output includes per-variant metrics, min/median/max return, range, positive-return and
buy-and-hold outperformance percentages, neighbor differences, and a 1D series or
2D return matrix. JSON records the complete grid, definitions, split and history SHA256.

These statistics describe the declared grid only. Similar neighboring returns or an
isolated spike are descriptive observations; configurations with fewer than five trades
are flagged, including zero trades. Repeated experimentation can overfit Train.
**No variant is ranked, selected or recommended.** Sensitivity is not optimization,
a robustness test or a profitability prediction. Freeze a preselected strategy before
separately running `validate`; the software cannot prove its Test data was unseen.

## Execution Costs

Added costs default to zero, preserving v0.6.0 numerical results. Fees remain 0.1% per executed side by default.

```bash
poetry run strategy-backtest --demo --spread-bps 20 --slippage-bps 10
poetry run strategy-backtest ai \
  'Backtest BTCUSDT on 1h for 180 days using RSI 30/70, with 10 bps spread and 5 bps slippage.'
poetry run strategy-backtest validate --config examples/validation.json --spread-bps 10 --slippage-bps 5 --json
poetry run strategy-backtest costs --config examples/execution-scenarios.json --json
```

The same flags work for explicit backtests, AI, compare, validate and sensitivity.
JSON configs accept `{"execution": {"spread_bps": 10, "slippage_bps": 5}}`; omitted
`fee_rate` inherits legacy `fee` (`fee_rate` in AI configuration). Conflicting explicit
fee settings are rejected. Config-only workflows need no OpenAI key.

**Spread is the full bid/ask spread**, with half applied on each side. Slippage is
adverse per side. With 20 bps spread and 10 bps slippage, buy reference 100 fills
at 100.20; sell reference 110 fills at 109.78. Fees are charged separately.
OHLC prices are mid-price proxies, not measured quotes or actual historical fills.

Open positions retain reference-price equity valuation; costs apply only to fills.
Buy & Hold buys at the first evaluation open and sells at the final close using
the same costs. Reports separate charged fees from modeled spread/slippage amounts.

[Cost scenarios](examples/execution-scenarios.json) evaluate one frozen DSL strategy
on Train only, sharing data and indicators with fresh portfolios. Declare 2–8 ordered
scenarios; the first has zero spread/slippage and supplies the comparison baseline.
Fees inherit the shared rate unless explicitly varied. These illustrative assumptions
are neither Binance cost estimates nor an optimization or recommendation.

## Advanced Technical Indicators

MACD, Bollinger Bands and ATR work with the same nested rule DSL and all research
commands. Config mode needs no OpenAI key:

```bash
poetry run strategy-backtest compare --config examples/advanced-comparison.json --json
poetry run strategy-backtest validate --config examples/advanced-validation.json
poetry run strategy-backtest sensitivity --config examples/advanced-sensitivity.json
poetry run strategy-backtest costs --config examples/advanced-costs.json
poetry run strategy-backtest walk-forward --config examples/advanced-walk-forward.json
poetry run strategy-backtest ai \
  'Backtest BTCUSDT on 1h for 90 days. Buy when MACD line is above signal line and RSI is below 35. Sell when MACD line is below signal line.'
```

Operands keep `type: "indicator"`. MACD uses `name: "macd"`, `fast_period: 12`,
`slow_period: 26`, `signal_period: 9`, and `component: "macd"`, `"signal"` or
`"histogram"`. Bollinger uses `name: "bollinger"`, `period: 20`, `multiplier: 2.0`
and an explicit `component: "upper"`, `"middle"` or `"lower"`. ATR uses
`name: "atr"`, `period: 14`, and **high/low/previous close**, with no component.
Numerical defaults apply when omitted; explicit invalid parameters are rejected.

MACD price EMAs seed at the first historical close; its signal EMA seeds at the
first available MACD value. Bollinger uses **population standard deviation**
(`ddof=0`). ATR uses an SMA True Range seed followed by Wilder smoothing.
Warm-up is MACD `10 × (slow + signal)`, Bollinger `period`, ATR `20 × period`
prior candles. Each new indicator has its own recorded history anchor; finite
MACD/ATR seeds can still influence threshold-adjacent signals.

`MACD line > signal` is a state condition. **Crosses above/below and crossover
operators remain unsupported.** Sensitivity accepts MACD `.fast_period`,
`.slow_period`, `.signal_period`, Bollinger `.period`/`.multiplier`, and ATR
`.period` paths on operands; invalid combinations fail the whole grid. See
[ARCHITECTURE.md](ARCHITECTURE.md#advanced-indicator-conventions) for formulas,
initialization policies and compatibility details.

## Supported Strategies

- Wilder RSI, SMA, EMA, MACD, Bollinger Bands, ATR, completed candle close (`price`), and constants
- Level comparisons: `<`, `<=`, `>`, `>=`, including indicator-to-indicator comparisons
- AND/OR conditions and clearly specified nested groups
- One symbol, one long position at a time, full available cash allocation
- Next-candle-open execution, entry/exit fees, and final-close liquidation
- Return, buy-and-hold comparison, trade PnL, win rate, drawdown, and profit factor
- Paginated Binance historical data, terminal summaries, JSON, and an offline demo
- Single-symbol comparisons, chronological validation and bounded parameter sensitivity

DSL periods: RSI 2–500; SMA/EMA 2–1000. Rules are limited to 20 comparisons and depth 5.
RSI defaults to period 14 when omitted; specify SMA/EMA periods. Use an explicit
market symbol such as `BTCUSDT`. AI mode defaults to 1h, 30 days, $10,000 initial
cash, and a 0.1% fee per side. Simple RSI requests default to buy below 30 and sell
above 70. The explicit-options CLI retains its 180-day default.

A moving-average level strategy:

```bash
poetry run strategy-backtest ai \
  'Backtest ETHUSDT on 4h for 90 days. Buy when SMA 20 > SMA 50. Sell when SMA 20 < SMA 50.'
```

`SMA 20 > SMA 50` is supported. `SMA 20 crosses above SMA 50` is a transition event
and is rejected. NOT, stop loss/take profit, short selling,
leverage, multiple symbols, live trading, and predictions are unsupported.

## AI Parsing and Deterministic Execution

```text
Plain English → OpenAI parser → Validated Strategy DSL
                                      ↓
Historical candles → Cached indicators → Rule Engine → Backtester → Results
```

AI extracts configuration only. It does not calculate prices, indicators, trading
signals, or financial results. Python validates the DSL and executes fixed rules;
no AI-generated code or arbitrary expressions are executed. Given the same validated
strategy and candles, the financial results are deterministic.

Rules use completed candle N and execute at **candle N+1 open**. Open positions
check exit rules; flat portfolios check entry rules. Unavailable indicator operands
make a comparison false. A final-candle signal cannot execute; any remaining
position is liquidated at the final close.

Rule strategies fetch prior candles for indicator warm-up: RSI `p+1`, SMA `p`, and
EMA `5p`, using the largest requirement. Warm-up candles are excluded from trading,
equity, and buy-and-hold results. Incomplete history or gaps cause an error rather
than a shortened evaluation period. EMA uses a finite approximation to historical
initialization; its seed can still affect signals near thresholds. Legacy RSI CLI,
demo, and simple AI RSI requests retain their original in-range initialization.
All boundaries use UTC and exclude unfinished candles.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the DSL schema, validation limits,
indicator initialization, execution accounting, metric definitions, and parser defaults.

## CLI and JSON

Run an RSI backtest with explicit options and no OpenAI key (Binance access required):

```bash
poetry run strategy-backtest \
  --symbol BTCUSDT --timeframe 1h --days 30 --balance 10000
```

Export an AI-parsed rule strategy:

```bash
poetry run strategy-backtest ai \
  'Backtest BTCUSDT. Buy when RSI < 30 and price > EMA 200. Sell when RSI > 70.' \
  --json > backtest.json
```

AI JSON includes `input`, `parsed_strategy`, and `backtest_result`, with metrics,
trades, indicator configuration, and evaluation-period metadata for rule strategies.
Explicit CLI JSON contains results and configuration directly. JSON stdout contains
no progress messages; errors go to stderr with exit code 2. Undefined metrics are
`null`. Credentials, prompts, and raw OpenAI responses are excluded.

For all CLI options and a network-free JSON example:

```bash
poetry run strategy-backtest --help
poetry run strategy-backtest ai --help
poetry run strategy-backtest --demo --days 30 --json
```

## Limitations

Backtests assume full fills, fractional quantities, and unlimited liquidity. They
model constant spread/slippage only when configured, and exclude funding, taxes,
and exchange lot-size constraints.
Drawdown samples candle opens and closes, not intrabar highs and lows. Binance data
availability depends on history, network access, rate limits, and regional restrictions.
Legacy/direct candle runs can span missing intervals; the rule-history fetch rejects gaps.
The application does not place orders or connect to private trading endpoints.

## Evidence-grounded research reports

Generate a report from one existing v0.8/v0.9-compatible CLI JSON result (also
emitted by v1.0.0) without fetching prices or rerunning a backtest. Supported inputs: standard backtest (including the AI
wrapper), comparison, validation, sensitivity, cost scenarios and walk-forward.

```bash
poetry run strategy-backtest report --input examples/report-source.json --format markdown
poetry run strategy-backtest report --input examples/report-source.json --format json
poetry run strategy-backtest report --input examples/report-source.json --format markdown --output reports/research.md
poetry run strategy-backtest report --input examples/report-source.json --ai --format markdown
```

Deterministic mode needs no API key. See the [synthetic example report](examples/research-report.md).
Markdown shows unique readable rules, compact segment tables and short row references;
full evidence identifiers and source paths remain in JSON.
Output files must be new; existing files are never overwritten. JSON stdout is one
object. Exit 0 means a deterministic report was generated, including when optional
AI is unavailable or rejected; its status and stderr explain the fallback. Invalid
input or filesystem errors exit 2.

Optional AI uses the existing OpenAI configuration to select evidence-linked,
preapproved explanatory statements and research questions. It cannot supply new
financial prose or change metrics. This deliberately conservative mode does not
prove arbitrary language true. Interpretation status and model are recorded.

Identical input bytes and generator version produce identical deterministic
content, with no generated timestamp. Source/canonical-input/evidence hashes aid
reproducibility, but cannot authenticate market data or supplied results. Inputs
are bounded and validated; Markdown metadata is escaped. Safe output creation
requires POSIX filesystem support and rejects symlink directories and parent
traversal. Reports preserve Train/Test distinctions and historical limitations;
positive returns do not establish predictive value.

## Configuration templates

Create validated JSON without prompts, OpenAI credentials, or repository examples.
`--output` must name a new file; existing files/directories and symlink destinations
are rejected. Missing real parent directories are created. No overwrite flag exists.

```bash
strategy-backtest init --type backtest --output backtest-config.json
strategy-backtest --config backtest-config.json --days 180 --demo --json
strategy-backtest init --type compare --output comparison-config.json
strategy-backtest compare --config comparison-config.json --demo --json
strategy-backtest init --type validate --output validation-config.json
strategy-backtest validate --config validation-config.json --demo --json
strategy-backtest init --type walk-forward --output walk-forward-config.json
strategy-backtest walk-forward --config walk-forward-config.json --demo --json
```

In a Poetry checkout, prefix these commands with `poetry run`. All four examples
run offline on deterministic synthetic candles and do not imply profitability.
Backtest uses `BacktestConfig`; its duration remains the CLI `--days` option
(default 180), and legacy account/strategy flags cannot accompany `--config`.
Spread/slippage flags can override costs. Other templates use their existing
research models (30 days for compare/validate, 60 days for walk-forward).
They declare balance 10000, fee 0.001 per side, full spread 10 bps and slippage
5 bps per side. Walk-forward uses rolling 30-day Train/10-day Test windows,
10-day steps and independent portfolios. These are fixed examples, not optimization.
`--demo` uses the fixed 2024-07-01 UTC end with exact prior warm-up candles;
research configs must use that end or null. For real Binance history omit `--demo`
and choose an appropriate evaluation period; that requires network access.
Safe file publication requires POSIX directory operations, as report output does.

## Offline diagnostics

```bash
strategy-backtest doctor
strategy-backtest doctor --type compare --config comparison-config.json
```

In a Poetry checkout, prefix with `poetry run`. Config validation is optional and
requires both `--type` (the same four choices as `init`) and `--config`; no research
files are scanned or guessed. Doctor reports Python compatibility, installed and
checkout metadata separately, dotenv discovery/loading, key presence and optional
AI model state. Stale editable metadata is labeled rather than used as the source
version. It uses normal shell-over-dotenv precedence, including empty shell values,
and honors `PYTHON_DOTENV_DISABLED`. Key values and model overrides are never shown.

Exit **0** means the checked offline capabilities are available; missing `.env`,
missing/empty credentials or unavailable optional AI do not cause failure. Exit
**1** means a Python compatibility, dotenv parsing/loading, explicit configuration
or offline self-check error needs attention. Exit **2** means invalid arguments.
Diagnostics are read-only: the offline check imports code and generates a small
synthetic sample, without running research, checking market connectivity or making
requests. A key's presence does not prove validity, funding or authorization; a
model setting does not prove provider availability. Validation confirms only the
selected configuration schema, not data availability, execution or profitability.

## Development

```bash
poetry run pytest
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy
```

Tests use mocked provider and OpenAI responses and require no API keys or network.
See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidance.

## Financial Disclaimer

This is educational/research software, not financial advice. Historical backtests do
not predict future profitability. Natural-language parsing does not make this a
trading recommendation system. Do not use simulated results as the sole basis for
investment decisions.

## License

[MIT](LICENSE).
