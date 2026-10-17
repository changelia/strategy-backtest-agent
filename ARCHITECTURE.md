# Strategy rule architecture

The existing `BacktestConfig`, candle/trade models, indicators, execution accounting, and
metrics remain the core. The rule engine adds no dependencies.

```text
Natural language → ai/parser.py → AIStrategyConfig (RSI or RuleStrategy)
                                 ↓
                    rules/history.py: fetch prior + requested UTC history
                                 ↓
                    rules/evaluator.py: unique indicator cache
                                 ↓
                    backtester.py: evaluate the previous completed candle
                                 ↓
                    existing next-open execution, fees, equity and metrics
                                 ↓
                    cli.py: deterministic summary or JSON
```

## Validation and indicator preparation

`rules/models.py` defines price, finite value and indicator operands, comparisons, and recursive
boolean groups. Literal tags close the language; extra fields are forbidden. Tree validation
limits depth to 5 and total comparisons to 20. Typed unions produce `anyOf` with recursive
references in the API schema; the SDK makes all fields required. This uses the documented
recursive schema support in [OpenAI Structured
Outputs](https://developers.openai.com/api/docs/guides/structured-outputs). The parser
revalidates returned data even if an injected SDK model bypassed construction validation.
Unsupported concepts and transition events are rejected rather than simplified.

`prepare_indicators` collects unique dependencies across both rules and builds each series once.
Evaluation resolves values at a single historical index. Every comparison first checks
finiteness. AND/OR recursively combine comparisons, without negation. The evaluator has no
provider, SDK, CLI or financial accounting dependency.

## Execution and compatibility

`run_backtest` validates the supplied rule tree again and initializes a portfolio at
`evaluation_start`. It skips prior candles for execution/equity purposes while retaining prior
indicator values. At each subsequent open it checks the previous evaluation close, selecting
exit when holding and entry when flat. A final signal has no following open; existing final-
close liquidation remains. Fees, sizing, reconciliation, open/close equity marks, drawdown and
summaries use the original accounting implementation.

Legacy RSI settings become equivalent comparison rules for periods 2–500. Older period limits
outside the DSL keep the legacy signal function. Legacy paths retain in-range initialization to
preserve v0.2.0 outputs. Regression tests force the old signal path and compare all metrics and
trades against DSL execution on identical data.

The CLI's explicit rule path calls `fetch_rule_history` once. It extends the requested start by
the largest requirement: RSI p+1, SMA p, EMA 5p, MACD 10*(slow+signal),
Bollinger p or ATR 20p prior intervals. It checks continuous history,
adequate initialization and evaluation coverage. Binance's existing sequential 1000-row
pagination, 0.2-second pauses and fail-fast rate-limit behavior remain. Pre-range candles are
excluded from benchmark and equity and never generate signals. See the historical warm-up policy
below for UTC boundaries and seed convergence limits.

Python callers providing candles directly control initialization history and the boundary index.
The engine validates increasing timestamps but does not enforce the provider's continuous-
history policy for those callers, preserving existing behavior. No arbitrary expressions,
generated executable source, or dynamic code execution are used.

## Strategy DSL reference

Operands are completed candle close (`price`), finite numeric constants (`value`), and
`indicator` with legacy name `rsi`, `sma`, or `ema` and an integer period, or advanced
MACD/Bollinger/ATR definitions described in [Advanced indicator conventions](#advanced-indicator-conventions).
RSI periods are 2–500;
SMA/EMA periods are 2–1000. Comparisons are `<`, `<=`, `>`, and `>=`, including indicator-to-
indicator comparisons. `and`/`or` groups have at least one child and can nest. A strategy has at
most 20 comparisons across entry and exit and depth at most 5, counting each root as depth 1.
Unknown fields, types, operators, nonfinite numbers and unsupported features fail validation in
Python.

Example internal DSL (serializable with `RuleStrategy.model_dump_json()`):

```json
{
  "type": "rules",
  "entry": {
    "type": "and",
    "conditions": [
      {
        "type": "comparison",
        "left": {
          "type": "indicator",
          "name": "rsi",
          "period": 14
        },
        "operator": "<",
        "right": {
          "type": "value",
          "value": 30
        }
      },
      {
        "type": "comparison",
        "left": {
          "type": "price"
        },
        "operator": ">",
        "right": {
          "type": "indicator",
          "name": "ema",
          "period": 200
        }
      }
    ]
  },
  "exit": {
    "type": "comparison",
    "left": {
      "type": "indicator",
      "name": "rsi",
      "period": 14
    },
    "operator": ">",
    "right": {
      "type": "value",
      "value": 70
    }
  }
}
```

Python callers can validate dictionaries using `RuleStrategy.model_validate` and call
`run_backtest(candles, config, strategy, evaluation_start=prior_candle_count)`.
`evaluation_start` indexes the first evaluation candle in the combined history. Fetching prior
history is the caller's responsibility outside the CLI. Unique `(name, period)` dependencies are
calculated once per run using the existing indicator functions. No HTTP or AI calls occur during
rule evaluation. An unavailable or nonfinite operand makes its comparison false; OR can still
succeed through another valid comparison. NOT is unsupported. Open positions evaluate exit; flat
portfolios evaluate entry. At most one action executes at each next open.

`SMA 20 > SMA 50` is a level comparison. `SMA 20 crosses above SMA 50` is a transition and is
rejected. The parser uses the official Responses SDK with recursive typed Structured Outputs,
then independently validates the entire tree in Python. It never produces or executes code.
Clearly parenthesized nested expressions are supported; ambiguity is rejected. RSI's omitted
period defaults to 14; SMA/EMA periods must be explicit. Legacy RSI extraction and its existing
defaults remain.

Terminal summaries use deterministic Python formatting with parentheses around boolean groups.
Rule JSON preserves `input`, `parsed_strategy`, and `backtest_result`. The result includes
`strategy`, unique `indicator_configuration`, `trading_fee`, and `evaluation_period` with
requested UTC start/end, actual prior candle count, required prior count and EMA policy.
Existing start/end and candle count fields refer only to evaluation candles. No progress
messages appear on JSON stdout.

## Historical warm-up policy

For explicit DSL strategies, take the maximum prior history requirement across all referenced
indicators:

| Indicator | Prior completed candles requested |
| --- | --- |
| RSI(p) | p + 1 |
| SMA(p) | p |
| EMA(p) | 5 × p |
| Only price/constants | 0 |

Fetch `[evaluation_start - requirement × interval, evaluation_end)` with the existing Binance
pagination, pauses, rate-limit handling and completed-candle filtering. Evaluation start remains
exactly the requested number of calendar days before the current UTC end. As in legacy mode,
only fully contained candles are evaluated; interval alignment can exclude boundary partial
candles. Insufficient prior history, gaps, or missing evaluation coverage raise clear errors; no
values are fabricated and no requested days are removed to accommodate indicators.

Indicators use all fetched history, but pre-range candles generate no signals or executions and
contribute no equity samples or benchmark exposure. Initial cash is applied at the first
evaluation candle. The first eligible signal is that candle's close, executing at the following
candle open. Buy-and-hold starts at the first evaluation candle open. Final-close liquidation is
preserved.

EMA retains the existing first-close seed and smoothing factor `2/(p+1)`. Five spans reduce the
contribution of the initial seed difference by approximately `((p-1)/(p+1))^(5p)` (less than
about 0.000046), rather than making an exact infinite-history EMA. Absolute error still depends
on the seed difference, and tiny residual differences can change signals near thresholds. RSI
retains the existing Wilder SMA seed and recurrence; p+1 prior closes provide initialization,
not an infinite-history convergence guarantee. SMA uses its exact finite rolling window.

Legacy explicit CLI, demo and simple AI RSI requests preserve their original in-range
initialization, results and JSON fields. Supported legacy RSI periods internally translate into
DSL comparisons; period 1 and periods above 500 retain the historical signal path to preserve
the older API's broader limits. An explicit RSI-only DSL with prior history can intentionally
differ from legacy RSI because its seed is earlier. Equivalent DSL and legacy strategies on
identical candles and boundaries have the same trades and metrics, covered by regression tests.

All signals, trades and financial results are deterministic Python operations for a fixed
validated strategy and candle history. Natural-language extraction may vary; review its output.
Backtesting does not predict future profitability.

## Parser defaults and API boundaries

The official OpenAI Python SDK uses Responses `responses.parse` with a Pydantic extraction
schema. Omitted envelope and legacy RSI values are returned as null; Python applies defaults
before strict validation. Rule operands have explicit values, including RSI period 14 when
omitted in the request. Portfolio settings map to `BacktestConfig`; the validated rule strategy
is passed separately to the backtester. Only the AI package imports the SDK. The parser has no
tools, market prices, or access to trading/brokerage accounts. It does not calculate
profitability or generate trading results.

| AI field | Default | Allowed values |
| --- | --- | --- |
| symbol | required | Explicit uppercase alphanumeric provider symbol, 5–20 characters |
| timeframe | 1h | Same intervals as the existing CLI |
| period_days | 30 | Integer, 1–365 |
| initial_balance | 10000 | Positive finite quote-currency cash |
| fee | 0.001 | Fraction per side, 0–0.05 (maximum 5%) |
| strategy.type | rsi | Legacy RSI or explicit `rules` |
| strategy.period (legacy RSI) | 14 | Integer, 2–200 |
| strategy.entry_below (legacy RSI) | 30 | Strictly between 0 and 100, below exit threshold |
| strategy.exit_above (legacy RSI) | 70 | Strictly between 0 and 100, above entry threshold |

AI's default range is 30 days; the original explicit-options CLI keeps its 180-day default. `RSI
25/75` means buy strictly below 25 and sell strictly above 75. A stated fee of `0.1%` means
`0.001`. Missing symbol/quote currency is not guessed: write `BTCUSDT`, not just `Bitcoin`.
Explicit invalid values are not replaced with defaults.

Unsupported requests fail rather than silently becoming RSI: short
selling, leverage, stop loss, take profit, crossover/crossunder events, NOT, portfolios/multiple
symbols, live trading, and price predictions. Contradictory or ambiguous requests also fail. A
conservative early keyword check rejects explicit unsupported concepts (including negated
mentions); structured AI rejection handles remaining semantics. Natural-language interpretation
can still be wrong even when schema validation succeeds; review the displayed configuration
before relying on results.

Terminal mode displays the input and parsed configuration before requesting historical data and
calculating results. `--json` prints one object with `input`, `parsed_strategy`, and
`backtest_result`; the result contains the same deterministic metrics/trades and market-data
metadata as the original JSON output. It never includes prompts or raw SDK responses. JSON-mode
errors go to stderr with exit code 2 and no result object. Missing/invalid keys, model access
errors, rate limits, timeouts, refusals, malformed output, validation errors, and market-data
failures produce concise errors. OpenAI requests have a 30-second timeout, no automatic retries,
and `store=False`.

Manual integration checks (not run by pytest or CI; require a real exported key):

```bash
poetry run strategy-backtest ai "Backtest BTCUSDT on 1h for 30 days. Buy when RSI is below 30 and sell when RSI is above 70."
poetry run strategy-backtest ai "Backtest ETHUSDT on 4h for 90 days using RSI 25/75" --json
poetry run strategy-backtest ai "Short BTCUSDT with 10x leverage using MACD"
```

The last command must exit with an unsupported-strategy error and never run a backtest. For a
parser-only manual check without market-data fetching:

```bash
poetry run python -c 'from strategy_backtest_agent.ai.parser import parse_strategy; print(parse_strategy("Backtest BTCUSDT").model_dump_json(indent=2))'
```

## Candle boundaries and accounting

For live runs the end is the current UTC time, and the start is exactly `--days` calendar days
earlier. Only candles whose open is in `[start, end)` and whose close time precedes end are
included. The current unfinished candle is excluded. Interval alignment can make coverage
slightly shorter than the requested days. For example, a 30-day hourly request at 12:30 excludes
the first partial hour (its open precedes start) and the current unfinished hour, leaving 719
completed candles. At an exact hour boundary, 720 may be returned. No valid fully contained hour
is dropped. Pagination continues beyond the provider's per-request maximum. Missing intervals
are not filled. Legacy RSI mode requests no extra pre-range history to preserve v0.2.0 results.
Explicit DSL strategies request prior history as described in the warm-up policy above.

Wilder RSI uses the first period's average gains/losses as its seed; its first value requires
period + 1 candles. Flat windows give 50, only gains 100, only losses 0. After the initial
simple averages, each Wilder average is updated as `(previous_average * (period - 1) +
current_gain_or_loss) / period`; RSI is `100 - 100 / (1 + average_gain / average_loss)`. SMA
requires period observations; EMA uses a first-value seed and hides the first period - 1
outputs. Indicator inputs must be finite.

A signal using completed candle N executes at **candle N+1 open**, for both entry and exit.
Legacy strict threshold equality means hold; DSL `<=` and `>=` include equality. A final-candle
signal cannot execute. One position uses all available cash, ignoring further buys while held
and sells while flat. Any remaining position is deliberately liquidated at the final close; this
is a simulation boundary, not an RSI signal. Trade timestamps identify candle opens, even for
the final liquidation; they are not exact intrabar fill times.

Entry quantity is `cash / (entry_price * (1 + fee))`. Exit proceeds are `quantity * exit_price *
(1 - fee)`. Net trade PnL subtracts the complete entry cost, including entry fee. Initial
balance plus all net trade PnLs equals final balance.

## Metrics

| Metric | Definition |
| --- | --- |
| Total return | `(final balance / initial balance - 1) * 100` |
| Buy & hold | Buy at first supplied candle open, hold to last close; includes both fees |
| Win rate | Positive net-PnL trades / all completed trades, as a percentage |
| Max drawdown | Largest peak-to-trough equity decline, as a nonpositive percentage |
| Profit factor | Sum of positive net PnL / absolute sum of negative net PnL |

Equity starts at initial cash and samples every candle open and close using `cash + quantity *
price`. Fees reduce equity when executed; hypothetical exit fees are not deducted from open
positions. Drawdown includes unrealized losses, but does not sample intrabar highs/lows. Legacy
mode includes its in-range RSI initialization in the benchmark. DSL mode excludes all pre-range
history from the benchmark and equity samples.

Break-even trades count as neither winners nor losers, but count in win rate's denominator. Thus
winners + losers can be less than total trades by the number of exactly zero-PnL trades; zero is
compared exactly, without rounding to displayed cents. Financial arithmetic uses floats;
reconciliation tests allow small rounding error. No trades gives null win rate and profit
factor. No losing trades gives null profit factor; losses without wins give zero. The engine
accepts empty history with unchanged cash and null benchmark; the CLI rejects insufficient RSI
history.

## Strategy comparison

The `comparison/` package contains validated models, an execution coordinator, a pure
formatter, and a CLI entry point. The engine imports neither OpenAI nor the AI package.
It reuses the existing DSL, indicators, backtester and metrics rather than creating a
second trading engine. The RSI model and strict base model now live in `models.py`;
`ai.models` re-exports them to preserve existing imports.

```text
Natural language → one OpenAI comparison parse → ComparisonConfig
                                                ↑
Validated JSON configuration ────────────────────┘
                                                ↓
                             one shared historical provider fetch
                                                ↓
                             one union of indicator dependencies
                                                ↓
                             sequential independent backtests
                                                ↓
                             excess return, ranking, CLI / JSON
```

### Configuration and public Python interfaces

See [examples/comparison.json](examples/comparison.json) for a complete configuration.
`ComparisonConfig` requires a symbol and 2–5 `NamedStrategy` entries. IDs must be unique,
1–64 ASCII letters/digits/hyphens/underscores, starting with a letter or digit. Names
must be nonempty, at most 80 characters, and contain no control characters. Strategies
reuse `RuleStrategy` or the existing legacy `RSIStrategy` (period 2–200). The DSL's
RSI period limit remains 500, SMA/EMA 1000, depth 5 and 20 comparisons per strategy.

Symbol, timeframe, period, capital and fee exist only at the comparison level;
per-strategy overrides are forbidden, including identical redundant overrides.
Defaults are 1h, 30 days, 10000 cash, fee 0.001, and `sort_by="total_return"`.
Days must be an integer in 1–365, cash positive and finite, and fee in 0–0.05.
`evaluation_end` accepts a timezone-aware ISO timestamp and is normalized to UTC.
Unknown fields and unsupported rule types fail validation.

```python
import asyncio
from pathlib import Path

from strategy_backtest_agent.comparison.engine import fetch_and_compare
from strategy_backtest_agent.comparison.models import ComparisonConfig
from strategy_backtest_agent.market_data import BinanceMarketData

config = ComparisonConfig.model_validate_json(
    Path("examples/comparison.json").read_text(encoding="utf-8")
)
result = asyncio.run(fetch_and_compare(BinanceMarketData(), config, data_source="binance"))
print(result.model_dump_json(indent=2))
```

For offline use, `run_comparison(candles, config, *, evaluation_end=None,
data_source="provided")` accepts a full candle sequence including initialization
history. No provider or OpenAI client is used. If neither config nor keyword supplies
an end, it derives one from the last candle's open plus the timeframe interval.
Conflicting configured and supplied end times are rejected. The direct comparison
path validates complete, continuous history just like the provider path.

### Shared history, initialization and indicators

All strategies, including legacy RSI entries, normalize to validated DSL rules before
comparison. Take the maximum warm-up requirement over every rule: RSI p+1, SMA p,
EMA 5p prior closes. Compute start as the resolved UTC end minus `period_days`, and
call the provider exactly once for `[start - maximum × interval, end)`.
One provider call can require multiple Binance HTTP pages; existing pagination,
0.2-second pauses and fail-fast rate-limit handling remain in effect.

The shared boundary indexes the first fully contained evaluation candle. Prior candles
never generate signals or trades and never enter equity samples or the buy-and-hold
benchmark. Each backtest starts with its own initial cash and no position at this
boundary. Its first possible execution follows the first evaluation candle's close.
Insufficient warm-up, gaps, unfinished candles, missing evaluation coverage and
out-of-range data are rejected. UTC and partial-boundary behavior match the historical
warm-up policy above.

`prepare_context` prepares the union of `(indicator name, period)` dependencies once.
Repeated RSI/EMA/SMA references across strategies share the same series; distinct
periods remain separate. The context is local to one comparison and is only read
while evaluating rules. There is no global cache and no per-candle network access.
`run_backtest` accepts an optional prepared `context`, checks its prices, dependency
keys and series lengths, and otherwise prepares indicators as before. The financial
accounting loop and formulas are unchanged. Sequential calls isolate portfolio state.

Comparisons deliberately differ from single-strategy legacy RSI initialization: every
comparison strategy uses prior history, including legacy entries. A legacy single run
still seeds inside its requested window. Adding a strategy with a longer warm-up can
move the shared seed earlier and change RSI/EMA signals even for unchanged strategies.
Reproduction therefore requires the full comparison configuration, not just one row.
EMA retains its finite first-close seed and five-span convergence approximation;
RSI retains the existing Wilder SMA seed and recurrence. Neither is an exact
infinite-history initialization.

### Metrics and ranking

Each `StrategyResult` contains ID, name, normalized DSL, the existing complete
`BacktestResult` including trades, and `excess_return_pp`:

```text
excess_return_pp = total_return_percent - buy_and_hold_return_percent
```

This is a percentage-point difference, not a relative growth ratio. The engine checks
that buy-and-hold is identical across all rows. Fees, full-cash sizing, next-open
execution, open/close equity marks, drawdown, reconciliation and final-close liquidation
use the existing backtester. Final-candle signals cannot create an execution.

`rank_results` sorts descending by exactly one selected criterion: `total_return`,
`excess_return`, `max_drawdown`, or `profit_factor`. For drawdown, -5% sorts ahead of
-10%. Undefined values sort after all defined values, even zero; null profit factor
never means infinity. Equal values sort by case-sensitive ID ascending. Results retain
configuration order; `ranking` lists IDs in ranked order. The formatter displays rows
in this ranking order. There is no composite score or automatically selected winner.

### Comparison parser and CLI boundary

`parse_comparison` makes one Responses `responses.parse` request for the entire
comparison, using the existing SDK boundary, unsupported-feature guard and sanitized
error handling. Its recursive Pydantic transport returns nullable global settings,
names and DSL rules, or a rejection. It must reject inconsistent per-strategy settings,
unsupported features, ambiguous expressions, and requests outside the 2–5 strategy
limit. Explicit invalid values remain invalid; Python supplies defaults only to
omitted fields. Python assigns `strategy-1`, `strategy-2`, etc. in request order.
Returned SDK objects are revalidated; unknown fields, including invented results or
per-strategy settings, are forbidden. Names and complete rules are validated again
in `ComparisonConfig` before any historical fetch.

RSI 25/70 shorthand uses RSI(14) <25 for entry and >70 for exit unless a different
period is explicit. SMA 20/50 shorthand means entry SMA(20) >SMA(50), exit <; EMA
shorthand follows the same level convention. Explicit crossover/crossunder requests
must be rejected. AI only extracts definitions; it cannot calculate or rank results.
Natural-language interpretation remains fallible; review the returned configuration.

```bash
poetry run strategy-backtest compare 'Compare RSI 25/70 and RSI 30/70 on BTCUSDT for 90 days'
poetry run strategy-backtest compare --config examples/comparison.json --json
poetry run strategy-backtest compare --config examples/comparison.json --sort profit_factor
```

The quoted request and `--config` are mutually exclusive. Config mode does not import
or call the parser and needs no OpenAI key. `--sort` overrides `sort_by` for either
path. Comparison stdout is a table or a single valid JSON document; failures use
stderr and exit code 2. JSON excludes original request text, system prompts, credentials
and raw SDK responses. Existing `ai`, explicit RSI options and `--demo` are unchanged.

### Reproducibility and JSON metadata

The JSON envelope contains:

| Field | Contents |
| --- | --- |
| `configuration` | Validated shared settings, original strategies, resolved UTC end, selected sort |
| `shared_data` | Source, exact requested UTC start/end, first/last evaluation opens, candle counts, warm-up, indicator union, history digest |
| `buy_and_hold_return_percent` | Common fee-adjusted evaluation-period benchmark |
| `results` | Per-strategy definitions, existing metrics/trades, excess return in pp |
| `ranking_criterion` | One selected historical metric |
| `ranking` | Ordered strategy IDs; no predicted winner |

When an asynchronous run omits `evaluation_end`, the engine reads UTC now once and
records that resolved value in both configuration and metadata. Fixed ends make the
requested window repeatable. Exact results require unchanged underlying candles;
Binance can revise historical data. Archive the candles, including warm-up, for exact
Python replay. `candles_sha256` hashes the full combined history in sequence as compact,
sorted-key JSON records, UTF-8 encoded with a newline after each record. Hashing is
streamed without constructing a duplicate dataset. A different digest detects changed
history; the digest does not itself contain or recover the candles.

The recorded source describes the provider supplied by the caller. Candle count,
first/last opens and benchmark exclude pre-range history; `history_candle_count` and
the digest include it. Metadata also records required and actual warm-up counts and
its finite initialization policy. Comparisons share the same simulation limitations as
single runs and cannot establish which strategy will be profitable in the future.

### Release metadata

At the v0.7.0 release, the tag and package version were aligned at 0.7.0.
Earlier tags may retain historical metadata mismatches; they are not modified.
The release follows the financial audit, quality gates and a fast-forward main merge.

## Chronological out-of-sample validation

`validation/models.py`, `engine.py`, `formatter.py` and `cli.py` add orchestration
around the v0.4.0 comparison infrastructure. `SharedConfig` factors out existing
shared trading assumptions, named DSL strategies and ID validation; `ComparisonConfig`
retains its 2–5 strategy limit and sort field. `ValidationConfig` allows 1–5 strategies,
has no ranking field and adds `train_ratio` (default 0.70, inclusive range 0.50–0.90).
All config fields are strict, finite and extra-forbidden. Strategies reuse the same
DSL or legacy RSI model; no new language or optimization parameters are introduced.

`prepare_shared_history` factors the comparison engine's existing UTC resolution,
maximum warm-up validation, normalized rules, unique indicator cache and streamed
SHA256 metadata into one reusable function. Comparison outputs and accounting remain
unchanged. Validation's engine imports no OpenAI modules. `fetch_and_validate` resolves
UTC now once (or uses fixed `evaluation_end`) and calls the same `fetch_history` once.
Binance may paginate that single shared fetch; there are no per-strategy or per-segment
fetches. Direct `run_validation(candles, config, *, evaluation_end=None,
data_source="provided")` supports offline replay, deriving an omitted end from the
last candle open plus its interval. Conflicting or naive end overrides are rejected.

### Exact split and execution policy

1. Validate the full history with the existing continuous, completed-candle and
   range-coverage rules. The requested start is end minus `period_days`; only fully
   contained completed candles belong to evaluation. Prior history is warm-up.
2. Let N be the count of evaluation candles and K = `floor(N * train_ratio)`
   using decimal ratio arithmetic to avoid binary-float undercount at integer boundaries.
   Train contains the first K evaluation candles; Test contains the remaining N−K.
   There is no randomization, overlap or discarded eligible evaluation candle.
   Reject if either count is less than two: a segment needs a completed signal candle
   and a following execution candle. Do not modify the ratio or shorten the window.
3. Record UTC half-open intervals: Train `[first Train open, first Test open)`;
   Test `[first Test open, last Test open + interval)`. Train's last candle precedes
   Test's first candle strictly. Requested start/end remain separately recorded in
   shared metadata; interval alignment can make actual evaluation boundaries differ.
4. Train's backtest receives only candles through its last candle and a correspondingly
   truncated cache. Its final close liquidates any position using only Train prices.
   A final Train entry or exit signal has no subsequent Train open and is discarded.
5. Test's backtest receives preceding history for indicator values, with
   `evaluation_start` at the first Test candle. `run_backtest` initializes cash to the
   configured amount with no position, cost, entry, trades or equity from Train.
   Signals preceding that index are ignored, including the last Train signal.
6. Test's first possible signal uses its first completed candle close; its first
   possible execution is at the second Test candle open. Its last signal cannot execute;
   any remaining position liquidates at its own final close. Buy-and-hold buys at each
   segment's first open and sells at its last close, charging both configured fees.

Forced liquidation trade timestamps retain the backtester's candle-open convention;
the segment's end records the actual completed interval boundary. A position can open
at a segment's last open and liquidate at that same candle's close.

### Indicator causality and portfolio isolation

The union of RSI/SMA/EMA dependencies is calculated once per full validation run,
using the existing indicators. These are causal series: SMA uses a trailing window,
EMA uses `adjust=False` first-close recursion, and Wilder RSI uses a prior SMA seed
and forward recurrence. The value at index i depends only on closes at indices ≤i.
Full-series preparation is safe because future values cannot alter earlier prefixes.
Train execution receives only its prefix, including truncated price and indicator
arrays; it cannot index Test values. Tests compare full cached prefixes against
independently prepared Train-only indicators and change all Test prices to verify
unchanged Train results. No centered windows, future shifts or future-informed seeds
are used. Adding new indicators requires equivalent causality tests.

Test indicators retain all preceding Train and pre-Train closes for initialization,
without recalculation or resetting the indicator seed. This history is excluded from
Test equity, trade state and benchmark. Each sequential backtest call uses fresh local
portfolio state; identical strategies also receive independent portfolios. Existing
accounting, fees, open/close equity, drawdown and trade metrics are reused unchanged.

Warm-up rules remain RSI p+1, SMA p, EMA 5p, taking the maximum across all strategies.
Adding a longer-history strategy can move RSI/EMA seeds and change signals. Finite
EMA and RSI initialization is not exact infinite-history initialization. Two candles
per segment is an execution minimum, not statistical evidence of adequate sample size.

### Results, parsing and interpretation

`ChronologicalSplit` records ratio, UTC intervals, candle counts and rounding policy.
`SegmentResult` records its interval, count, preceding history count, complete existing
`BacktestResult` and `excess_return_pp`. `StrategyValidationResult` contains the normalized
DSL and independent Train/Test results, with:

```text
return_gap_pp = test.total_return_percent - train.total_return_percent
```

`ValidationReport` contains configuration, shared metadata, split, ordered strategy
results and methodology warnings. No strategy is ranked or automatically selected.
The formatter labels Test **Held-out evaluation** and displays initial/final cash,
returns, fee-adjusted buy-and-hold, excess return, drawdown, trades, win rate and profit
factor for both segments. Null win rate means no trades; null profit factor means no
losing trades (including zero trades), not infinity. Return gaps compare different
segment lengths without duration normalization and are descriptive only.

`parse_validation` reuses the existing structured Responses parsing boundary in one
request for all strategies and settings. Nullable extraction fields distinguish omitted
values from explicit invalid values; Python defaults and validates, assigns stable IDs,
and revalidates SDK output. The prompt restricts output to configuration or rejection.
Deterministic guards reject explicit optimization, tuning, randomization, walk-forward,
folds and selection requests; structured rejection handles unsupported semantics,
inconsistent settings, ambiguous grouping/splits and missing symbols. No trades, prices,
performance, predicted profitability or executable Python are accepted in the schema.
Natural-language interpretation can still be wrong; review and freeze the parsed DSL.

The config path never imports the AI parser and needs no OpenAI credentials. CLI
sources are mutually exclusive, errors use stderr and exit code 2, and `--json`
emits exactly one JSON object without prompts, keys, raw SDK responses or progress.

```bash
poetry run strategy-backtest validate \
  'Validate RSI 30/70 and SMA 20/50 on BTCUSDT over 180 days using a 70/30 train/test split'
poetry run strategy-backtest validate --config examples/validation.json --json
poetry run strategy-backtest validate --help
```

### Reproducibility and limitations

Resolved requested UTC boundaries, actual segment intervals, all strategy definitions,
shared warm-up, indicator union and full-history SHA256 are recorded. Hash encoding
matches comparison: compact sorted-key JSON candle records with newline separators,
including warm-up. Fixed `evaluation_end` plus archived identical candles reproduce
results; a hash detects revisions but cannot recover prices. Binance history may change.

Holdout validity depends on selecting and freezing rules before inspecting Test.
Selecting among these strategies using Test results, repeatedly modifying rules after
viewing Test, or relying on previously inspected historical prices contaminates the
holdout. The software cannot prove the user's data was unseen. A single chronological
split cannot establish robustness across regimes or guaranteed future profitability.
No parameter optimization, walk-forward, cross-validation, normalized-return scoring
or robustness score is included. Future walk-forward validation should preserve the
same causal boundary and portfolio isolation rules. Existing full-fill, liquidity,
slippage, spread, intrabar drawdown and exchange-constraint limitations remain.


## Deterministic parameter sensitivity

The `sensitivity/` package adds strict models, grid expansion, descriptive statistics,
a Train-only coordinator, formatter and CLI. It imports no AI modules. Existing DSL
models, RSI/SMA/EMA functions, backtester, metrics and market provider remain the core.
There are no new indicators, operators, accounting formulas or optimizer.

### Shared infrastructure and evaluation policy

`MarketConfig` factors the v0.4.0 market assumptions out of `SharedConfig`; comparison
and validation retain their original strategy-count limits and fields. Sensitivity
adds `base_strategy` (a `RuleStrategy`), `parameters`, and `train_ratio` (0.50–0.90,
default 0.70). Existing defaults are 1h, 30 days, cash 10000 and fee 0.001. All new
configuration fields use strict, extra-forbidden, finite Pydantic validation.

`comparison.engine.prepare_history` validates the existing complete historical window,
resolves UTC boundaries, records unique dependencies and streams the same full-history
SHA256 without computing indicators. Existing `prepare_shared_history` delegates to it
and prepares the original full causal cache for comparison and validation. Their result
schemas and execution behavior remain unchanged. `validation.engine.chronological_split`
factors the existing v0.5.0 split policy into a shared function: decimal floor of N×ratio,
no overlap or omissions, at least two completed candles in each segment, UTC half-open
boundaries. Sensitivity reserves the Test segment but never evaluates variants there.

`fetch_and_analyze` fully validates and expands the bounded grid before any provider
call. It requests history once, using the maximum warm-up over all generated variants:
RSI p+1, SMA p, EMA 5p. The same Binance pagination and complete-history validation
apply. Each generated strategy runs with identical market settings and Train boundaries.
Base indicator references left unchanged in a variant still count toward its warm-up.

`run_sensitivity` truncates history at the split **before** calling
`sensitivity.cache.prepare_train_context`. Each unique `(indicator name, period)` uses
only its own existing warm-up requirement immediately before first Train open. That
requirement is reused through `rules.evaluator.indicator_warmup`, also used by
`warmup_count`; indicator formulas are unchanged. `prepare_context` computes each
series once from its anchored suffix. NaNs pad the unused earlier prefix to align the
series with the common candle indices. This prefix is never evaluated. Unique keys
prevent period collisions and adding a longer grid period cannot move another key's
seed. Shared metadata records sorted `indicator_initializations` (indicator definition,
prior candle count, UTC history start) and the sensitivity-specific `warmup_policy`.
The maximum fetched warm-up count remains separately recorded. Indicator
functions and backtests receive only prior history plus Train. Their first execution
follows the first completed Train signal candle; final Train signals cannot execute
on Test. Remaining positions liquidate at the final Train close. Every variant calls
`run_backtest` independently with configured cash, no position and fresh equity/trades.
Warm-up is excluded from benchmark and accounting. RSI, SMA and EMA remain causal;
non-flat prefix-invariance tests guard the prepared cache across periods.

Test timestamps determine its reserved interval and count. Test candle values are read
only for shared history integrity/hashing, never for grid construction, indicators,
portfolio evaluation, statistics, local observations or selection. Altering Test values
changes the full-history digest but leaves Train metrics and all sensitivity statistics
unchanged. There is no Test result, ranking, winner or recommended strategy in this report.

### Structural parameter paths and explicit coupling

Supported path grammar:

```text
(entry|exit)(.conditions.<zero-based index>)*.(left|right).(period|value)
```

A `period` field must target an RSI/SMA/EMA operand. A `value` field must target a
constant compared with price or an indicator. Constant-to-constant rules cannot be
varied. Names, operators, prices and boolean structure are immutable. Group indices
must be canonical ASCII integers (no negative indices, leading zeros or wildcards).
Ambiguous selectors are rejected; parameter identification never matches numeric values.

Repeated indicator references are independent by default. To vary a shared SMA fast
period in both entry and exit, declare:

```json
{
  "path": "entry.left.period",
  "coupled_paths": ["exit.left.period"],
  "values": [10, 15, 20]
}
```

Coupled indicator paths must have the same base indicator name and period. Coupled
constants must have the same base value and compatible kinds; an RSI threshold cannot
be coupled to a generic constant. Coupling is confined to explicitly named paths; no
unrelated node changes. Paths must be unique across all primary and coupled references.
A deep serialized copy of the base DSL is mutated per combination and fully revalidated;
the original strategy stays unchanged. Existing depth 5 and 20-comparison limits apply.

RSI candidate thresholds are finite numbers in inclusive 0–100, including reversed
constant-versus-RSI comparisons. Period candidates must be integers (explicit float
periods are rejected), RSI 2–500, SMA/EMA 2–1000. The conventional simple DSL form
`entry RSI(p) < a; exit RSI(p) > b` also retains `a < b` ordering, including inclusive
operators. Compound rules or different indicator periods keep their explicit DSL
semantics; there is no inferred ordering constraint across unrelated constants or SMA
fast/slow periods. Those configurations can be valid DSL while economically unusual.

### Grid specifications and stable ordering

Each `ParameterSpec` uses exactly one source:

```json
{"path": "entry.right.value", "values": [25, 30, 35]}
{"path": "entry.left.period", "range": {"start": 10, "stop": 20, "step": 5}}
{"path": "entry.right.value", "nearby": {"step": 5, "steps": 1}}
```

These are separate specifications, not one JSON file. `values` is nonempty and contains
no numerical duplicates (30 and 30.0 are duplicates). `range` is inclusive, ascending,
with a positive step; stop must be reached exactly. Expansion uses decimal arithmetic
to avoid float accumulation. Indicator ranges require integral bounds and steps.
Nearby generates `base + step × offset` for offsets `−steps..steps`, including base.
`steps` defaults to 1, maximum 12. Omitted step defaults to 5 for RSI thresholds and 1
for indicator periods. Other constants require an explicit step. No values are clipped
at boundaries; e.g. nearby period 2 generates invalid period 1 and fails with a clear
error. Rounded duplicate/nonfinite generated values are rejected.

There are 1–3 dimensions and at most 25 Cartesian variants. Dimensions retain config
order, explicit candidates retain declared order, ranges/nearby are ascending. The last
dimension varies fastest. IDs are `variant-001`, `variant-002`, etc. in that order;
coordinates and primary-path values are recorded. Coupled paths share their dimension's
candidate value and do not multiply grid size. Invalid combinations reject the entire
grid with parameter values and validation details; nothing is silently discarded. A
three-dimension nearby grid with three values each exceeds 25 and must be narrowed.

Examples: [RSI thresholds](examples/sensitivity.json),
[SMA fast/slow periods](examples/sensitivity-sma.json),
[EMA nearby periods](examples/sensitivity-ema.json). The base strategy is metadata;
explicit candidate sets need not include its current values. Nearby always includes it.

### Descriptive metrics, adjacency and observations

Each `VariantResult` contains the existing `SegmentResult` and full `BacktestResult`,
including fees, benchmark, trade records, total return, excess return in pp, drawdown,
win rate and profit factor. Zero trades retain cash, null win rate and null profit
factor. No losses means null profit factor, not infinity; losses without wins give zero.

The summary reports min/median/max total return, max−min in pp, percentage of variants
with return strictly >0, and percentage with excess return strictly >0. If benchmark
is undefined, its outperformance percentage is null. Zero/low-trade variants remain
in the descriptive statistics and are explicitly listed as insufficient for observations.
These statistics describe the evaluated grid only; durations are identical across variants.

Two variants are neighbors when exactly one coordinate differs by one index in the
**declared candidate order**; all other coordinates match. Unsorted explicit values
therefore define a different neighborhood than numerically sorted values. Report every
edge once with signed `second return − first return`, its parameter path, and trade
sufficiency. Do not rank variants. One dimension produces an ordered series; two produce
a matrix with first parameter as rows and second as columns, plus IDs and trade counts
for each cell. Three dimensions still produce edges and tables, with no flattened matrix.

Local observations use documented descriptive conventions: at least five trades for a
configuration and every neighbor; a 5 pp absolute similarity tolerance. These constants
are included in the summary. A qualifying configuration within 5 pp of every neighbor
is `similar_to_all_neighbors`; this describes its local neighborhood, not an entire
stable region. A configuration exceeding every neighbor by >5 pp with at least two
neighbors is an `isolated_positive_spike`. Others are `mixed_neighbors`, `no_neighbors`,
`insufficient_neighbor_trades`, or `insufficient_trades`. Few or zero trades can never
receive a similarity/spike label. Matrix cells with insufficient trades carry `*` in
terminal output. These labels are transparent heuristics, not significance claims,
robustness scores, recommendations or proof of future profitability.

### CLI, structured parsing and JSON

```bash
poetry run strategy-backtest sensitivity \
  'Analyze nearby RSI 30/70 thresholds on BTCUSDT over 180 days'
poetry run strategy-backtest sensitivity --config examples/sensitivity.json
poetry run strategy-backtest sensitivity --config examples/sensitivity-sma.json --json
poetry run strategy-backtest sensitivity --config examples/sensitivity-ema.json
```

Config mode never imports the AI parser and needs no OpenAI key. AI mode makes one
existing Responses structured-output request for nullable globals, validated base DSL
and parameter specs or rejection. Python handles defaults, bounded expansion and all
financial calculations. Explicit unsupported strategies, optimization, randomization,
selection and Test-evaluation requests are rejected; structured rejection also handles
ambiguous paths, conflicts and unsupported semantics. SDK objects are revalidated and
an explicit symbol must be present in the request. Names/paths and parsed rules still
require review because natural-language interpretation can be wrong.

JSON emits one object, with stable ordered lists, finite values or null, containing
`configuration`, `shared_data`, `split`, expanded `parameters`, full `variants`,
`results`, `summary`, `neighbors`, `ordered_series`, `matrix`, `execution_assumptions`,
and `methodology_warnings`. There is no progress on stdout. Errors use stderr and
exit code 2; no credentials, prompts or raw SDK responses are exposed.

### Research limitations and reproducibility

Sensitivity explores a declared grid; it does not automatically optimize or select
parameters. Repeated experimentation can overfit Train, and an isolated spike may be
fragile or sampling noise. Local similarity is not statistical stability. Freeze a
preselected configuration before a separate explicit `validate` workflow; sensitivity
never evaluates variants on Test. `validate` currently requires a full configuration
and recomputes its own shared warm-up, so a later run with a different strategy set or
maximum period may have a different indicator seed. Preserve archived initialization
history when exact replay matters. The application cannot prove data was never inspected.

Fixed UTC ends, complete strategy/grid definitions, split intervals, counts and full
warm-up/history SHA256 make runs auditable. Exact reproduction requires identical
candles and configuration; hashes do not recover data. Longer-period grid additions
can change the requested history and digest, but cannot change existing indicator
values or variant trades/metrics at fixed Train boundaries. Summary distributions and
neighbor labels naturally change when variants/neighbors are added; those describe
the new grid. Finite RSI/EMA seeds still depend on the prices inside each recorded
initialization window. EMA uses its existing first-close seed; RSI uses its existing
Wilder seed. This is deterministic finite initialization, not exact infinite-history
convergence. Comparison and validation retain their prior shared-seed semantics, so
cross-command results can differ for strategies with multiple indicator periods.
Provider revisions, full-fill assumptions, fixed modeled spread/slippage,
unlimited liquidity, floating financial arithmetic and open/close-only drawdown remain
limitations. Stop loss, take profit, leverage, shorts, crossover operators,
multi-symbol analysis, automatic optimization, walk-forward and profitability predictions
remain unsupported. Parameter sensitivity is included in release v0.6.0.


### Final financial audit: grid stability

The pre-audit sensitivity cache seeded every indicator from the earliest candle fetched
for the entire grid. Increasing the grid's maximum RSI/EMA period extended prior history
and moved the existing short-period seed. This did not use Test data, but it changed
fixed variants' entry timing and return solely because another variant was added.
That is a comparison/reproducibility defect: the grid changed both the parameter set
and an unreported recursive initialization input.

Regression fixtures use one unchanged timestamped price archive, a fixed 12-candle Train
window and a fixed end. Compare period 2 alone with the grid [2, 6]. The provider filters
that same archive to each requested historical range. Train/pre-Train overlapping candles
are identical; no prices are revised. RSI's prior count extends from 3 to 7, EMA's from
10 to 30. The EMA fixture includes extreme older prices to expose residual seed error.
Both strategies enter below a fixed threshold (RSI 36.4 / EMA 104), use initial cash 1000
and fee 0.01, and force-close at final Train close 160.

| Original period-2 variant | Old first Train value alone | Old first value in larger grid | Old Train return alone / larger grid | Fixed Train return in both grids |
| --- | --- | --- | --- | --- |
| RSI | 33.333333 | 39.487179 | 42.574257% / 30.693069% | 42.574257% |
| EMA | 100.895832 | 107.072143 | 42.574257% / 30.693069% | 42.574257% |

Old entry timing shifted from 2024-01-01 01:00 UTC (open 110) to 03:00 UTC (open 120).
The fixed original variant enters at 01:00 in both grids. Its final cash is
`1000 / (110 * 1.01) * 160 * 0.99`. No indicator formulas, trade accounting or legacy
command initialization policies changed. Sensitivity results for grids with different
periods can change from pre-audit outputs; the report's policy and anchor metadata make
that correction explicit. The 12 top-level JSON sections and all input fields remain;
`shared_data.indicator_initializations` is additive metadata. Existing archived reports
are not rewritten.

`tests/test_sensitivity_audit.py` covers these recursive witnesses, individually anchored
cache oracles, prefix causality, mixed RSI/EMA keys, initialization-window revisions and
missing-history rejection. A separate parameterized test replaces **every** Test candle's
OHLCV while preserving all earlier candles. It instruments indicator inputs, rule indices,
backtest calls, closed trades and equity samples; all Train computations, variant definitions,
summary/neighbor observations and matrix data remain identical. Only the full-history
SHA256 differs. JSON/CLI and the pre-v0.6.0 regression suites continue to guard compatibility.

## Deterministic execution costs (v0.7.0)

Introduced in v0.7.0, `models.ExecutionConfig`
and `execution.quote_execution` provide one strict execution implementation for all
engines. Strategy rules, indicators, next-open timing and initialization formulas
are unchanged. Legacy configs containing only `fee` remain valid; nested
`execution.fee_rate` inherits that alias when omitted. Explicit conflicting aliases
fail validation. An explicit nested rate must also satisfy the enclosing model's
historical fee limits (research MarketConfig retains its 5% cap).

For reference P, define a = (spread_bps / 2 + slippage_bps) / 10000.
Buy fill is P × (1+a); sell fill is P × (1−a). Spread is FULL bid/ask
spread; slippage is adverse PER SIDE. All inputs must be finite and nonnegative,
fee_rate < 1, and half-spread + slippage < 10000 bps. Computed fills must be
finite and positive; overflow/underflow is rejected rather than clipped.

OHLC prices serve as mid-price proxies; historical Binance OHLCV does not reveal
bid/ask quotes. A modeled fill may be outside the candle's high/low. This is a
constant-cost research assumption, not reconstruction of actual fills or liquidity.

### Accounting, marking and benchmark

With available cash C and fee f, entry quantity is C / (buy_fill × (1+f)).
Entry fee is quantity × buy_fill × f; remaining cash is zero, without leverage.
Exit cash is quantity × sell_fill × (1−f); exit fee is quantity × sell_fill × f.
Trade PnL is exit cash minus cash allocated at entry, including both fees and
adjusted fills. Win rate and profit factor use this actual net PnL. Signals from
completed N execute at N+1 OPEN; forced liquidation instead uses the segment's
final CLOSE and applies one sell adjustment. Positions/signals never cross a split.

For example, C=1000, reference buy=100, sell=110, full spread=20 bps,
slippage=10 bps, f=0.001: fills are 100.20 and 109.78,
quantity=1000/(100.20×1.001), and final cash=quantity×109.78×0.999.
Financial arithmetic remains binary floating point; oracle tests use independent
Decimal arithmetic with explicit tolerances.

Equity retains the historical reference-price policy: cash + quantity × candle
open/close. No hypothetical liquidation fees or repeated spread/slippage deductions
are applied to marks. Executed exits and final-close liquidation replace the mark
with actual cash, so final equity reconciles to final balance. Drawdown samples
opens/closes and cannot capture intrabar extremes. Nonfinite marks are rejected.

Buy & Hold remains first evaluation OPEN to final CLOSE, using identical buy/sell
costs and its own entry quantity. Its net return retains the exact original operation
order when spread/slippage are zero. Its attribution is reported separately under
`benchmark_costs`; it never enters strategy cost totals. Historical in-range legacy
RSI initialization still counts toward its benchmark window, as before.

Trade fields retain their names; entry_price/exit_price are actual fills. Additive
entry_execution/exit_execution record reference, fill, quantity, fee, per-unit spread
and slippage adjustment, modeled monetary amounts, and forced liquidation.
Result costs sum actual fills using each trade's quantity, including compounded
quantity changes between trades. Charged fees are cash deductions; modeled spread
and slippage are attribution relative to reference, not separately observed charges.
They are already included through fills and must not be deducted a second time.
Their sum is not generally the return loss versus baseline: changed sizing and fees
also affect the counterfactual. Zero-trade portfolios have zero charged/model costs.

### Shared research engines and cost scenarios

Comparison applies one execution configuration to all strategies. Validation applies
it to fresh Train/Test portfolios. Sensitivity retains its v0.6.0 indicator-local
RSI/EMA anchored seeds and evaluates variants on Train only. Costs do not enter DSL
signals or indicator cache keys, which remain (indicator name, period).

The config-only `costs` command is separate because scenario-specific assumptions
must be declared explicitly rather than mixed with strategy parameter grids.
`costs.models.CostScenarioConfig` reuses MarketConfig and one frozen RuleStrategy,
with 2–8 unique ordered scenario IDs. First scenario must have zero spread/slippage.
A scenario may explicitly vary fee_rate (<1); otherwise the shared fee is inherited.
Shared nonzero spread/slippage is rejected to avoid ambiguous scenario overrides.
There is no parameter grid, sorting, optimization, winner or recommendation.

`costs.engine` reuses comparison history preparation, v0.5.0 chronological split,
v0.6.0 prepare_train_context, and the existing backtester. One fetch includes the
strategy's maximum warm-up; each unique indicator is initialized once using its
anchored prior window. Data is truncated at Train end before preparing indicators
or running independent portfolios. No Test strategy evaluation occurs. Test values
affect only integrity validation and the complete-history SHA256, not Train results
or baseline differences. Default split is 70/30; existing sufficient-history checks
apply. The full-history hash and fixed UTC boundaries preserve auditability.

Scenario JSON records config, history digest/anchors, split, baseline ID, all resolved
scenario assumptions and Train results with cost totals and return differences in
percentage points. Output order follows declared order. Undefined metrics are null;
nonfinite outputs fail validation. CLI JSON stdout contains one object and errors use
stderr. All original commands accept --spread-bps / --slippage-bps; explicit flags
override parsed/config values while preserving the effective fee. AI extracts only
explicit supplied costs, defaults omitted costs to zero, and is prevented from
inventing spread/slippage assumptions. Python alone computes fills and economics.

See `examples/execution-scenarios.json`. Scenario magnitudes are illustrative, not
measured exchange costs. Constant costs omit time variation, market impact,
order-book dynamics, partial fills, liquidity limits, funding, taxes and exchange
quantity constraints. Finite RSI/EMA initialization and historical differences
between command warm-up policies remain documented limitations.


## Fixed-strategy walk-forward analysis

`walk_forward` reuses the validated DSL, shared history validation, v0.6.0
indicator-local cache and v0.7.0 `run_backtest` accounting. It introduces no second
financial engine. Introduced in v0.8.0 — Walk-Forward Analysis.

`WalkForwardConfig` extends shared market settings with `windows` (`mode`,
`train_days`, `test_days`, optional `step_days`, `max_folds`) and `stitch_oos`.
All models forbid extra fields and nonfinite numbers. Durations are positive whole
days and must divide exactly into timeframe candle counts. Each segment needs at
least two completed candles. Strategy IDs are unique; 1–5 strategies share costs.
AI uses the existing Responses structured parser to extract fixed rules and protocol
only; deterministic Python validates everything and generates folds. Config-only
execution does not import or invoke the AI parser.

Given evaluation boundary B, Train size T, Test size U and step S, fold k uses
Train `[B+kS, B+kS+T)` in rolling mode, or `[B, B+kS+T)` in expanding mode;
Test is always `[B+kS+T, B+kS+T+U)`. Indices count candles, never calendar offsets.
The first eligible completed evaluation candle anchors B. UTC boundaries are
half-open candle intervals; the final end is last candle open plus timeframe.
Only complete folds are used, and at least two are required. S >= U prevents Test
overlap. Train may overlap previous Tests; fixed strategies cannot adapt to those
results. S > U produces explicitly visible Test gaps. Default maximum is 50 folds,
hard maximum 100; exceeding the configured limit is an error, never silent truncation.
Unused trailing count is total evaluation candles minus the final Test end index.
Evaluation range coverage, missing candles and unfinished candles follow existing
shared-history validation. A fixed evaluation_end and identical candles reproduce
results; the SHA256 includes all warm-up and evaluation candles.

One provider fetch includes the largest dependency warm-up. For each distinct
indicator, `prepare_train_context` anchors its own history start at B minus its
required warm-up (RSI p+1, SMA p, EMA 5p). Values then continue causally through
all folds; neither rolling segments nor Tests reseed indicators. Dependencies are
computed once, even when repeated in several strategies. The report records each
indicator, required prior count and exact history start. This adopts v0.6.0's
strategy/grid-independent initialization instead of v0.5.0 validation's common
full-history seed: adding a longer-period strategy cannot move shorter-period
RSI/EMA seeds. Differences from standalone validation are possible and deliberate.
Adding later folds with the same evaluation start cannot move existing seeds.
Changing the evaluation start changes the declared initialization protocol.

Every backtest receives only the prefix ending at its segment end, a correspondingly
truncated cache, and its evaluation_start. Each call resets cash, quantity, trades,
equity and realized PnL. Each expanding Train remains one continuous segment internally; intermediate days and earlier fold boundaries do not reset its portfolio or force liquidation. Only its own final close does. Independent Test backtests still reset. Prior history initializes indicators only; the first signal
is the first completed segment candle and executes at the next segment open.
The last signal cannot cross the boundary; positions liquidate at final segment
close. Train positions, capital and signals never carry to Test or another fold.
Fee per side, full spread (half on each side) and adverse slippage per side are
identical everywhere, including net first-open/final-close Buy & Hold. Existing
`SegmentResult` and `BacktestResult` preserve PnL, trade metrics and cost breakdowns.

Aggregates are Test-only, per strategy in configuration order. Completed trades are
summed. Positive count/fraction uses strictly positive net return, fraction in [0,1].
Return median/min/max use unweighted independent fold returns; drawdown median is
the median of individual fold drawdowns, not a continuous-portfolio statistic.
Excess median uses strategy return minus net benchmark in percentage points;
outperforming count uses strictly positive excess. Undefined benchmark excess is
null and excluded from its median/count. Zero-trade returns remain in aggregates;
undefined win rate/profit factor remain null. Neither is averaged or pooled.

Optional stitched OOS output is deliberately a fold-endpoint index, not an intrafold
curve. It starts at 100 at the first Test open, and each Test end multiplies its
previous value by that fold's final_balance / initial_balance. This normalizes
fresh-capital accounts and includes all fees, spread/slippage and final liquidation.
Absolute balances are never concatenated. Requests with Test gaps are rejected;
no implicit gap return or position continuity is assumed. No stitched drawdown is
reported, since endpoint sampling omits intrafold fluctuations.

Multiple historical folds help describe temporal variation; they do not constitute
parameter optimization, statistical independence, robustness certification or a
future prediction. Strategies must be frozen before inspecting Test. Repeated
experimentation can contaminate all historical OOS periods. Finite RSI/EMA seeds,
constant illustrative costs, unlimited liquidity and open/close drawdown sampling
retain the limitations of the existing engines. JSON includes precise folds,
shared metadata, configuration/execution assumptions, ordering policies, full
segment results, optional index, aggregate definitions and methodology warnings.


## Advanced indicator conventions

Every indicator operand requires an explicit `name`; numerical defaults never
infer an indicator family from an incomplete operand.

The v0.9 implementation extends the existing `type: indicator` operand union,
comparison operators, nested groups, complexity limits and backtester. No new
financial engine, provider or execution semantics are introduced. Released in
v0.9.0 — Advanced Technical Indicators. All examples in `examples/advanced-*`
use the validated schema and a fixed UTC end.

### Definitions and available observations

- MACD: `name: macd`, integer `fast_period`, `slow_period`, `signal_period` in
  1–1000 (defaults 12/26/9), fast strictly less than slow; component `macd`
  (default line), `signal` or `histogram`. Price EMAs use alpha=2/(p+1),
  adjust=False, first-close seed, and hide the first p-1 observations. The line
  is fast EMA minus slow EMA and first becomes available at local index slow-1.
  The signal EMA starts at that first available line value, uses the same EMA
  recurrence, and hides its first signal-1 observations. Signal and histogram
  first appear at slow+signal-2. Histogram is line minus signal. This explicitly
  differs from implementations that seed signal using unavailable early MACD
  or seed price EMAs with an SMA. Components share the same seed and warm-up,
  so adding a signal/histogram operand cannot change the MACD line.
- Bollinger: `name: bollinger`, period 1–1000 (default 20), positive finite
  multiplier (default 2.0), required component upper/middle/lower. Middle is
  existing SMA(close,p); upper/lower = middle ± multiplier * rolling population
  std (ddof=0). First output is at p-1. Period 1 and constant prices have zero
  standard deviation; all three bands coincide. Existing SMA is unchanged.
- ATR: `name: atr`, period 1–1000 (default 14), no component. It consumes validated
  high, low and previous close, not close-only changes. At the first local candle
  TR=high-low (there is no previous local close). Subsequently TR=max(high-low,
  abs(high-previous close), abs(low-previous close)). ATR's first value at p-1
  is the arithmetic mean of the first p TRs; subsequent values use
  ATR=(p-1)/p * previous ATR + TR/p. Period 1 returns TR. ATR revalidates OHLCV
  model instances and rejects invalid/nonfinite prices or nonincreasing timestamps.

Low-level indicator functions represent unavailable warm-up observations with NaN,
never with a fabricated value. Rules treat unavailable operands as false; these
internal NaNs are never serialized as financial metrics. Research history fetching
rejects insufficient prior data instead of moving evaluation boundaries. Explicit
nonfinite inputs/parameters and nonfinite available computed outputs are errors.

### Warm-up, dependency identity and metadata

Advanced dependencies always anchor locally before the first eligible evaluation
candle (or first Train open); rolling/expanding windows continue the same causal
series, never reseed at fold or Test boundaries. Required prior candles are:

| Indicator | Prior candles | Initialization |
| --- | --- | --- |
| MACD, all components | 10*(slow+signal) | First-close price EMAs, first available MACD signal seed |
| Bollinger, all components | period | Rolling SMA and population std |
| ATR | 20*period | First TR high-low, SMA TR seed, then Wilder |
| RSI / SMA / EMA | p+1 / p / 5p | Existing conventions |

MACD is two sequential filters: the policy allocates ten slow-period spans plus
ten signal-period spans, rather than assuming the legacy EMA 5p policy settles
both stages. ATR's alpha=1/p decays more slowly than EMA's 2/(p+1); it receives
20p observations, including its SMA seed. These are fixed deterministic finite
approximations, not exact infinite-history indicators or guarantees that seed
error cannot change a near-threshold trade. Even small indicator error can change
signals. Moving the evaluation start changes the declared seed protocol.

Dependency extraction visits every operand in nested rules. Existing cache keys
remain (name,period). An advanced key is an opaque pair: canonical JSON of the
complete validated operand and initialization-policy version 1. It includes every
period, multiplier and component; callers must use `indicator_key` and
`indicator_from_key`, not parse the encoding. Future initialization changes require
a version change. Each component has its own series identity, while MACD and
Bollinger components with identical calculation parameters share one underlying
family calculation per cache preparation. Different multipliers, periods or
families cannot collide. ATR uses the existing fetched OHLCV history, never a
separate provider request. Input fields are explicit in initialization metadata.
Prepared ATR contexts retain high/low/close inputs as well as cached values; execution
rejects stale contexts with matching closes but changed highs/lows. Context prefix
slicing preserves and truncates these inputs at segment ends.

Sensitivity and walk-forward retain v0.6/v0.8 dependency-local initialization for
all indicators. Comparison and validation preserve the earlier common legacy
RSI/SMA/EMA seed: its lookback is the maximum *legacy* dependency warm-up only.
New advanced dependencies use individual anchors; additional advanced warm-up is
trimmed from the legacy calculation prefix. Thus adding a longer advanced strategy
cannot move existing legacy seeds. The older behavior where adding a longer
legacy indicator can change comparison/validation's common legacy seed remains;
use the recorded anchors when comparing workflows. Standard direct rule backtests
with advanced operands anchor advanced series when evaluation_start is supplied;
legacy-only direct behavior remains unchanged. AI execution uses the same advanced-local/legacy-common
policy as comparison and records those anchors. A low-level direct
run at evaluation_start=0 uses only the supplied finite history, with unavailable
signals false, just as legacy direct runs do.

Shared metadata includes full definitions, input_fields, seed_policy, actual history
start and preceding count per initialized dependency. Sensitivity/cost/walk-forward
replace shared-history anchors with the actual local anchors they use. Legacy
strategy JSON retains its original fields; report initialization metadata gains
additive fields. Comparison/validation gain indicator_initializations (empty for
legacy-only reports). Candle SHA256 continues covering full OHLCV and warm-up.
Execution-cost formulas, reference marking, next-open timing, fresh segment cash,
final-close liquidation and net Buy & Hold are unchanged.

### Sensitivity and interpretation

Numeric paths use the same entry/exit(.conditions.N)*.(left|right) prefix.
MACD permits fast_period/slow_period/signal_period; Bollinger period/multiplier;
ATR period. Components and names are immutable. Period grids require integers,
while multiplier grids allow finite fractional values. Nearby multipliers need an
explicit step. Couplings can join identical calculation parameters across MACD
or Bollinger components, but must name the same field and share all base
calculation parameters. Every variant is revalidated; fast>=slow, nonpositive
multipliers and invalid periods reject the entire grid. Existing dimension and
variant bounds and declared ordering remain in force; seeds cannot move when a
longer variant is added.

MACD above signal is a persistent state comparison, not a crossing event. Cross,
crosses, crossing, crossover and crossunder requests remain rejected. AI only
extracts validated configurations using the existing Responses structured output
boundary. It computes no series/trades, generates no executable code and selects
no strategy. ATR volatility thresholds are absolute quote-price units. No stops,
position sizing by ATR, leverage, shorts, live orders, statistical robustness
claims or predictions are added.


## Evidence-grounded reports (v1.0 feature)

`report --input` reads one existing JSON result. It never calls a data provider or
backtester. `reports/inputs.py` bounds decoding and chooses an explicit
`sba-v0.9-<type>/1` adapter. Supported unversioned inputs are the complete v0.8/v0.9
standard CLI result, AI CLI wrapper, ComparisonResult, ValidationReport,
SensitivityReport, CostScenarioReport and WalkForwardReport. Missing source
schema versions remain null; other versions and ambiguous shapes reject rather
than guessing. Full native models and required fields are validated before
`reports/validation.py` checks accounting, execution assumptions, segment bounds,
identities/order, dependency and initialization metadata, and summary consistency.
Existing execution, ranking, sensitivity and OOS summary helpers are reused only
for consistency checks. No indicator or trade is recomputed by report generation.
These checks cannot verify supplied signal accuracy, actual market prices,
intrabar behavior or an equity path absent from the source. A candle digest is
unverified provenance, not proof of truthful financial results.

`reports/evidence.py` extracts typed metrics with stable scope IDs, JSON source
paths, units and methodological context. Financial values are copied, with
explicit final-minus-initial net PnL where needed. Existing calculations are not
replaced. Source strategy order and complete Train/Test/fold/scenario metrics are
preserved. Deterministic observations use explicit sign, count and comparison
rules; undefined metrics remain null. Sensitivity and cost scenarios are labeled
Train-only. Walk-forward Test summaries remain distinct from Train diagnostics;
stitched endpoints are an index compounded from independent Test returns, never
a position-carrying portfolio or pooled drawdown. Benchmark policy must be the
supported net policy; unknown/gross policies are rejected instead of relabeled.

`reports/render.py` renders applicable Markdown sections or the strict JSON
ResearchReport. Percent and percentage-point units are separate; monetary costs
use quote currency. Display rounding does not change evidence precision. No wall
clock timestamp is introduced. Original-byte SHA256, canonical-input SHA256 and
canonical-evidence SHA256 serve different purposes: whitespace changes the first
and provenance-containing evidence, while canonical input hashing ignores JSON
key order/whitespace. Canonical JSON sorts keys and disallows nonfinite numbers.
Input dates normalize to UTC. Generator and adapter versions are recorded;
changes to report semantics require a generator-version change.

### Optional interpretation and trust boundaries

`reports/ai.py` sends only selected deterministic observations and their referenced
metrics to the existing OpenAI structured-output SDK. It excludes raw candles,
trades, prompts, strategy names and source notes. Requests use store=false, no
tools, bounded output and the existing timeout/retry policy. The AI selects from
approved explanation and research-question codes, returning exact approved text.
Validation requires compatible observation kinds, exact known evidence IDs,
separately matched numeric values/units and no duplicated statements. Unknown
references, free prose, numerical inventions, advice and forecasts reject the
interpretation. This constraint intentionally limits expressiveness; checking
IDs alone cannot prove unrestricted natural-language claims. Even accepted
selection is not a financial or statistical inference engine.

Missing credentials/provider failures yield `ai_unavailable`; invalid structured
output or failed grounding yields `ai_rejected`. Both preserve the complete
deterministic evidence and report, emit a sanitized warning and exit 0. Accepted
AI is separately labeled with requested/response model metadata; its selection
is not guaranteed byte reproducible. Raw provider exceptions/headers are never
printed. Invalid source or filesystem errors exit 2, without a report object.

Inputs are untrusted: maximum 16 MiB, depth 32, 250,000 nodes and 8,192 characters
per string; duplicate keys, nonfinite numbers and unsupported controls reject.
Only regular files are read, nonblocking to avoid FIFO hangs. No eval or generated
code runs. User strings are escaped as Markdown data (including HTML/link/table
syntax); source warnings are explicitly unverified notes, not generated findings.
POSIX output uses descriptor-relative, no-follow directory traversal and an
exclusive temporary file, fsync and atomic no-overwrite hard link. Parent
traversal, symlink directories and existing destinations reject. Input files are
never overwritten. Multi-file aggregation, PDF/HTML, charts, source authenticity
verification and unrestricted AI narratives remain outside this feature.

### Offline example

`examples/report_fixture.py` explicitly creates fixed synthetic native research
JSON (not historical BTCUSDT); it is separate from the reporting pipeline.
`examples/report-source.json` and `examples/research-report.md` are checked in,
and a regression regenerates both byte-for-byte. To generate a new report:

```bash
poetry run strategy-backtest report --input examples/report-source.json --format markdown
poetry run strategy-backtest report --input examples/report-source.json --format json
```


### Legacy initialization compatibility

v0.8 local initialization profiles omit the additive v0.9 `input_fields` and
`seed_policy` fields. For RSI/SMA/EMA only, the complete legacy profile shape is
accepted without treating model defaults as source assertions. Explicit fields
must both be present and agree with indicator semantics. Period/dependency,
prior-count, warm-up and UTC anchor checks always apply. Advanced indicators
still require complete profiles. v0.8 comparison/validation may omit the profile
list, which those engines did not yet emit. Missing legacy fields remain absent
in normalized provenance rather than being invented. Source schema versions
remain null: unversioned structure cannot authenticate a producer version.
Tagged v0.8/v0.9 synthetic fixtures cover all six result types.


### Human-readable Markdown

Markdown is a presentation of the unchanged evidence contract. Unique rule
structures are formatted once with the existing DSL formatter. Nested configuration
and initialization metadata become individual labeled rows; financial segment
metrics become compact returns/benchmark, trade and cost tables, grouped by
strategy for Walk-Forward. Short R row references connect metrics to exact UTC
Train/Test boundaries. Every segment and undefined/negative value remains visible;
full identifiers, source paths and per-metric contexts stay in JSON. Executive
sentences replace machine scope prefixes with readable labels. Optional AI uses
the same short references without changing accepted statements or grounding.
Markdown escapes syntax with backslashes, HTML delimiters with named entities,
and removes controls; ordinary colons and quotation marks remain readable.
No input hash, normalized evidence, observation, AI constraint or JSON field is
changed by rendering. Six synthetic snapshots and pinned JSON hashes cover the
presentation boundary.


### v1.0.0 release verification

The package release is v1.0.0; research result shapes remain compatible with v0.9,
and report schema 1.0 / generator research-reports/1 remain separate version fields.
All six v0.8/v0.9 tagged synthetic result fixtures retain their financial values.
No backtester, indicator, portfolio, benchmark or research-engine calculation changed
for this release. The existing CLI only gains the report dispatch; the shared AI
default is corrected to gpt-4.1-mini, with OPENAI_MODEL override preserved.

The unchanged default 180-day offline demo is intentionally not a profitability
example. Its sine-wave candles and legacy RSI timing produce 45 losing trades,
final balance 123.09 from 10000, return -98.77%, and net Buy & Hold +6.98%.
Full demo JSON matches the v0.9.0 tagged implementation byte-for-byte. Negative
performance is retained; no accounting or synthetic candles were adjusted to make
it look attractive. The demo exercises reproducibility and command behavior rather
than validating real-market predictive value. Release tests use mocked OpenAI
responses; they do not establish live API account access or real-model behavior.


### CLI environment configuration

The common CLI entry point calls python-dotenv once before subcommand dispatch,
using `find_dotenv(usecwd=True)` and `load_dotenv(..., override=False)`. Discovery
starts at the caller's working directory and walks parents; explicit shell values
for OPENAI_API_KEY, OPENAI_MODEL and other settings take precedence. No .env is
required. Library calls do not implicitly load files. Existing SDK credential/model
reads remain unchanged and consume the resulting environment. Tests disable ambient
.env loading and explicitly opt into isolated temporary files for regression cases;
developer credentials are never needed for the offline suite.
