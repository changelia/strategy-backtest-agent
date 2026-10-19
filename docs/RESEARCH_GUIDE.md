# Research Guide

[Home](../README.md) · [Quick Start](QUICK_START.md) · [Python API](PYTHON_API.md) · [CLI](CLI.md) · [AI](AI.md)

Use a research mode to answer a predeclared historical question. Python performs all
calculations. Strategies remain fixed; no mode chooses an optimal strategy or forecasts
future returns. Run independent examples in **separate fresh directories** so results
are preserved and file creation succeeds.

## Contents

- [Configuration contracts](#configuration-contracts)
- [Six complete research workflows](#six-complete-research-workflows)
- [Parameter grids and cost scenarios](#parameter-grids-and-cost-scenarios)
- [Strategy DSL and indicators](#strategy-dsl-and-indicators)
- [Metrics and report interpretation](#metrics-and-report-interpretation)
- [Execution, initialization and reproducibility](#execution-initialization-and-reproducibility)

## Configuration contracts

A **configuration** is input, not a result/report. Use the model for the consumer:

| Model | Consumer | What it describes |
| --- | --- | --- |
| `BacktestConfig` | Python `run`; root CLI `--config` | Legacy RSI and account/cost settings. Duration is `days=` / `--days`, not a model field. |
| `AIStrategyConfig` | Python `run`; Python parse output | One legacy RSI or DSL strategy, with `period_days`. Despite the name, manual construction needs no AI. Root CLI does not consume this model. |
| `ComparisonConfig` | `compare` | Shared market/account/costs; 2–5 named fixed strategies; display sorting. |
| `ValidationConfig` | `validate` | Shared settings; 1–5 named strategies; chronological Train/Test split. |
| `SensitivityConfig` | `sensitivity` | Shared settings; one DSL `base_strategy`; bounded parameter grid; Train only. |
| `CostScenarioConfig` | `costs` | Shared settings; one fixed DSL `strategy`; 2–8 execution scenarios; Train only. |
| `WalkForwardConfig` | `walk_forward` / CLI `walk-forward` | Shared settings; 1–5 named strategies; rolling/expanding windows. |

Python `config=` accepts the matching validated model, a mapping, or a JSON file path.
Positional strings are natural-language requests, never guessed filenames. Supplying
both request/config is an error. Direct model construction is validated by Pydantic;
unknown fields and NaN/Infinity fail. Models are frozen: edit a dumped mapping then
revalidate, rather than assigning attributes. See [Python input reference](PYTHON_API.md#input-error-and-diagnostics-reference).

### Market and account fields

A candle records open, high, low, close and traded volume (OHLCV) for one timeframe.
For `BTCUSDT`, BTC is the traded asset and USDT is the quote currency: account balances,
trade profit/loss (PnL) and cost totals are measured in USDT. These are simulated accounts,
not exchange balances.

| Field | Default / valid input | Meaning |
| --- | --- | --- |
| `symbol` | Required in AI/shared research configs; `BTCUSDT` in `BacktestConfig` | Uppercase provider symbol; AI/shared regex `[A-Z0-9]{5,20}`, legacy accepts uppercase alphanumeric. One symbol per research run. |
| `timeframe` | `1h` | `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `8h`, `12h`, `1d`. |
| `period_days` | 30; integer 1–365 | Evaluation duration in AI/shared configs. Earlier warm-up is fetched in addition. Not a `BacktestConfig` field. |
| `days` / `--days` | Python legacy default 180; root CLI 180 | Positive integer duration for single backtest. With AI config/parsed request, Python `days=` must agree with `period_days`. |
| `initial_balance` | 10000, positive | Fresh starting cash in quote currency; never carried between independent portfolios. |
| `fee` | 0.001, 0–0.05 inclusive in AI/shared configs | Fee fraction per executed side. Legacy backtest instead uses `trading_fee` with `0 <= value < 1`. |
| `execution` | `null` | Omitted means alias fee, zero spread/slippage. Explicit costs use `ExecutionConfig`. |
| `evaluation_end` | `null` in shared configs | Timezone-aware end, normalized to UTC. Omitted live end resolves to current time. Half-open range `[start,end)` uses completed candles. Not an `AIStrategyConfig`/`BacktestConfig` field: pass `run(evaluation_end=...)` in Python. |

Costs use `execution.fee_rate` (`0 <= value < 1`), `execution.spread_bps` and
`execution.slippage_bps` (finite, nonnegative). 1 bp = 0.01%; `fee=0.001` = 0.1%,
not 0.001%. Spread is **full spread**, half applied per side; slippage is adverse per
side. Require `spread_bps / 2 + slippage_bps < 10000` for a positive sell price.
If an explicit alias fee and `execution.fee_rate` disagree, validation rejects the
config. If `fee_rate` is omitted it inherits the alias; if the alias is omitted an
explicit fee rate becomes the normalized fee. The workflow alias limit still applies
after normalization: AI/shared effective fees cannot exceed 0.05; scenario-specific
fee overrides separately allow values below 1. CLI cost flags override only their
supplied spread/slippage component and revalidate. There is no per-strategy override
of shared market/account/costs.

A named strategy has `id` (1–64 alphanumeric/underscore/hyphen, first character
alphanumeric), `name` (1–80 non-control characters), and `strategy`. IDs must be unique.
Use a DSL strategy or legacy `RSIStrategy` (`type="rsi"`, period default 14, range
2–200; `entry_below` default 30, `exit_above` default 70, both strictly between 0 and
100, entry < exit). BacktestConfig's distinct legacy fields allow `rsi_period >= 1`,
thresholds 0–100 with entry < exit. Do not substitute one schema's field names into another.

## Six complete research workflows

Prerequisites: installed package in an active virtual environment. For each section,
create the indicated JSON file by copying the **entire** block into a text editor.
Then use either the Python script or CLI commands, from a new directory. No repository
checkout/resources are required. The same files are version-controlled under
[`examples/`](https://github.com/changelia/strategy-backtest-agent/tree/main/examples)
as `customer-*.json`. They are not installed package resources. Downloading examples
from GitHub uses network; executing the synthetic examples does not.

Each Python block is a complete script: save it as `research.py` and run
`python research.py` after creating the corresponding config. It prints the summary
and relevant fields, saves raw JSON using exclusive creation, and generates both
report formats. CLI examples save the same categories of output. Choose **one** path
per directory to avoid output conflicts.

### 1. Single-strategy backtest

Question: how did my declared RSI rule behave over this window? Use this as the first
accounting/strategy check. This example is **offline synthetic**, with no AI/market
request. The root CLI accepts only this legacy RSI schema. Python also supports the
DSL through `AIStrategyConfig`, described after this example.

Save as `customer-backtest.json`:

```json
{
  "symbol": "BTCUSDT",
  "timeframe": "1h",
  "initial_balance": 10000.0,
  "trading_fee": 0.001,
  "rsi_period": 14,
  "entry_rsi": 30.0,
  "exit_rsi": 70.0,
  "execution": {
    "fee_rate": 0.001,
    "spread_bps": 10.0,
    "slippage_bps": 5.0
  }
}
```

Python (offline):

```python
from pathlib import Path
from strategy_backtest_agent import BacktestClient, BacktestConfig

client = BacktestClient()
config = BacktestConfig.model_validate_json(Path("customer-backtest.json").read_text())
result = client.run(config=config, days=30, demo=True)
print(result.summary())
print(result.final_balance, result.total_trades, result.costs.fees)
with Path("result.json").open("x", encoding="utf-8") as stream:
    stream.write(result.to_json())
result.save_report("report.md")
result.save_report("report.json", format="json")
```

CLI, using the same saved config (**Offline synthetic**; no AI.):

```bash
set -C
strategy-backtest --config customer-backtest.json --days 30 --demo --json > result.json
strategy-backtest report --input result.json --format markdown --output report.md
strategy-backtest report --input result.json --format json --output report.json
```

Expected: initial/final balance, return, net benchmark, completed trades, drawdown and
costs for one portfolio. These are synthetic outcomes; the demo is not a profitability
example. Warm-up differs between the legacy backtest and shared research modes, so
identical RSI thresholds do not promise identical standalone/shared results.

Next: read every result (including negative and zero-trade cases), costs and methodology
warnings in `report.md`; retain `result.json` as the raw source, and `report.json` as
normalized evidence. Use new filenames/directories for reruns.

For advanced single-strategy DSL without AI, save the following complete
`AIStrategyConfig` as `customer-ai-strategy.json` (the name identifies a schema, not a
required provider call):

```json
{
  "symbol": "BTCUSDT",
  "timeframe": "1h",
  "period_days": 30,
  "initial_balance": 10000.0,
  "fee": 0.001,
  "execution": {
    "fee_rate": 0.001,
    "spread_bps": 10.0,
    "slippage_bps": 5.0
  },
  "strategy": {
    "type": "rules",
    "entry": {
      "type": "comparison",
      "left": {
        "type": "indicator",
        "name": "rsi",
        "period": 14
      },
      "operator": "<",
      "right": {
        "type": "value",
        "value": 30.0
      }
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
        "value": 70.0
      }
    }
  }
}
```

Run it with Python, not root CLI `--config`:

```python
from strategy_backtest_agent import BacktestClient

client = BacktestClient()
result = client.run(config="customer-ai-strategy.json", demo=True)
print(result.summary())
result.save_report("dsl-report.md")
```

Expected: the supported DSL RSI rule on synthetic candles. Edit operands or nested
conditions using the exact models below. See [AI Guide](AI.md) for paid parsing of your
own English request; parsing is separate from these deterministic configs.

### 2. Strategy comparison

Question: how did 2–5 fixed strategies behave on the same data and execution costs?
Use comparison to make historical differences visible, not to choose a live winner.
The example is **offline synthetic**. Each strategy starts in an independent portfolio;
market history is shared.

Save as `customer-comparison.json`:

```json
{
  "symbol": "BTCUSDT",
  "timeframe": "1h",
  "period_days": 30,
  "initial_balance": 10000.0,
  "fee": 0.001,
  "execution": {
    "fee_rate": 0.001,
    "spread_bps": 10.0,
    "slippage_bps": 5.0
  },
  "evaluation_end": "2024-07-01T00:00:00Z",
  "strategies": [
    {
      "id": "rsi-30",
      "name": "RSI 14 30/70",
      "strategy": {
        "type": "rsi",
        "period": 14,
        "entry_below": 30.0,
        "exit_above": 70.0
      }
    },
    {
      "id": "rsi-25",
      "name": "RSI 14 25/70",
      "strategy": {
        "type": "rsi",
        "period": 14,
        "entry_below": 25.0,
        "exit_above": 70.0
      }
    }
  ],
  "sort_by": "total_return"
}
```

Python (offline):

```python
from pathlib import Path
from strategy_backtest_agent import BacktestClient, ComparisonConfig

client = BacktestClient()
config = ComparisonConfig.model_validate_json(Path("customer-comparison.json").read_text())
result = client.compare(config=config, demo=True)
print(result.summary())
for item in result.results:
    print(item.id, item.result.total_return_percent, item.excess_return_pp)
print("Ranking:", result.ranking)
with Path("result.json").open("x", encoding="utf-8") as stream:
    stream.write(result.to_json())
result.save_report("report.md")
result.save_report("report.json", format="json")
```

CLI, using the same saved config (**Offline synthetic**; no AI.):

```bash
set -C
strategy-backtest compare --config customer-comparison.json --demo --json > result.json
strategy-backtest report --input result.json --format markdown --output report.md
strategy-backtest report --input result.json --format json --output report.json
```

Expected: one `results` item per strategy plus shared metadata and ranking IDs.
`sort_by` defaults to `total_return`; alternatives are `excess_return`, `max_drawdown`
and `profit_factor`. Less-negative drawdown ranks higher; null metrics sort last,
ties by ID. `--sort` overrides the display/ranking criterion, not financial metrics.
A ranking is descriptive, not an automatically selected strategy.

Next: read every result (including negative and zero-trade cases), costs and methodology
warnings in `report.md`; retain `result.json` as the raw source, and `report.json` as
normalized evidence. Use new filenames/directories for reruns.

### 3. Chronological Train/Test validation

Question: how did 1–5 rules declared before inspection behave on a later period?
Use one chronological holdout. `train_ratio` defaults to 0.70, allowed 0.50–0.90.
Train gets `floor(N × train_ratio)` candles; Test gets the remainder; both require at
least two. The example is **offline synthetic**.

Save as `customer-validation.json`:

```json
{
  "symbol": "BTCUSDT",
  "timeframe": "1h",
  "period_days": 30,
  "initial_balance": 10000.0,
  "fee": 0.001,
  "execution": {
    "fee_rate": 0.001,
    "spread_bps": 10.0,
    "slippage_bps": 5.0
  },
  "evaluation_end": "2024-07-01T00:00:00Z",
  "strategies": [
    {
      "id": "rsi-30",
      "name": "RSI 14 30/70",
      "strategy": {
        "type": "rsi",
        "period": 14,
        "entry_below": 30.0,
        "exit_above": 70.0
      }
    }
  ],
  "train_ratio": 0.7
}
```

Python (offline):

```python
from pathlib import Path
from strategy_backtest_agent import BacktestClient, ValidationConfig

client = BacktestClient()
config = ValidationConfig.model_validate_json(Path("customer-validation.json").read_text())
result = client.validate(config=config, demo=True)
print(result.summary())
for item in result.results:
    print(item.id, item.train.result.total_return_percent, item.test.result.total_return_percent)
print("Test starts:", result.split.test_start)
with Path("result.json").open("x", encoding="utf-8") as stream:
    stream.write(result.to_json())
result.save_report("report.md")
result.save_report("report.json", format="json")
```

CLI, using the same saved config (**Offline synthetic**; no AI.):

```bash
set -C
strategy-backtest validate --config customer-validation.json --demo --json > result.json
strategy-backtest report --input result.json --format markdown --output report.md
strategy-backtest report --input result.json --format json --output report.json
```

Expected: separate Train/Test metrics and exact split boundaries. Test starts with
fresh initial cash and no position; Train signals cannot execute there. Test may use
prior candles only for causal indicator initialization. `return_gap_pp` is Test return
minus Train return; segment durations differ and the gap is not time-normalized.
Repeated tuning after inspecting Test contaminates its held-out role.

Next: read every result (including negative and zero-trade cases), costs and methodology
warnings in `report.md`; retain `result.json` as the raw source, and `report.json` as
normalized evidence. Use new filenames/directories for reruns.

### 4. Parameter sensitivity

Question: how much did a predeclared parameter grid change **Train-only** outcomes?
Use this to describe sensitivity; it never evaluates Test, ranks variants or selects
parameters. Default Train ratio 0.70 (0.50–0.90). The Python example is **offline
synthetic**; the CLI has **no --demo** and fetches Binance.

Save as `customer-sensitivity.json`:

```json
{
  "symbol": "BTCUSDT",
  "timeframe": "1h",
  "period_days": 30,
  "initial_balance": 10000.0,
  "fee": 0.001,
  "execution": {
    "fee_rate": 0.001,
    "spread_bps": 10.0,
    "slippage_bps": 5.0
  },
  "evaluation_end": "2024-07-01T00:00:00Z",
  "base_strategy": {
    "type": "rules",
    "entry": {
      "type": "comparison",
      "left": {
        "type": "indicator",
        "name": "rsi",
        "period": 14
      },
      "operator": "<",
      "right": {
        "type": "value",
        "value": 30.0
      }
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
        "value": 70.0
      }
    }
  },
  "train_ratio": 0.7,
  "parameters": [
    {
      "path": "entry.right.value",
      "values": [
        25.0,
        30.0,
        35.0
      ]
    }
  ]
}
```

Python (offline):

```python
from pathlib import Path
from strategy_backtest_agent import BacktestClient, SensitivityConfig

client = BacktestClient()
config = SensitivityConfig.model_validate_json(Path("customer-sensitivity.json").read_text())
result = client.sensitivity(config=config, demo=True)
print(result.summary())
print("Variants:", result.data.summary.variant_count)
for item in result.results:
    print(item.variant_id, item.train.result.total_return_percent, item.observation)
with Path("result.json").open("x", encoding="utf-8") as stream:
    stream.write(result.to_json())
result.save_report("report.md")
result.save_report("report.json", format="json")
```

CLI, using the same saved config (**Binance/network required**; no AI.):

```bash
set -C
strategy-backtest sensitivity --config customer-sensitivity.json --json > result.json
strategy-backtest report --input result.json --format markdown --output report.md
strategy-backtest report --input result.json --format json --output report.json
```

Expected: declared `variants`, Train `results`, grid `summary`, neighbor differences
and a 1D `ordered_series` / 2D `matrix` where applicable. The wrapper's `summary()`
method is text; use `result.data.summary` for the typed statistical summary. Candidate
order defines adjacency. Low-trade variants are flagged, not evidence of stability.
No Test returns are calculated. See parameter forms below.

Next: read every result (including negative and zero-trade cases), costs and methodology
warnings in `report.md`; retain `result.json` as the raw source, and `report.json` as
normalized evidence. Use new filenames/directories for reruns.

### 5. Execution-cost scenarios

Question: how did alternative declared execution assumptions affect one frozen
strategy on Train? The first scenario must have zero spread and zero slippage.
It **still charges the inherited fee** unless its fee is explicitly zero; do not call
it a zero-cost baseline. Python here is **offline synthetic**. CLI is config-only,
has no natural-language parser and **no --demo**; it fetches Binance.

Save as `customer-costs.json`:

```json
{
  "symbol": "BTCUSDT",
  "timeframe": "1h",
  "period_days": 30,
  "initial_balance": 10000.0,
  "fee": 0.001,
  "execution": {
    "fee_rate": 0.001,
    "spread_bps": 0.0,
    "slippage_bps": 0.0
  },
  "evaluation_end": "2024-07-01T00:00:00Z",
  "strategy": {
    "type": "rules",
    "entry": {
      "type": "comparison",
      "left": {
        "type": "indicator",
        "name": "rsi",
        "period": 14
      },
      "operator": "<",
      "right": {
        "type": "value",
        "value": 30.0
      }
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
        "value": 70.0
      }
    }
  },
  "train_ratio": 0.7,
  "scenarios": [
    {
      "id": "baseline",
      "name": "Fee-only baseline",
      "spread_bps": 0.0,
      "slippage_bps": 0.0
    },
    {
      "id": "modeled",
      "name": "Illustrative spread and slippage",
      "spread_bps": 10.0,
      "slippage_bps": 5.0
    }
  ]
}
```

Python (offline):

```python
from pathlib import Path
from strategy_backtest_agent import BacktestClient, CostScenarioConfig

client = BacktestClient()
config = CostScenarioConfig.model_validate_json(Path("customer-costs.json").read_text())
result = client.costs(config=config, demo=True)
print(result.summary())
for item in result.results:
    print(item.id, item.execution.fee_rate, item.train.result.total_return_percent, item.return_difference_pp)
with Path("result.json").open("x", encoding="utf-8") as stream:
    stream.write(result.to_json())
result.save_report("report.md")
result.save_report("report.json", format="json")
```

CLI, using the same saved config (**Binance/network required**; no AI.):

```bash
set -C
strategy-backtest costs --config customer-costs.json --json > result.json
strategy-backtest report --input result.json --format markdown --output report.md
strategy-backtest report --input result.json --format json --output report.json
```

Expected: one scenario result with applied execution settings, Train financials
and `return_difference_pp` (scenario return minus first-scenario return). All scenarios
share strategy, data and indicators but have independent portfolios. Later Test is
reserved and not evaluated. Modeled spread/slippage are assumptions, not historical
Binance quote observations or optimized recommendations.

Next: read every result (including negative and zero-trade cases), costs and methodology
warnings in `report.md`; retain `result.json` as the raw source, and `report.json` as
normalized evidence. Use new filenames/directories for reruns.

### 6. Fixed-strategy Walk-Forward

Question: how did 1–5 predeclared fixed strategies vary across multiple chronological
Test windows? Test is the later out-of-sample (OOS) evaluation segment. Rolling Train windows keep their length; expanding Train always begins
at the first eligible evaluation candle and grows. Train is diagnostic only; no
adaptive selection/parameter optimization occurs. This example is **offline synthetic**.

Save as `customer-walk-forward.json`:

```json
{
  "symbol": "BTCUSDT",
  "timeframe": "1h",
  "period_days": 60,
  "initial_balance": 10000.0,
  "fee": 0.001,
  "execution": {
    "fee_rate": 0.001,
    "spread_bps": 10.0,
    "slippage_bps": 5.0
  },
  "evaluation_end": "2024-07-01T00:00:00Z",
  "strategies": [
    {
      "id": "rsi-30",
      "name": "RSI 14 30/70",
      "strategy": {
        "type": "rsi",
        "period": 14,
        "entry_below": 30.0,
        "exit_above": 70.0
      }
    }
  ],
  "windows": {
    "mode": "rolling",
    "train_days": 30,
    "test_days": 10,
    "step_days": 10,
    "max_folds": 10
  },
  "stitch_oos": true
}
```

Python (offline):

```python
from pathlib import Path
from strategy_backtest_agent import BacktestClient, WalkForwardConfig

client = BacktestClient()
config = WalkForwardConfig.model_validate_json(Path("customer-walk-forward.json").read_text())
result = client.walk_forward(config=config, demo=True)
print(result.summary())
print("Folds:", len(result.folds), "Trailing:", result.unused_trailing_candles)
for item in result.summaries:
    print(item.strategy_id, item.positive_test_folds, item.median_test_return_percent)
with Path("result.json").open("x", encoding="utf-8") as stream:
    stream.write(result.to_json())
result.save_report("report.md")
result.save_report("report.json", format="json")
```

CLI, using the same saved config (**Offline synthetic**; no AI.):

```bash
set -C
strategy-backtest walk-forward --config customer-walk-forward.json --demo --json > result.json
strategy-backtest report --input result.json --format markdown --output report.md
strategy-backtest report --input result.json --format json --output report.json
```

Expected: complete `folds`, per-strategy/per-fold `results` with Train/Test, unused
trailing candles and Test-only `summaries`. Every Train and Test starts with independent
initial capital and no carried position. Positive means return > 0; outperformance
means excess > 0. Medians/extrema are unweighted fold statistics; trade counts sum,
win rates/profit factors are not pooled, and drawdowns are not a continuous portfolio
statistic. `stitch_oos=true` compounds normalized independent Test returns into an
index starting at 100 at fold endpoints. It requires contiguous Tests, cannot stitch
gaps, does not carry positions, and has no continuous drawdown interpretation.

Next: read every result (including negative and zero-trade cases), costs and methodology
warnings in `report.md`; retain `result.json` as the raw source, and `report.json` as
normalized evidence. Use new filenames/directories for reruns.

### Walk-Forward window constraints

`windows.mode` defaults to `rolling`, accepts `expanding`. `train_days` and `test_days`
are required positive integers; `step_days` is positive or null (defaults to Test
length), and must be at least Test length. Durations convert to exact timeframe
candle counts, not approximate calendar windows. Each segment needs at least two candles;
Train precedes Test and Test windows never overlap. At least two **complete** folds
must fit the requested history. `max_folds` defaults to 50, allowed 2–100. Exceeding
it is rejected rather than silently truncating; change the declared protocol.
Incomplete final windows are omitted and trailing candles counted. `stitch_oos` defaults
to false and requires step == Test length. Changing a fixed demo evaluation end away
from `2024-07-01T00:00:00Z` is rejected.

### Run all six together

[`examples/customer_research.py`](https://github.com/changelia/strategy-backtest-agent/blob/main/examples/customer_research.py)
is a complete self-contained synthetic script. It constructs configs in memory, runs
**all six** modes, prints summaries, and saves a separate raw JSON/Markdown/report JSON
set per mode. With the package installed, download into a fresh directory:

```bash
mkdir six-mode-run && cd six-mode-run
set -C
curl -fsSL https://raw.githubusercontent.com/changelia/strategy-backtest-agent/main/examples/customer_research.py > customer_research.py
python customer_research.py
```

Retrieving the script requires GitHub network access; execution requires neither
Binance nor OpenAI. Expected output includes all six mode labels and one summary
heading per mode, followed by the output directory. Examples are checkout/download
files, not installed runtime resources. For parse-inspect-run and direct natural-language
examples for each supported mode, see [AI](AI.md#other-research-modes) and
[CLI](CLI.md#natural-language-research-requests); costs remains config-only.

## Parameter grids and cost scenarios

A sensitivity `ParameterSpec` selects an exact numeric DSL field and exactly one
candidate source. These are **individual parameter items**, not standalone run configs:

```json
{"path":"entry.right.value","values":[25.0,30.0,35.0]}
```

```json
{"path":"entry.left.period","coupled_paths":["exit.left.period"],"range":{"start":10,"stop":20,"step":5}}
```

```json
{"path":"exit.right.value","nearby":{"steps":1}}
```

- `values`: 1–25 unique numeric candidates, evaluated in declared order. Periods must
  use integer values, not `14.0`.
- `range`: `start`, `stop`, positive `step`; inclusive stop must be exactly reachable.
  Period ranges require integer bounds/step.
- `nearby`: default `steps=1`, allowed 1–12; produces base ± offsets including base.
  Default step is 1 for periods and 5 for RSI thresholds; other constants (including
  multipliers) need explicit positive step.
- At most 3 parameter dimensions and 25 Cartesian variants. Invalid combinations
  reject the whole grid; they are not clipped/discarded. RSI thresholds stay 0–100;
  simple RSI entry must stay below exit; MACD fast must stay below slow.
- Supported targets: indicator `period`; MACD `fast_period`, `slow_period`,
  `signal_period`; Bollinger `multiplier`; numeric operand `value`. Nested paths include
  `entry.conditions.0.left.period`; indices are zero-based. No arbitrary expressions.
- Repeated indicators do not mutate together unless exact `coupled_paths` are provided.
  Coupled fields must have matching operand kinds/parameters/base values and the same
  numeric field. All paths must be unique across dimensions/couplings.

Sensitivity observations require at least 5 trades for descriptive neighbor comparison
and use a 5 pp similarity tolerance. These are conventions, not significance tests.
The grid's positive-return percentage describes variants, not future win probability.

Cost scenarios require unique IDs/names, 2–8 ordered entries. `spread_bps` and
`slippage_bps` default to zero. Scenario `fee_rate` defaults to null (inherit shared
fee), or accepts `0 <= fee_rate < 1`. The first scenario must have zero spread/slippage;
its inherited fee can be nonzero. Shared `execution` may declare fee but cannot contain
nonzero spread/slippage in a cost scenario config: put those in each scenario.
No scenario is selected or recommended. There is no hidden gross/net recalculation.

## Strategy DSL and indicators

The Strategy DSL is a small typed rule language, not executable Python.
A `RuleStrategy` has `type="rules"`, `entry` and `exit`. A comparison has
`type="comparison"`, `left`, `operator`, `right`. Operands:

| Model / JSON fields | Meaning and limits |
| --- | --- |
| `Price` / `{"type":"price"}` | Completed candle **close**, not bid/ask or an execution instruction. |
| `Value` / `{"type":"value","value":30.0}` | Finite numeric constant. |
| `Indicator` / `type="indicator", name="rsi"/"sma"/"ema", period` | RSI integer 2–500; SMA/EMA integer 2–1000; period required. |
| `MACDIndicator` / `name="macd", fast_period, slow_period, signal_period, component` | Defaults 12,26,9; integer periods 1–1000, fast < slow; component `macd` (default), `signal`, `histogram`. |
| `BollingerIndicator` / `name="bollinger", period, multiplier, component` | Period 20 default, integer 1–1000; positive finite multiplier default 2.0; **required** component `upper`, `middle`, `lower`. |
| `ATRIndicator` / `name="atr", period` | Period 14 default, integer 1–1000. No component field. Uses high, low and previous close. |

All indicator operands retain `type="indicator"`. Names and component values are
case-sensitive. Comparisons support only `<`, `<=`, `>`, `>=`. Groups use
`{"type":"and","conditions":[...]}` or `type="or"`, with 1–20 children,
maximum rule depth 5 (root depth 1), and at most 20 comparisons across entry+exit.
These bracket examples describe structure; use the complete runnable Python below.

Complete offline example of RSI **AND** ATR (entry below 30 and ATR > 100), with RSI
exit above 70. High/low matter to ATR, so the threshold may pass every RSI entry on
some data; that does not imply a no-op filter:

```python
from strategy_backtest_agent import (
    AIStrategyConfig, ATRIndicator, BacktestClient, Comparison, Group, Indicator,
    RuleStrategy, Value,
)

config = AIStrategyConfig(
    symbol="BTCUSDT", timeframe="1h", period_days=30,
    strategy=RuleStrategy(
        entry=Group(type="and", conditions=[
            Comparison(left=Indicator(name="rsi", period=14), operator="<", right=Value(value=30.0)),
            Comparison(left=ATRIndicator(name="atr", period=14), operator=">", right=Value(value=100.0)),
        ]),
        exit=Comparison(left=Indicator(name="rsi", period=14), operator=">", right=Value(value=70.0)),
    ),
)
result = BacktestClient().run(config=config, demo=True)
print(result.summary())
```

For MACD line versus signal, place two `MACDIndicator` operands with identical periods
and components `macd` and `signal` in a `Comparison`. Price below a lower band uses
`Price()` on the left, `BollingerIndicator(name="bollinger", component="lower")` on
the right. Numeric thresholds use `Value`. A state comparison is evaluated at every
completed candle; “above” does not mean “just crossed above.” Crossovers, arbitrary
Python functions, shorts, leverage, stops/targets, multi-symbol portfolios, live orders
and forecasts are unsupported. Existing complete advanced configs remain available:
[comparison](../examples/advanced-comparison.json),
[validation](../examples/advanced-validation.json),
[sensitivity](../examples/advanced-sensitivity.json),
[costs](../examples/advanced-costs.json), [Walk-Forward](../examples/advanced-walk-forward.json).

## Metrics and report interpretation

| Field | Unit / interpretation |
| --- | --- |
| `initial_balance`, `final_balance` | Quote currency; account reset per independent strategy/segment. |
| `total_return_percent` | `(final / initial - 1) × 100`, including modeled fills/fees/liquidation. |
| `buy_and_hold_return_percent` | Net first evaluation open to final close under the same execution costs. |
| `excess_return_pp` | Strategy return minus net benchmark, **percentage points**, not percent change. |
| `max_drawdown_percent` | Signed peak-to-trough percent, nonpositive; sampled opens/closes, not intrabar extremes. |
| `total_trades`, `winning_trades`, `losing_trades` | Completed round trips; zero-PnL trades need not count as winners/losers. |
| `win_rate` | Percent of completed trades; undefined with none. |
| `profit_factor` | Sum of positive completed-trade PnL / absolute sum of negative PnL; null without a losing denominator, not infinity or zero. |
| `costs.fees`, modeled spread/slippage totals | Quote currency; actual deterministic charges vs modeled fill adjustments. Not bps. |

See the [mode-specific Python access table](PYTHON_API.md#result-types-and-metric-access)
for nested result paths. Never flatten Train/Test, variants, cost scenarios or folds
into one continuous account. Negative and missing results remain visible.

Raw research JSON records inputs and engine results. Normalized report JSON records
`evidence`, `observations`, source/evidence SHA256, warnings and report/AI status.
Markdown renders those values in readable tables. A report never reruns research or
fetches market data. Default status is `deterministic`; optional AI statuses are
`ai_accepted`, `ai_unavailable`, `ai_rejected`. Failed AI leaves deterministic evidence
available. Unknown IDs, unsupported numerical claims, forecasts and advice are rejected.
Evidence validation cannot prove arbitrary prose or authenticate the original research.

## Execution, initialization and reproducibility

Signals use a completed candle; fills use the next candle's open. First segment open
cannot execute a prior segment signal; final signals do not escape the segment. Open
positions liquidate once at the segment's final close. Fractional quantities, full fills
and unlimited liquidity are assumed. Open positions are marked at reference prices;
spread/slippage costs apply on fills without being charged again as cash fees.
Buy & Hold applies the same costs. Example: full spread 20 bps and slippage 10 bps
makes buy reference 100 fill at 100.20 and sell reference 110 fill at 109.78, before fees.

The synthetic interval ends at 2024-07-01 UTC. Research/DSL history includes required
prior warm-up: RSI p+1, SMA p, EMA 5p, MACD 10(slow+signal), Bollinger p, ATR 20p.
MACD uses first-close price EMA seeds and a signal seed at first available MACD;
Bollinger uses population standard deviation (`ddof=0`); ATR starts True Range with
high−low, seeds with mean TR, then Wilder smoothing. Insufficient history is rejected.
See [exact advanced conventions](../ARCHITECTURE.md#advanced-indicator-conventions).

Initialization policies differ deliberately: comparison/validation retain shared
legacy RSI/SMA/EMA seed semantics, so adding a longer **legacy** indicator can change
those legacy seeds. Advanced indicators use local anchors; sensitivity uses indicator-
local seeds at Train start; Walk-Forward continues local initialized series causally
across folds, without reseeding at every split. These finite-history seeds are not
infinite-history convergence; threshold-adjacent signals can depend on initialization.
See [Walk-Forward policy](../ARCHITECTURE.md#fixed-strategy-walk-forward-analysis) and
[sensitivity policy](../ARCHITECTURE.md#deterministic-parameter-sensitivity).

Reproduce using the same validated config, resolved UTC boundaries, candle values
(including warm-up), initialization/execution policy and software version. Metadata
records source, dependencies, seed boundaries and candle digest where supported. A
source-provided candle hash is provenance, not cryptographic proof of truthful results.
Report source hashes use input bytes; deterministic evidence uses canonical serialization.
Identical raw input bytes and report version produce identical deterministic content.
AI interpretation is not promised byte-identical.

Train-only grids/cost scenarios and repeatedly inspected historical Tests can overfit.
Multiple positive OOS folds do not establish independence, predictive value, robustness
or future profitability. Synthetic data is for workflow checks, not market evidence.
