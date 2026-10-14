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
the largest requirement: RSI p+1, SMA p, EMA 5p prior intervals. It checks continuous history,
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
`indicator` with name `rsi`, `sma`, or `ema` and an integer period. RSI periods are 2–500;
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

Unsupported requests fail rather than silently becoming RSI: MACD, Bollinger Bands, short
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

The latest tag is v0.4.0 and `pyproject.toml` declares 0.4.0. There is no current
package/tag mismatch. Earlier tags may retain historical metadata mismatches; they
are not modified. The v0.5.0 implementation leaves the package version at 0.4.0 until
a separate release workflow. No release tag, push or publication is part of this work.

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
