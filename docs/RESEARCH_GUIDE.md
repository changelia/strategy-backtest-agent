# Research Guide

Choose a research mode to answer a bounded historical question. Every mode evaluates
fixed rules with Python calculations. None automatically optimizes parameters,
selects a winner, or forecasts future returns.

## Data, time, and execution conventions

Each configuration names one symbol, timeframe and whole-day `period_days` history.
Aware timestamps are normalized to UTC. A fixed `evaluation_end` makes the requested
boundary repeatable; it does not freeze Binance's data. Shared research workflows
record resolved candle boundaries, indicator dependencies/warm-up and candle SHA256.
The hash is provenance metadata, not proof of source authenticity.

The standalone backtest CLI instead accepts duration through `--days`; do not put
`period_days` in a `BacktestConfig`. Fees are fractions per side (`0.001` means 0.1%),
full spread is in bps with half applied on each side, and slippage is adverse bps per
side. Signals use completed candles and fill at the next candle open. Buy & Hold uses
the same cost assumptions. Portfolios use fractional quantities and full fills,
liquidate at their segment's final close, and have no modeled liquidity limits.

Synthetic demo input is deterministic and offline, ending at 2024-07-01 00:00 UTC.
It verifies code paths, not market behavior. Binance requests require network access
and can be limited by provider availability, historical gaps, region, or rate limits.

## The six research modes

Each terminal example below is independent: start it from a new working directory.
The `curl` step retrieves only a version-controlled example config from GitHub; config
validation and `--demo` research itself make no application network request. Sensitivity
and costs require live Binance candles as noted in those sections.

### 1. Single-strategy backtest

Use `BacktestClient.run` or the root `strategy-backtest` command to evaluate one legacy
RSI config or an AI-extracted RSI/rule strategy. The client also accepts validated
config models, mappings, and JSON paths via `config=`. `demo=True` runs synthetic data;
otherwise it fetches Binance.

```bash
strategy-backtest init --type backtest --output backtest-config.json
strategy-backtest --config backtest-config.json --days 30 --demo --json > backtest.json
```

The output is raw engine JSON, not the normalized report JSON described under Reports.
The template includes the initial balance and execution assumptions. Expected result:
initial/final balance, return, net Buy & Hold, trade and cost metrics. Next, pass this
raw JSON to `strategy-backtest report` to create Markdown or normalized report JSON.

### 2. Strategy comparison

Use comparison to evaluate 2–5 fixed strategies on shared candle data and shared
account/cost assumptions. Each strategy starts with separate cash; results are not a
pooled portfolio. Ranking is a descriptive display convention only.

```bash
mkdir comparison-run && cd comparison-run
set -C
curl -fsSL https://raw.githubusercontent.com/changelia/strategy-backtest-agent/main/examples/comparison.json > comparison-config.json
strategy-backtest compare --config comparison-config.json --demo --json > comparison-result.json
```

Complete example: [`examples/comparison.json`](../examples/comparison.json). It includes
three predeclared RSI/SMA strategies and a fixed UTC end. `--demo` avoids Binance;
without it, config mode fetches Binance. `--sort` accepts `total_return`, `excess_return`,
`max_drawdown`, and `profit_factor`.
Expected result: one result for each strategy plus shared data and ranking. Next,
inspect each independent result and its benchmark/cost assumptions; a display ranking
is not an automatic recommendation.

### 3. Chronological Train/Test validation

Use validation for one predeclared strategy set and a single chronological split.
`train_ratio` defaults to 0.70 and must be 0.50–0.90. Train comes first, Test second;
each has independent capital, positions, trades and liquidation. Prior candles may
initialize indicators, but a signal or position does not cross the split.

```bash
mkdir validation-run && cd validation-run
set -C
curl -fsSL https://raw.githubusercontent.com/changelia/strategy-backtest-agent/main/examples/validation.json > validation-config.json
strategy-backtest validate --config validation-config.json --demo --json > validation-result.json
```

Complete example: [`examples/validation.json`](../examples/validation.json). Select
rules before inspecting Test. If you alter rules after reviewing Test, that period is
no longer an untouched holdout. A positive Test return is historical evidence, not
proof of predictive value.
Expected result: separate Train and Test metrics, boundaries and methodology warnings.
Next, regard Test as held out only if it was not used to choose the rules.

### 4. Parameter sensitivity

Use sensitivity to describe how a declared grid changes **Train-only** outcomes. It
does not evaluate Test, rank or choose a variant. The default split reserves later
candles; do not use the grid as an automatic optimization tool.

```bash
mkdir sensitivity-run && cd sensitivity-run
set -C
curl -fsSL https://raw.githubusercontent.com/changelia/strategy-backtest-agent/main/examples/sensitivity.json > sensitivity-config.json
strategy-backtest sensitivity --config sensitivity-config.json --json > sensitivity-result.json
```

Complete example: [`examples/sensitivity.json`](../examples/sensitivity.json). CLI
sensitivity always fetches Binance and does not accept `--demo`; the Python client
supports synthetic input with `demo=True`. Each `parameters` item uses exactly one of
`values`, `range`, or `nearby`; maximum three dimensions and 25 variants. Paths name
the exact DSL field, for example `entry.right.value`. Period and MACD fast/slow
constraints are validated; invalid grid combinations fail the entire request.

The report includes variants and descriptive grid summaries; undefined values remain
null. Similarity and neighbor observations have fixed conventions but are not
significance tests. Repeated exploration can overfit Train.
Expected result: requested variants and Train-only summary, with no Test metrics or
selected winner. Next, freeze a rule set before a separate validation run.

### 5. Execution-cost scenarios

Use costs to compare modeled assumptions for one fixed strategy on Train. The first
scenario is the zero-spread/zero-slippage baseline. Scenario fees inherit the shared
fee unless explicitly set. The scenarios are illustrative and are not measured Binance
quotes or estimates.

```bash
mkdir costs-run && cd costs-run
set -C
curl -fsSL https://raw.githubusercontent.com/changelia/strategy-backtest-agent/main/examples/execution-scenarios.json > costs-config.json
strategy-backtest costs --config costs-config.json --json > costs-result.json
```

Complete example: [`examples/execution-scenarios.json`](../examples/execution-scenarios.json).
The CLI accepts only `--config` and `--json`: no natural-language parser and no
`--demo`; it always fetches Binance data. `BacktestClient.costs(config=..., demo=True)`
is available for an offline synthetic run.
Expected result: each scenario's Train metrics and return difference from the first
zero-cost baseline. Next, consider whether assumptions deserve more research; these
scenarios are not market cost estimates.

### 6. Walk-Forward

Use Walk-Forward to observe predeclared fixed strategies across several chronological
Train/Test windows. It is not true walk-forward parameter optimization: Train results
are diagnostics only, and no parameters or strategies are selected between folds.
Rolling windows move fixed-size Train and Test intervals; expanding Train begins at the
first evaluation candle and grows. Durations map to exact candle counts. Complete
folds are required, Test intervals cannot overlap, a minimum of two folds is required,
and incomplete trailing candles are reported.

```bash
mkdir walk-forward-run && cd walk-forward-run
set -C
curl -fsSL https://raw.githubusercontent.com/changelia/strategy-backtest-agent/main/examples/walk-forward.json > walk-forward-config.json
strategy-backtest walk-forward --config walk-forward-config.json --demo --json > walk-forward-result.json
strategy-backtest report --input walk-forward-result.json --format markdown --output walk-forward-report.md
```

Complete example: [`examples/walk-forward.json`](../examples/walk-forward.json). Every
Train and Test segment starts with fresh initial capital; positions never carry across
segments or folds. Aggregate statistics use Test results only. An optional stitched
OOS index compounds normalized independent Test returns at fold endpoints; it does
not represent an account with carried positions and has no continuous drawdown
interpretation. Gaps are not stitched.
Expected result: every complete fold, Train/Test metrics, unused trailing candles and
Test-only summary statistics. Next, inspect negative folds and warnings before drawing
descriptive conclusions.

## Complete offline Python example

The package's public client can run all six modes against synthetic candles. It needs
no OpenAI key, Binance access, or application network request. With the package
installed, retrieve the runnable example into a new directory and run it:

```bash
mkdir customer-python-research && cd customer-python-research
set -C
curl -fsSL https://raw.githubusercontent.com/changelia/strategy-backtest-agent/main/examples/customer_research.py > customer_research.py
python customer_research.py
```

Expected: the script prints a result type and formatted summary for backtest,
comparison, validation, sensitivity, cost scenarios, and Walk-Forward. The API is in
the published 1.2.0 package. The example file is a repository resource, not a file
installed into site-packages; download it as shown, or copy the complete script from
[`examples/customer_research.py`](../examples/customer_research.py).

## Strategies and indicators

Legacy RSI configs and the nested Strategy DSL are supported. DSL operands include
price, numeric values, and indicator components. Operators are `<`, `<=`, `>`, `>=`,
and nested `AND`/`OR`. Supported indicators:

| Indicator | Parameters/components | Calculation convention |
| --- | --- | --- |
| RSI | period, default 14 | Wilder RSI. |
| SMA | period | Close-price simple moving average. |
| EMA | period | Close-price EMA with deterministic finite seed. |
| MACD | fast 12, slow 26, signal 9; `macd`, `signal`, `histogram` | Fast EMA minus slow EMA; signal EMA over MACD line. |
| Bollinger Bands | period 20, multiplier 2.0; upper/middle/lower | SMA middle; population standard deviation (`ddof=0`). |
| ATR | period 14 | True Range uses high, low, prior close; SMA seed then Wilder smoothing. |

`MACD > signal` is a state relation, not a crossover event; crossover operators are
unsupported. The engine rejects malformed or too-complex rules and insufficient
required history. Warm-up candles initialize indicators but do not become evaluation
trades. Finite EMA, MACD and ATR seeds can still affect values near thresholds.

Short selling, leverage, multi-symbol portfolio execution, stop-loss/take-profit orders,
private exchange endpoints, live trading, arbitrary Python rules, and liquidity
prediction are unsupported.

## Reading results and reports

Return is a percent; excess return is a difference in percentage points (pp); drawdown
is a percent. Win rate is undefined with no completed trades, and profit factor can be
null when undefined—null is not zero. Fees are quote currency. Spread/slippage settings
and modeled totals are different concepts. Inspect the source range, benchmark policy,
execution assumptions, warm-up and warnings before interpreting metrics.

Raw research JSON contains engine inputs and results. `strategy-backtest report` turns
one saved raw result into normalized report JSON or Markdown without rerunning research.
Markdown is for reading; report JSON preserves evidence IDs, units, source paths, hashes
and warnings. See [Quick Start](QUICK_START.md) for a complete report sequence.

Repeated evaluation of the same history can lead to selection bias. Neither a positive
historical return nor multiple positive folds proves future performance or robustness.
