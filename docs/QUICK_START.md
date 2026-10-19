# Quick Start

This guide starts with the published package and the installed terminal command. It
uses synthetic offline candles first. Python API and Poetry contributor setup are
covered in [Python API](PYTHON_API.md) and [Contributing](../CONTRIBUTING.md).

## 1. Install the package

Requirements: Python `>=3.12,<4.0`, pip, and a POSIX environment for safe creation of
configuration and report files. CI and the isolated installation checks use Python
3.12; later versions allowed by the declared range are not separately verified here.
Windows file output is not supported.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install strategy-backtest-agent==1.2.0
strategy-backtest --help
```

The PyPI distribution is `strategy-backtest-agent`; the installed import is
`strategy_backtest_agent`; the executable is `strategy-backtest`. Version 1.2.0 is
published. The README stored in an already uploaded wheel is fixed at upload time;
GitHub documentation changes do not alter that old distribution description.

## 2. Make a clean research directory

Do not run the following in a directory containing files you want to preserve. Config
and report output paths refuse to overwrite existing files. The shell option `set -C`
also protects the raw result file written with `>`.

```bash
mkdir customer-research
cd customer-research
strategy-backtest doctor
strategy-backtest init --type backtest --output backtest-config.json
```

Expected: doctor reports offline functionality available; missing optional OpenAI
credentials do not block it. `init` creates a validated RSI(14) configuration with
RSI entry below 30 and exit above 70, a 0.001 fee fraction, 10 bps full spread and 5
bps slippage per side. Review the created JSON before running. Edit fields with a text
editor if needed; use a new filename for another template. Only backtest, compare,
validate and walk-forward templates are available through `init`.

## 3. Run and save raw results

```bash
set -C
strategy-backtest --config backtest-config.json --days 3 --demo --json > backtest-result.json
```

Expected: `backtest-result.json` contains one valid JSON object with the raw result,
evaluation details and execution-cost metadata. The command uses fixed synthetic
candles ending at 2024-07-01 UTC. This is an offline command: no Binance or OpenAI
request occurs. For a readable console summary, omit `--json` and the redirection.

## 4. Generate reports from the saved result

```bash
strategy-backtest report --input backtest-result.json --format json --output report.json
strategy-backtest report --input backtest-result.json --format markdown --output report.md
```

Expected: `report.json` is normalized report data with evidence, observations,
provenance and status; `report.md` is its readable rendering. These differ from the raw
`backtest-result.json`. Report generation validates this saved input; it does not fetch
market data or rerun the backtest. Repeating report generation to a new filename with
the same input and version produces the same report content.

The output path is exclusive. If a file already exists, choose a new name or a fresh
directory rather than deleting or overwriting it. For Markdown with optional AI
interpretation, use `--ai`; it may make a paid OpenAI request. The deterministic report
still works without a key.

## 5. Choose another research workflow

`init` creates complete configurations for the following matching commands:

```bash
strategy-backtest init --type compare --output compare-config.json
strategy-backtest compare --config compare-config.json --demo --json > compare-result.json

strategy-backtest init --type validate --output validation-config.json
strategy-backtest validate --config validation-config.json --demo --json > validation-result.json

strategy-backtest init --type walk-forward --output walk-forward-config.json
strategy-backtest walk-forward --config walk-forward-config.json --demo --json > walk-forward-result.json
```

Comparison runs each fixed strategy in an independent portfolio on shared candles.
Validation runs chronological Train then Test with separate portfolios; a strategy
chosen after looking at Test is not independently held out. Walk-Forward repeats
predeclared fixed strategies over complete folds; Train is diagnostic, Test folds reset
capital, and summaries use Test results only. None of these workflows performs
automatic parameter optimization or chooses a winner.

For sensitivity, first download the complete example config into this fresh directory.
This example requires network access both to retrieve that file and, when running,
to fetch Binance candles:

```bash
set -C
curl -fsSL https://raw.githubusercontent.com/changelia/strategy-backtest-agent/main/examples/sensitivity.json > sensitivity-config.json
strategy-backtest sensitivity --config sensitivity-config.json --json > sensitivity-result.json
```

For cost scenarios, download the complete config and run the config-only CLI command.
It also fetches Binance candles:

```bash
set -C
curl -fsSL https://raw.githubusercontent.com/changelia/strategy-backtest-agent/main/examples/execution-scenarios.json > costs-config.json
strategy-backtest costs --config costs-config.json --json > costs-result.json
```

These two CLI commands fetch Binance candles. They have no `--demo` switch. Their
configs declare a fixed UTC evaluation end to make the requested boundary explicit,
but exact replay still depends on receiving identical candles. Run them only when
network access is available and you intend a historical data request. For all options,
see [CLI Reference](CLI.md); for methodology and result interpretation, see
[Research Guide](RESEARCH_GUIDE.md).

## 6. Use historical Binance candles

The demo is synthetic. To use public Binance candle history, omit `--demo` from a
supported research command. For example:

```bash
strategy-backtest compare --config compare-config.json --json > binance-result.json
```

This makes an application network request to Binance; availability depends on network,
rate limits, region and history. The example’s evaluation end may be old or outside
available data. Edit `evaluation_end` to a deliberate UTC timestamp and use a new
result filename before running. A fixed end does not freeze the provider’s historical
data; the report records a candle digest for provenance, not proof of authenticity.

Fees are decimal fractions per side (`0.001` = 0.1%), not a percent number. Spread is
the full spread in bps, with half modeled at each side; slippage bps are adverse per
side. `period_days` is a research configuration field. For single backtests, duration
is supplied as the CLI `--days` option. Dates are timezone-aware and evaluated in UTC.

## Next steps

- [Research Guide](RESEARCH_GUIDE.md) explains six workflows, rules, metrics, costs,
  warm-up and reproducibility.
- [Python API](PYTHON_API.md) covers in-memory execution, typed results, templates,
  reports, async calls and custom data providers.
- [AI Guide](AI.md) covers optional paid parsing and interpretation.
- [Troubleshooting](TROUBLESHOOTING.md) covers common installation and runtime errors.
