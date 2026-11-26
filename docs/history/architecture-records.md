# Architecture records

Historical release and audit notes moved verbatim from
[ARCHITECTURE.md](../../ARCHITECTURE.md), which keeps a one-line pointer where each
section was. They describe the project at the time they were written; the current
rules are in ARCHITECTURE.md.

### Release metadata

At the v0.7.0 release, the tag and package version were aligned at 0.7.0.
Earlier tags may retain historical metadata mismatches; they are not modified.
The release follows the financial audit, quality gates and a fast-forward main merge.

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
