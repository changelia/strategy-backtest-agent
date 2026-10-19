# Customer Documentation Coverage

This is a maintainer checklist for the customer guides. Contracts were inspected in
the root exports, client, models, all CLI parsers, init/doctor, report renderer and
installed smoke helpers. Implemented/published baseline: package v1.2.0; these guide
changes do not change runtime behavior or already-uploaded PyPI descriptions.

## Public client operations

| Operation | Customer documentation | Complete example |
| --- | --- | --- |
| constructor | [API settings](PYTHON_API.md#installation-and-client-configuration), [AI precedence](AI.md#setting-precedence-and-empty-values) | README explicit key; AI environment/dotenv examples |
| `run` / `arun` | [API](PYTHON_API.md), [backtest](RESEARCH_GUIDE.md#1-single-strategy-backtest) | `examples/customer_backtest.py`, `examples/customer_async.py` |
| `compare` / `acompare` | [comparison](RESEARCH_GUIDE.md#2-strategy-comparison) | Complete Python/CLI block and customer-comparison.json |
| `validate` / `avalidate` | [validation](RESEARCH_GUIDE.md#3-chronological-traintest-validation) | Complete Python/CLI block and customer-validation.json |
| `sensitivity` / `asensitivity` | [sensitivity](RESEARCH_GUIDE.md#4-parameter-sensitivity) | Complete Python/CLI block and customer-sensitivity.json |
| `costs` / `acosts` | [costs](RESEARCH_GUIDE.md#5-execution-cost-scenarios) | Complete Python/CLI block and customer-costs.json |
| `walk_forward` / `awalk_forward` | [Walk-Forward](RESEARCH_GUIDE.md#6-fixed-strategy-walk-forward) | Complete Python/CLI block and customer-walk-forward.json |
| `parse` / `aparse` | [AI journey](AI.md#parse-inspect-and-execute-in-python), [async API](PYTHON_API.md#async-applications) | README parse-inspect-run, customer_ai.py; workflow request table |
| `report` / `areport` | [results/reports](PYTHON_API.md#results-serialization-and-reports), [AI interpretation](AI.md#interpret-an-existing-report) | Direct result reports, saved raw JSON reuse, async script |
| `template` | [templates/doctor](PYTHON_API.md#templates-and-doctor-workflow-differences) | Validated model, edited mapping, explicit output saving |
| `doctor` | [diagnostics](PYTHON_API.md#templates-and-doctor-workflow-differences) | Structured diagnostics, explicit config validation |
| `ClientResult` | [result types](PYTHON_API.md#result-types-and-metric-access), [serialization](PYTHON_API.md#public-operation-reference) | Metric access per mode; summary, dump/JSON, raw save/reuse, save_report |
| custom `MarketDataProvider` | [provider tutorial](PYTHON_API.md#custom-market-data-providers) | `examples/customer_provider.py`, complete validated candles and prior history |

Async variants share their sync signatures and return types. Existing-loop exceptions
are documented: only sync execution/parsing wrappers and AI report calls reject it;
template, doctor and deterministic reports remain usable. AI/candle provider examples
are labelled by actual network behavior, not by whether a key is configured.

## CLI commands and configuration contracts

| Command | Config / input | Usage example and options |
| --- | --- | --- |
| root | `BacktestConfig`; legacy flags | [CLI root](CLI.md#root-backtest), Quick Start, customer-backtest.json |
| `ai` | Quoted supported request; paid parse + Binance | [AI terminal journey](AI.md#terminal-journey), [CLI ai](CLI.md#ai) |
| `init` | Four exact types + new output | [CLI init](CLI.md#init), Quick Start |
| `doctor` | Optional explicit four-type config pair | [CLI doctor](CLI.md#doctor), exit codes and limits |
| `report` | One raw research result, not config | [CLI report](CLI.md#report), deterministic/AI output paths |
| `compare` | `ComparisonConfig` or quoted request | [CLI](CLI.md#comparison), full Research Guide JSON/Python/CLI |
| `validate` | `ValidationConfig` or quoted request | [CLI](CLI.md#validation), full Research Guide JSON/Python/CLI |
| `sensitivity` | `SensitivityConfig` or quoted request | [CLI](CLI.md#sensitivity), full Research Guide JSON/Python/CLI; no demo flag |
| `costs` | `CostScenarioConfig` only | [CLI](CLI.md#cost-scenarios), full Research Guide JSON/Python/CLI; no AI/demo |
| `walk-forward` | `WalkForwardConfig` or quoted request | [CLI](CLI.md#walk-forward), full Research Guide JSON/Python/CLI |
| Python single DSL | `AIStrategyConfig` | Full customer-ai-strategy.json and Python consumer; not accepted by root CLI |

Shared `MarketConfig`/`SharedConfig`, `NamedStrategy`, `RSIStrategy`, `ExecutionConfig`,
window/grid/scenario types and validated rule operands are explained in
[configuration fields](RESEARCH_GUIDE.md#configuration-contracts),
[grids/scenarios](RESEARCH_GUIDE.md#parameter-grids-and-cost-scenarios), and
[DSL/indicators](RESEARCH_GUIDE.md#strategy-dsl-and-indicators). Public helper/result
models are grouped by role in the Python reference. They do not add CLI consumers.

## Validation scope

- Offline examples: installed wheel, outside checkout, credential-free, socket guard.
- Complete config files: actual Pydantic models; nested rules/advanced operands covered.
- CLI: all help parsers, root/config research, init/doctor, raw JSON, Markdown/JSON reports.
- Six modes, async and custom provider: complete independent scripts.
- OpenAI examples: mocked request boundary and existing regression tests; no paid request.
- Binance examples: actual parser/model/implementation inspection and mocked provider
  coverage; no live market call during documentation validation.
- Packaging: fresh isolated wheel/sdist build, strict Twine, archive checker and separate
  clean installs with the existing packaging orchestration.

The final delivery records exact execution results. Live OpenAI authorization/model
availability and live Binance availability are intentionally not verified here.
No future features are documented as present. New GitHub example links become publicly
available after the documentation branch is merged; example files are not wheel resources.

## Discovered product defect: direct natural-language DSL backtest

Installed v1.2.0 reproduction: mock only `ai.parser.parse_strategy` to return the
validated `examples/customer-ai-strategy.json` (a RuleStrategy), then call
`BacktestClient().run("Backtest BTCUSDT on 1h for 30 days using RSI 30/70", demo=True)`.
No network is needed to reproduce. `CLIBacktest.model_validate(backtest_payload(...))`
in `client.arun` rejects string timestamps in `evaluation_period` because the nested
model is strict. `run(config=parsed_config, demo=True)` uses JSON-mode validation and
succeeds with the same strategy; direct legacy RSI succeeds without that metadata.

Smallest proposed runtime correction for a separate task: validate the serialized
payload in JSON mode consistently with the config path, retaining the original AI
source envelope, financial values and report metadata; add a direct RuleStrategy
natural-language regression. No runtime fix is included here. This remains a product
blocker for claiming universal direct natural-language single-strategy parity.

## Review and validation record

Verified 2026-10-19 UTC. Starting branch `docs/customer-guides` at
`235db1beff44872a8a38e1f565036cc7d319f224`. Read-only HTTPS ref inspection confirmed
main `b4053587ac80b3e12f13d0b8f1b1095e7a56a27b` and annotated v1.2.0 dereferencing to
that main commit. A direct no-cache request to
[official PyPI JSON](https://pypi.org/pypi/strategy-backtest-agent/json) confirmed
latest 1.2.0 and both wheel/sdist present. A cached web reader returned older 1.1.0
metadata; the direct response was used for publication statements.

Commands run from the checkout:

```bash
poetry run pytest -q
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy
poetry check --lock
```

Results: 1,425 tests passed; Ruff passed; 126 Python files formatted; mypy passed for
120 source files; Poetry lock validation passed. No financial/runtime code, dependencies,
version, report schema or packaging policy changed.

Existing isolated validation was invoked with the temporary packaging-tool interpreter:

```bash
python tests/packaging_ci.py --checkout /absolute/checkout --work /physical/external/fresh-work
```

The helper runs `python -m build --sdist --wheel --verbose`, `python -m twine check
--strict`, the distribution checker, and separate wheel/sdist virtual environments with
uncached pip source-archive installation and installed smoke checks. Tooling: Python
3.12.3, build 1.6.1, Twine 7.0.0, packaging 26.3; isolated backend poetry-core 2.5.0.
An initial sandboxed attempt failed resolving the build-dependency index. Repeating
with permitted build/install network access passed, without changing source.

Additional external installed-wheel validation covered 31 complete Python documentation
blocks, five runnable scripts, 19 example configuration files and ten JSON guide blocks.
All configurations used actual models. Fifty-five CLI commands covered every help
parser, all init types, doctor validation, the four CLI demo consumers, saved raw JSON,
both report formats, byte-identical repeats and no-overwrite failures. Application
sockets were denied and real credentials removed. AI parsing was mocked; the known
single-run DSL failure was explicitly diagnosed. Interpretation fallback and existing
mocked AI success/rejection/credential-isolation tests passed. No paid OpenAI or live
Binance request was made. All six synthetic modes, async and custom-provider examples
ran with complete reports. Local links/anchors and Python example syntax passed.

Normal customer installation remains the unpinned pip command. Validation used fresh
local artifacts to include the changed README; this is not evidence that uploaded
PyPI descriptions have changed. Public links to new guide/example files require the
usual later merge; publishing documentation metadata is a separate owner decision.

Final artifact validation passed in both clean environments: `pip check` reported no
broken requirements, imports came from each environment's site-packages, entry point
was correct, all existing installed smoke checks passed, and matching wheel/sdist raw
results and deterministic report bytes were confirmed with zero application network
attempts. Final local artifact SHA256 (version stays 1.2.0, not uploaded):

| Artifact | SHA256 |
| --- | --- |
| `strategy_backtest_agent-1.2.0-py3-none-any.whl` | `8df5746050a5934793e9978792a142f92e13bdd1488d64ae4f7c5a66c54ac178` |
| `strategy_backtest_agent-1.2.0.tar.gz` | `40971d416769e7eff9499da6e37103bb0c620939cfff78e1072fdbc75eb2d63d` |

Validation work and logs were kept outside the checkout under
`/private/tmp/sba-customer-complete.mFqbyH/`; final build/install receipts are in
`final-packaging/`. The same existing packaging orchestrator was used, not a new CI
implementation. No remote CI run, merge, push, tag or publication was performed.
