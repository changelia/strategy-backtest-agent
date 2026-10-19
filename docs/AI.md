# Optional AI: Your Key and Your Strategy

[Home](../README.md) · [Quick Start](QUICK_START.md) · [Python API](PYTHON_API.md) · [CLI](CLI.md)

AI has two optional roles: parse supported natural-language rules into validated
configuration, and select evidence-linked explanations for an existing report.
Python calculates indicators, signals, trades, accounting and metrics. AI does not
invent prices, generate executable strategies, optimize parameters or predict returns.

## Contents

- [Create and configure a key](#create-and-configure-a-key)
- [Setting precedence and empty values](#setting-precedence-and-empty-values)
- [Parse, inspect and execute in Python](#parse-inspect-and-execute-in-python)
- [Direct natural-language execution](#direct-natural-language-execution)
- [Other research modes](#other-research-modes)
- [Terminal journey](#terminal-journey)
- [Interpret an existing report](#interpret-an-existing-report)
- [Failures and boundaries](#failures-and-boundaries)

## Create and configure a key

Prerequisites: installed package, an OpenAI API account, and network access for AI.
Create a key in your own [OpenAI API project](https://platform.openai.com/api-keys).
Follow the [official OpenAI quickstart](https://developers.openai.com/api/docs/quickstart)
for account setup. Check your API billing, access and usage controls; account/model
availability is not verified by this package. Never share or commit a real key.

Use explicit Python configuration locally:

```python
from strategy_backtest_agent import BacktestClient

client = BacktestClient(api_key="YOUR_OPENAI_API_KEY", model="gpt-4.1-mini")
print(client.doctor().api_key_present)  # Presence only; no request.
```

Expected after replacing the placeholder: `True`. Construction does not validate the
key or contact a provider. Do not use the placeholder for a real request.

Or set environment variables in the terminal before starting Python or the CLI:

```bash
export OPENAI_API_KEY="YOUR_OPENAI_API_KEY"
export OPENAI_MODEL="gpt-4.1-mini"
```

The default in this package is `gpt-4.1-mini`. OpenAI documents
[GPT-4.1 mini](https://developers.openai.com/api/docs/models/gpt-4.1-mini) and structured
outputs, but access, quotas and accepted model identifiers depend on your account and
provider. The package uses the OpenAI Responses API with Pydantic structured output.
An environment override is configuration, not a guarantee every named model works.

For local `.env` configuration, create a file named `.env` containing placeholders
replaced privately with your own values:

```dotenv
OPENAI_API_KEY=YOUR_OPENAI_API_KEY
OPENAI_MODEL=gpt-4.1-mini
```

Add `.env` to your own project's `.gitignore`. The CLI searches the current directory
and parents and automatically loads the nearest `.env` at startup with `override=False`.
Already-set environment variables win, including empty ones. Set
`PYTHON_DOTENV_DISABLED=1` to disable automatic CLI dotenv loading.
Python clients do **not** search/load `.env` automatically. Opt in explicitly:

```python
from strategy_backtest_agent import BacktestClient

client = BacktestClient(dotenv_path=".env")
print(client.doctor().api_key_present)
```

This reads the named UTF-8 file without changing `os.environ`; malformed/missing
explicit files raise a sanitized `BacktestClientError`. Python's explicit
`dotenv_path` is independent of the CLI automatic-loading switch.

## Setting precedence and empty values

For Python, resolution occurs once at **client construction**, separately per setting:

1. Explicit non-`None` `api_key` / `model` constructor value.
2. `OPENAI_API_KEY` / `OPENAI_MODEL` already in the process environment.
3. Values in explicitly supplied `dotenv_path`.
4. No key, or the shared model default `gpt-4.1-mini`.

`None` means “unspecified”: `api_key=None` does not disable environment credentials.
An explicit `""` blocks fallback. An empty/whitespace key prevents parsing; an empty
model fails model validation instead of using the default. Deterministic operations
remain usable. An empty environment setting also takes precedence over dotenv.

The client captures settings, so later changes to environment variables do not update
that instance. Construct a new client deliberately. Clients pass their settings per
request and do not temporarily mutate process environment. No key is included in
results, evidence or reports. Diagnostics show presence/source, never a key fragment.

## Parse, inspect and execute in Python

Prerequisites: package installed, your key supplied explicitly below, fresh output
directory. Save this as `my_ai_research.py`, replace the placeholder locally, then run
`python my_ai_research.py`. **The parse is paid OpenAI; the following demo execution
is synthetic and offline.** Configuring the client alone makes no request.

```python
from pathlib import Path
from strategy_backtest_agent import AIStrategyConfig, BacktestClient

client = BacktestClient(api_key="YOUR_OPENAI_API_KEY", model="gpt-4.1-mini")
config = client.parse(
    "Backtest BTCUSDT on 1h candles for 30 days with initial balance 10000, "
    "fee 0.001 per side, full spread 10 bps and slippage 5 bps per side. "
    "Buy when MACD line (12,26,9) is above its signal line and RSI(14) < 35. "
    "Sell when MACD line (12,26,9) is below its signal line."
)
assert isinstance(config, AIStrategyConfig)
print(config.model_dump_json(indent=2))
# Review the printed symbol, timeframe, period, rules and cost assumptions.
result = client.run(config=config, demo=True)
print(result.summary())
print(f"Return: {result.total_return_percent:.2f}%; trades: {result.total_trades}")
with Path("ai-raw-result.json").open("x", encoding="utf-8") as stream:
    stream.write(result.to_json())
result.save_report("ai-research.md")
result.save_report("ai-research.json", format="json")
```

Expected: validated JSON with MACD components and nested entry rules, followed by a
synthetic backtest summary and numeric metrics. Three files appear in the current
working directory. Reports are deterministic here; no second OpenAI call is requested.
For a manual pause, run the script through the printed config first, inspect it, then
execute the remaining lines. Inspect *what AI understood*, not just whether parsing
succeeded. Change rules only as part of your declared research plan.

To execute the same config on Binance history, use `client.run(config=config)` with
new output filenames. This fetches historical market data; no second parse occurs.
A configuration can also be created directly as `AIStrategyConfig` without using AI.
See [Research Guide](RESEARCH_GUIDE.md#configuration-contracts).

## Direct natural-language execution

Comparison and the other multi-stage research methods can parse and execute directly.
Prerequisite: environment credentials; **paid OpenAI**, followed here by synthetic data:

```python
from strategy_backtest_agent import BacktestClient

client = BacktestClient()
result = client.compare(
    "Compare RSI 25/70 and RSI 30/70 on BTCUSDT 1h over 30 days with fee 0.001.",
    demo=True,
)
print(result.summary())
result.save_report("direct-comparison.md")
```

Expected: a two-strategy comparison summary and one new Markdown report. Without demo,
execution also fetches Binance history. Direct `validate`, `sensitivity` and
`walk_forward` calls similarly accept requests; costs is config-only.

**Known v1.2.0 single-run issue:** `client.run(text, demo=True)` fails when the parser
returns a DSL `RuleStrategy`: strict Python validation rejects the serialized
`evaluation_period.requested_start/end` timestamps. Direct legacy RSI output does not
have those fields, so it can succeed. Do not rely on the AI selecting a legacy shape.
The recommended single-strategy route is `parse()` followed by `run(config=config)`
from the previous section; that path preserves the same rules and avoids the defect.
A complete diagnostic example of the convenience call (paid parsing):

```python
from strategy_backtest_agent import BacktestClient, ValidationError

client = BacktestClient()
try:
    result = client.run(
        "Backtest BTCUSDT on 1h for 30 days. Buy when price is below the lower "
        "Bollinger Band (20,2) and sell when price is above the middle band.",
        demo=True,
    )
    print(result.summary())
except ValidationError:
    print("Known direct DSL validation issue: use parse(), then run(config=parsed_config).")
```

The error is a product defect, not an invalid strategy or a reason to edit source
metrics. No runtime fix is included in this documentation-only work. This example
intentionally diagnoses the limitation; it does not claim a successful backtest.

## Other research modes

`parse(workflow=...)` supports the following selectors. Inspect the returned config
before passing it to the matching method. Example requests:

| Selector / execution | Meaningful request (paid parsing) |
| --- | --- |
| `compare` / `compare` | Compare RSI 25/70 and RSI 30/70 on BTCUSDT 1h over 30 days with fee 0.001. |
| `validate` / `validate` | Validate RSI 30/70 on BTCUSDT 1h over 60 days using chronological 70/30 Train/Test. |
| `sensitivity` / `sensitivity` | Analyze RSI entry thresholds 25, 30 and 35 with exit 70 on BTCUSDT 1h over 60 days, Train ratio 0.7. |
| `walk-forward` / `walk_forward` | Run rolling walk-forward RSI 30/70 on BTCUSDT 1h over 60 days, Train 30 days, Test 10 days, step 10 days. |

Complete comparison example, with environment credentials configured and new paths:

```python
from strategy_backtest_agent import BacktestClient, ComparisonConfig

client = BacktestClient()
config = client.parse(
    "Compare RSI 25/70 and RSI 30/70 on BTCUSDT 1h over 30 days with fee 0.001.",
    workflow="compare",
)
assert isinstance(config, ComparisonConfig)
print(config.model_dump_json(indent=2))
result = client.compare(config=config, demo=True)
print(result.summary())
result.save_report("comparison-ai.md")
```

Expected: a validated shared config and two independent strategy results. Direct
`client.compare("...")`, `validate("...")`, `sensitivity("...")` and
`walk_forward("...")` also parse then execute, fetching Binance by default.
Requests must be nonempty and at most 8000 characters. Costs has **no**
natural-language parser; use `CostScenarioConfig`.

## Terminal journey

Prerequisites: installed CLI, your key configured through environment or local `.env`,
Binance/OpenAI network access and a fresh working directory. Unlike Python execution,
CLI `ai` has no demo option. This journey makes **both paid OpenAI and Binance calls**:

```bash
strategy-backtest doctor
set -C
strategy-backtest ai \
  'Backtest BTCUSDT on 1h for 30 days. Buy when RSI(14) < 30 and sell when RSI(14) > 70.' \
  --spread-bps 10 --slippage-bps 5 --json > ai-result.json
strategy-backtest report --input ai-result.json --format markdown --output ai-report.md
strategy-backtest report --input ai-result.json --format json --output ai-report.json
```

Expected: one raw result JSON (including the input/parsed configuration envelope) and
two deterministic reports. Read `parsed_strategy` to check what was understood.
Report generation above makes no further provider call. Terminal `compare`, `validate`,
`sensitivity` and `walk-forward` also accept a quoted request instead of `--config`.
See [CLI Reference](CLI.md#natural-language-research-requests) for complete commands.
There is no CLI parse-only command; use Python `parse()` to inspect before execution.

## Interpret an existing report

Prerequisites: an existing raw result file from the previous section and credentials.
This is a separate **paid OpenAI** request; it neither fetches candles nor reruns research:

```bash
strategy-backtest report --input ai-result.json --format markdown --ai --output interpreted.md
```

The equivalent Python journey can stay synthetic for the research stage:

```python
import json
from strategy_backtest_agent import BacktestClient, BacktestConfig

client = BacktestClient()  # Environment credentials, or explicit settings.
result = client.run(config=BacktestConfig(), days=30, demo=True)
report = client.report(result, format="json", ai=True, output="interpreted.json")
metadata = json.loads(report)
print(metadata["status"])
print(metadata["warnings"])
```

Expected status is `ai_accepted`, `ai_unavailable` or `ai_rejected`, with deterministic
evidence retained in every case. AI sees selected normalized evidence and observations,
not the raw OHLCV history. It selects approved explanations/questions with known IDs;
free-form numerical narratives, invented numbers, predictions and advice are rejected.
This is constrained interpretation, not proof of arbitrary prose or source authenticity.

## Failures and boundaries

| Situation | Behavior and next action |
| --- | --- |
| Missing/empty key during parse | `StrategyParseError`; configure your own key or use structured configs. |
| Invalid key, quota/rate limit, timeout/network or unsupported model | Sanitized parsing error; privately check your OpenAI account/model, billing and connectivity. No research executes if parsing fails. |
| Unsupported/ambiguous strategy | Rejection; use supported level rules and specify symbol/period. Crossovers, stops, shorts, leverage and forecasts are unsupported. |
| Missing key/provider failure during interpretation | `ai_unavailable`; deterministic report still generated. |
| Invalid structured interpretation/grounding | `ai_rejected`; deterministic report retained. |
| Successful interpretation | `ai_accepted`; numerical evidence still comes from Python. |

CLI report prints an AI fallback notice to stderr and returns success if the deterministic
report was generated. Python report returns the string; inspect JSON status/warnings.
Model configuration/key presence is not proof of authorization, funding or availability.
Requests use a 30-second SDK timeout and no automatic retries. No live AI request was
made while validating these documentation examples; API behavior is covered with mocks.

See [Troubleshooting](TROUBLESHOOTING.md), [Python API](PYTHON_API.md) and
[Research Guide](RESEARCH_GUIDE.md) for the supported product boundaries.
