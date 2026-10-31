# Visual Report Data Audit

Audited 2026-10-31 against main `54f557e313b728e60ccf247fc06564551dc58a12`
(package metadata 1.2.2). This is a source/data inventory, not an implemented HTML
feature or a release assignment. Task 22's historical v1.2.0 label is not the
visualization version. No calculation, schema, dependency or package version changes
are required to record this audit.

## Sources and terminology

- [Portfolio/result models](../src/strategy_backtest_agent/models.py),
  [backtester](../src/strategy_backtest_agent/backtester.py) and
  [metric calculation](../src/strategy_backtest_agent/metrics.py).
- Native [comparison](../src/strategy_backtest_agent/comparison/models.py),
  [validation](../src/strategy_backtest_agent/validation/models.py),
  [sensitivity](../src/strategy_backtest_agent/sensitivity/models.py),
  [cost](../src/strategy_backtest_agent/costs/models.py) and
  [Walk-Forward](../src/strategy_backtest_agent/walk_forward/models.py) models.
- [CLI backtest serialization](../src/strategy_backtest_agent/services.py),
  [report adapters](../src/strategy_backtest_agent/reports/inputs.py),
  [consistency checks](../src/strategy_backtest_agent/reports/validation.py),
  [evidence extraction](../src/strategy_backtest_agent/reports/evidence.py) and
  [normalized report models](../src/strategy_backtest_agent/reports/models.py).

Paths below describe serialized native research JSON. `i` is the source list index;
join by explicit IDs where provided. For an AI single-backtest envelope, prefix all
backtest paths with `/backtest_result`; `/input` and `/parsed_strategy` remain source
metadata. Bare `BacktestResult` lacks the market/time metadata needed by the report
adapter; use complete CLI JSON or `ClientResult.to_json()`.

An available chart can use validated saved results without prices or another
backtest. A missing time series requires new engine-produced retained data. Scalars,
trade fills, indicator initialization metadata and candle hashes do not supply it.

## All six native result types

Let `B` denote a serialized `BacktestResult` at the following locations:

| Mode / actual model | Location of `B` | Boundaries and identity | Saved data sufficient for |
| --- | --- | --- | --- |
| Single / `CLIBacktest` | Root, or `/backtest_result` in `AIBacktest` | `/symbol`, `/timeframe`, `/start_time`, `/end_time`, `/candle_count`; optional `/evaluation_period/{requested_start,requested_end}` | One strategy's scalar performance, benchmark and cost bars |
| Comparison / `ComparisonResult` | `/results/i/result` | `/results/i/{id,name}`; `/configuration/strategies`; `/shared_data` | Per-strategy scalar comparison; `/ranking` and `/ranking_criterion` are existing ranking data, not a new visual ranking |
| Chronological validation / `ValidationReport` | `/results/i/train/result`, `/results/i/test/result` | `/results/i/id`; each `/results/i/train` or `/results/i/test` has `start`, `end`, `candle_count`, `warmup_candles`; `/split` | Separate Train/Test bars and interval panels; `/results/i/return_gap_pp` is Test minus Train |
| Sensitivity / `SensitivityReport` | `/results/i/train/result` | `/results/i/variant_id` joins `/variants/i/id`; `/parameters`, `/split` | Train-only parameter response, 2D heatmap when `/matrix` exists, per-variant scalar values |
| Execution costs / `CostScenarioReport` | `/results/i/train/result` | `/results/i/{id,name,execution}`; `/baseline_id`, `/split` | Train-only scenario return, difference and modeled-cost bars |
| Walk-Forward / `WalkForwardReport` | `/results/i/train/result`, `/results/i/test/result` | `/results/i/{fold_id,strategy_id}` join `/folds/i/id` and configured strategy IDs; segment boundaries; `/summaries` | Fold timelines, independent Train/Test bars and summary statistics; optional fold-endpoint index |

Single-backtest `start_time` and `end_time` are **candle opens**, including the final
candle's open, not an exclusive evaluation end. The adapter adds one timeframe to
`end_time` for the actual half-open segment. Requested evaluation boundaries can
differ from actual candle coverage. Multi-mode `/shared_data` includes requested
`evaluation_start/end`, `first_candle_open`, `last_candle_open`, counts, warm-up,
initialization profiles and `candles_sha256`, but no candle prices. Segment
`start/end` are actual half-open UTC boundaries. Train/Test portfolios reset capital
and positions; plot their performance separately even when intervals touch.

## Equity and drawdown: missing retained data in every mode

`run_backtest` creates a local `equity` list starting with initial cash. For each
evaluation candle, it appends reference-price portfolio value at the open **after
any open execution**, then at the close **after final forced liquidation when
applicable**. `summarize` reduces that sequence to `B.max_drawdown_percent` and
discards it. Neither `BacktestResult`, `CLIBacktest` nor any of the five containers
exposes timestamped equity or drawdown points. `BacktestExecution.candles` is transient
orchestration state, not part of the public saved result or client wrapper.

| Desired visual | Exact available fields / units | Missing data / saved-input verdict |
| --- | --- | --- |
| Portfolio equity curve | `B.initial_balance`, `B.final_balance`: quote-currency amounts; `B.equity_policy = reference_prices` | All intermediate values and sampling/event timestamps are absent. Requires a retained engine series; no curve from current saved inputs |
| Drawdown curve | `B.max_drawdown_percent`: nonpositive %, largest sampled peak-to-trough decline | No path or running peaks. A scalar drawdown bar is available; a curve requires the actual equity sequence |
| Benchmark equity or cumulative-return curve | `B.buy_and_hold_return_percent`: nullable net %, `B.benchmark_costs`, `B.benchmark_policy` | No intermediate benchmark values or prices. Only final-return comparison is supported |
| Strategy-vs-benchmark return bars | `B.total_return_percent`, `B.buy_and_hold_return_percent`: %; segment `excess_return_pp` where present: pp | Available per matching segment, retaining nulls and the net benchmark policy |

Trades contain entry/exit times, quantities, prices, PnL and optional execution fills.
They do not contain the intervening market prices required for mark-to-market equity.
Even forced final-close trades use the candle's timestamp, not a separate close-time
sample. Do not interpolate an equity path, infer intrabar extrema, convert a single
drawdown scalar to a curve or draw an initial-to-final line labeled equity.

The net benchmark policy is first evaluation open to final close with the same
execution model. Comparison also stores `/buy_and_hold_return_percent`; its validator
checks equality with each result. The other modes' benchmark is local to each
independent segment/scenario. Return differences are percentage **points**, not
percentage changes; returns are not annualized or normalized for unequal durations.

## Walk-Forward panels

`/folds/i/{train_start,train_end,test_start,test_end}` and candle counts provide UTC
timeline rectangles. `/configuration/windows/{mode,train_days,test_days,step_days}`
records rolling/expanding policy; `/unused_trailing_candles` records excluded data.
Training intervals may overlap. Test intervals do not overlap but can have gaps.
Use actual boundaries, preserve gaps and label each independent portfolio.

Per-fold return/benchmark/drawdown scalars live at the `B` paths above. Summary fields
include `/summaries/i/{median_test_return_percent,minimum_test_return_percent,
maximum_test_return_percent,median_test_max_drawdown_percent}` in %, nullable
`median_test_excess_return_pp` in pp, `total_test_trades`/fold counts in counts and
`positive_test_fraction` in [0,1]. These are independent-fold statistics, not pooled
portfolio metrics. The median of fold maximum drawdowns is not OOS portfolio drawdown.

Optional `/summaries/i/stitched_oos_index/j/{time,value}` is an index starting at 100
at the first Test start, followed by one point per Test end. The
[engine](../src/strategy_backtest_agent/walk_forward/engine.py) compounds independent
fold final/initial ratios. It is present only when `stitch_oos` is true; current
configuration rejects stitching gapped Test windows. A labeled endpoint scatter plot
is possible, but it is **not continuous execution, equity or intrafold drawdown**.
No benchmark endpoint index is retained. Do not create one from scalar returns in
the renderer or calculate a continuous OOS drawdown from these points.

## Sensitivity parameter response and heatmaps

The [grid analysis](../src/strategy_backtest_agent/sensitivity/analysis.py) emits:

| Dimensions | Saved fields | Plot and units | Limitation |
| --- | --- | --- | --- |
| One | `/ordered_series/i/{value,variant_id,return_percent,total_trades}` | Declared candidate value vs Train return (%), with trade counts | Candidate order is declared order; connecting points must not imply untested results |
| Two | `/matrix/{row_parameter,column_parameter,row_values,column_values,variant_ids,returns_percent,trade_counts}` | Row = parameter 0, column = parameter 1; cell return (%) and count | Full declared grid, no interpolation; cells map to variant IDs |
| Three | `/matrix = null`, `/ordered_series = null`; `/variants/i/{id,coordinates,parameter_values,strategy}` and `/results/i/variant_id` | Detailed variant table is available | No stored 2D projection. Slicing requires a separate reviewed UI/contract; do not silently select a dimension or aggregate |

`/parameters/i/{path,coupled_paths,base_value,values}` describes resolved dimensions.
Candidate units depend on the operand: indicator periods are candle counts,
Bollinger multipliers are dimensionless, RSI thresholds are oscillator levels, and
other constants inherit the compared indicator/price's units. Do not label all
parameters as % or quote currency. Coupled paths are one dimension, not separate axes.
Current bounds are three dimensions and 25 total variants. Low/zero-trade cells
remain visible and carry counts plus `/summary/minimum_observation_trades` and
`/summary/insufficient_trade_variant_ids`; color is not evidence of robustness.
Sensitivity evaluates **Train only**; reserved Test has no result to plot.

## Execution-cost comparisons

Scenario execution assumptions are `/results/i/execution/{fee_rate,spread_bps,
slippage_bps}`: fraction per side, full spread in bps, adverse slippage in bps per
side. `/results/i/return_difference_pp` is scenario return minus declared baseline
Train return. Join `/baseline_id`, not a renderer-selected best scenario.

Every `B` also has `/costs/{fees,modeled_spread_cost,modeled_slippage_cost}` in quote
currency; nullable `benchmark_costs` has the same units. These support labeled
component bars alongside returns and separate benchmark costs. Spread/slippage
components are modeled fill attributions, not additional cash fees to subtract from
already net results. Do not stack them with net PnL as an accounting identity, infer
historical liquidity/spreads or claim monotonic performance across scenarios.
The cost workflow evaluates Train only, with Test reserved.

## What survives normalized report generation

`ResearchReport` schema `1.0`, generator `research-reports/1`, contains
`evidence.source`, `configuration`, `reproducibility_metadata`, `scopes`, `metrics`,
limitations/methodology/source notes, observations, optional AI interpretation and
hashes. It does not embed native research JSON, trades, candles or curve arrays.

Metric records give exact `id`, `scope`, `name`, `value`, `unit`, `source_path` and
context. Common names include `total_return`, `net_buy_and_hold`, `max_drawdown`,
`fees`, `modeled_spread_cost`, `modeled_slippage_cost`, `completed_trades` and
`profit_factor`. `net_pnl` is explicitly final minus initial balance. Nullable values
include benchmark return, win rate, profit factor and excess return; null is not zero.

| Native information | Normalized availability |
| --- | --- |
| All segment scalars and execution assumptions | Metrics scoped as `strategy.single`, `strategy.<id>`, `strategy.<id>.train/test`, `variant.<id>.train`, `scenario.<id>.train`, `fold.<fold_id>.strategy.<id>.train/test` |
| Segment boundaries and labels | `evidence.scopes[*].{id,label,role,start,end,strategy,execution}`; UTC normalization |
| Fold summary and endpoint index | `summary.strategy.<id>.oos` metrics and `.index.<offset>` point scopes (`role = stitched_index`); point `start = end = time`, `value` metric unit `index` |
| Resolved grid axes, coordinates, matrix and series | Not copied as structured layout fields. Configuration retains parameter specifications and variant scopes retain mutated rules, but the resolved native layout is absent |
| Original source hashes and candle provenance | `evidence.source.{input_content_sha256,canonical_input_sha256,candle_sha256}`; single-backtest candle hash may be null. Metadata is not authentication |

For a full 2D heatmap, use a validated native layout projection in addition to the
existing evidence, or design a future versioned report extension. Do not pretend
current normalized report JSON contains `/matrix`. A generic metric table and
per-variant bars require no extension.

## Current public/report/output boundaries

[Python client](../src/strategy_backtest_agent/client.py): `report`, `areport` and
`ClientResult.save_report` currently accept only `markdown`/`json`. `ClientResult`
retains original source bytes, including the AI envelope. `report(ResearchReport)`
accepts a typed report directly; native models/mappings/paths go through research
adapters. A path to a saved normalized `ResearchReport` JSON is **not currently a
supported adapter input**. A raw engine `BacktestResult` alone is also insufficient.

[CLI report](../src/strategy_backtest_agent/reports/cli.py) reads one native saved
research result via `--input`; formats are Markdown/JSON and default is Markdown.
It does not rerun research. `--ai` explicitly opts into optional interpretation.
HTML is not implemented at this baseline.

Input reading requires regular files and bounds UTF-8 JSON to 16 MiB, 250,000 nodes,
depth 32 and strings of 8,192 characters; duplicate keys and nonfinite numbers reject.
Adapters validate strict JSON and then financial/identity/grid/initialization
consistency. Existing tagged v0.8/v0.9 compatibility preserves missing legacy
initialization fields as absent; it does not accept arbitrary incomplete outputs.

`write_new` uses POSIX descriptor-relative traversal, rejects `..` and symlink
directories, creates an exclusive temporary UTF-8 file, flushes/fsyncs, atomically
hard-links to a new destination and cleans up the temporary file. Existing files,
directories and symlink destinations cannot be overwritten, including races. Parent
directories can be created. This is the writer to reuse for HTML; UUID temporary
filenames do not enter report content. No browser launch or companion asset writer
exists. See [safe-output tests](../tests/test_report_security.py).

## Read-only evidence

Source inspection covered every native container and the adapter/evidence/client/
CLI/writer paths above. A socket-denying Python inspection passed all 12 checked-in
tagged v0.8.0/v0.9.0 fixtures (six modes per version) through `build_report` and
confirmed no public equity/drawdown arrays. Their sensitivity examples are 1D;
2D matrix construction is separately evidenced by `describe_grid` and
[existing 2D sensitivity cases](../tests/test_sensitivity_engine.py). These are
schema/source findings, not new runtime or browser acceptance tests. No full test
suite, paid AI request or live market-data request is part of this documentation audit.
