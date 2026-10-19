# Runnable Customer Examples

Install the package first (Python 3.12+, POSIX for output files):

```bash
python -m pip install strategy-backtest-agent
```

Examples are separate downloadable repository files, not installed package resources.
You can copy a complete script from GitHub's Raw view without cloning. For example,
from a new working directory:

```bash
set -C
curl -fsSL https://raw.githubusercontent.com/changelia/strategy-backtest-agent/main/examples/customer_backtest.py > customer_backtest.py
python customer_backtest.py
```

Downloading uses GitHub network access. The script then runs offline and prints a
summary/benchmark before saving raw JSON, Markdown and normalized report JSON in the
current directory. Use a separate new directory for every script/rerun; existing output
files refuse overwrite.

| Script | Prerequisites and execution | Expected output |
| --- | --- | --- |
| `customer_backtest.py` | Package only; synthetic/offline | Summary, benchmark, three new backtest files. |
| `customer_research.py` | Package only; synthetic/offline, all six modes | Six labels and summary first lines; 18 files under new `six-mode-results/`. |
| `customer_async.py` | Package only; synthetic/offline | Offline diagnostic, summary and two async reports. In notebooks `await research()` instead of nesting `asyncio.run`. |
| `customer_provider.py` | Package only; local validated hourly provider, offline | Summary, `Source: custom`, and two reports. Prior warm-up returned for the requested interval. |
| `customer_ai.py` | Your `OPENAI_API_KEY` set before starting; paid OpenAI parsing, then synthetic execution | Validated config, summary, raw JSON and two deterministic reports. No Binance fetch. |

`customer-*.json` are complete validated configs matching
[Research Guide](../docs/RESEARCH_GUIDE.md). Save/copy the config before passing its path:

- `customer-backtest.json`: `BacktestConfig`; root CLI, `--days` outside config.
- `customer-ai-strategy.json`: manually built `AIStrategyConfig`; Python `run(config=...)`.
- `customer-comparison.json`: `ComparisonConfig`.
- `customer-validation.json`: `ValidationConfig`.
- `customer-sensitivity.json`: `SensitivityConfig`.
- `customer-costs.json`: `CostScenarioConfig`.
- `customer-walk-forward.json`: `WalkForwardConfig`.

All use a deliberate fixed protocol and illustrative costs. Shared configs fix
`evaluation_end=2024-07-01T00:00:00Z`, compatible with synthetic demo execution. That
old boundary is an example, not a recommendation to use that period for market research.
CLI sensitivity/costs have no demo mode; use the Python client for their synthetic runs.
Complete matching commands, field explanations and report steps are in the guide.
Existing `advanced-*`, comparison/validation/sensitivity and execution-scenario configs
remain available for deeper examples. Inspect the corresponding model before editing.

For your own English strategy and explicit key/model setup, read [AI Guide](../docs/AI.md).
Synthetic outcomes and historical backtests do not establish future profitability.
