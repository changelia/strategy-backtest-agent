# Historical Strategy Research Report

**Walk-Forward Analysis**

Report status: deterministic

## Executive Summary

- For RSI 14 (OOS), 3 of 3 independent Test folds had positive historical returns.
- For RSI 14 (OOS), median Test return was positive.
- For RSI 14 (Fold 001, Train), historical net return was negative; this is descriptive, not predictive evidence.
- For RSI 14 (Fold 001, Train), historical return was above net Buy &amp; Hold.
- For RSI 14 (Fold 001, Train), there were fewer than five completed trades; limited trade evidence is not proof of stability.
- For RSI 14 (Fold 001, Train), sampled historical equity experienced a drawdown.

All observations describe supplied historical evidence; no future performance or live position is recommended.

## Research Configuration

| Setting | Validated value (schema defaults applied) |
| --- | --- |
| Symbol | BTCUSDT |
| Timeframe | 1h |
| Period days | 4 |
| Initial balance | 1000.0 |
| Fee | 0.001 |
| Evaluation end | 2024-01-05T00:00:00Z |
| Windows / Mode | rolling |
| Windows / Train days | 1 |
| Windows / Test days | 1 |
| Windows / Step days | Not provided |
| Windows / Max folds | 50 |
| Stitch oos | Yes |

## Strategies and Rules

| Definition | Used by | Entry | Exit |
| --- | --- | --- | --- |
| S1 | RSI 14 | RSI(14) &lt; 30 | RSI(14) &gt; 70 |

## Historical Data and Evaluation Period

- Source: synthetic offline versioned fixture
- Evaluation (UTC): 2024-01-01 00:00:00 to 2024-01-05 00:00:00
- Boundary interpretation: Source requested UTC evaluation range; scopes contain actual half-open completed-candle segments.

## Execution Assumptions

Fee is a per-side fraction; spread is the full bid/ask spread in bps; slippage is adverse per side in bps.
OHLC prices are reference proxies. Reported spread/slippage costs are illustrative adjustments, not measured fills.
Signals execute at the following candle open; forced liquidation uses the segment's final close.

| Applies to | Fee per side | Full spread | Slippage per side |
| --- | --- | --- | --- |
| All segments | 0.001 fraction | 10 bps | 5 bps |

## Performance Results

Numbers are rounded for display; JSON evidence retains source precision, full identifiers, source paths and contexts. All segments, negative results and undefined metrics are shown. R references identify rows below; boundaries are UTC and use the source boundary policy.

### RSI 14

| Reference | Segment | Start UTC | End UTC |
| --- | --- | --- | --- |
| R1 | RSI 14 (Fold 001, Train) | 2024-01-01 00:00:00 | 2024-01-02 00:00:00 |
| R2 | RSI 14 (Fold 001, Test) | 2024-01-02 00:00:00 | 2024-01-03 00:00:00 |
| R3 | RSI 14 (Fold 002, Train) | 2024-01-02 00:00:00 | 2024-01-03 00:00:00 |
| R4 | RSI 14 (Fold 002, Test) | 2024-01-03 00:00:00 | 2024-01-04 00:00:00 |
| R5 | RSI 14 (Fold 003, Train) | 2024-01-03 00:00:00 | 2024-01-04 00:00:00 |
| R6 | RSI 14 (Fold 003, Test) | 2024-01-04 00:00:00 | 2024-01-05 00:00:00 |
| R7 | RSI 14 (OOS) | 2024-01-02 00:00:00 | 2024-01-05 00:00:00 |
| R8 | Stitched OOS endpoint 000 | 2024-01-02 00:00:00 | 2024-01-02 00:00:00 |
| R9 | Stitched OOS endpoint 001 | 2024-01-03 00:00:00 | 2024-01-03 00:00:00 |
| R10 | Stitched OOS endpoint 002 | 2024-01-04 00:00:00 | 2024-01-04 00:00:00 |
| R11 | Stitched OOS endpoint 003 | 2024-01-05 00:00:00 | 2024-01-05 00:00:00 |

#### Returns and benchmark

| Segment | Initial balance | Final balance | Net pnl | Total return | Net buy and hold | Excess return | Max drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R1 | 1000.0000 quote | 940.4030 quote | -59.5970 quote | -5.9597 % | -20.1937 % | 14.2340 pp | -5.9597 % |
| R2 | 1000.0000 quote | 1427.9711 quote | 427.9711 quote | 42.7971 % | 24.9981 % | 17.7991 pp | -0.1997 % |
| R3 | 1000.0000 quote | 1427.9711 quote | 427.9711 quote | 42.7971 % | 24.9981 % | 17.7991 pp | -0.1997 % |
| R4 | 1000.0000 quote | 1370.3793 quote | 370.3793 quote | 37.0379 % | 23.7979 % | 13.2400 pp | -4.3179 % |
| R5 | 1000.0000 quote | 1370.3793 quote | 370.3793 quote | 37.0379 % | 23.7979 % | 13.2400 pp | -4.3179 % |
| R6 | 1000.0000 quote | 1215.0039 quote | 215.0039 quote | 21.5004 % | -14.0192 % | 35.5196 pp | -5.3662 % |

#### Trades

| Segment | Completed trades | Winning trades | Losing trades | Win rate | Profit factor |
| --- | --- | --- | --- | --- | --- |
| R1 | 1 | 0 | 1 | 0.0000 % | 0 ratio |
| R2 | 1 | 1 | 0 | 100.0000 % | N/A (undefined) |
| R3 | 1 | 1 | 0 | 100.0000 % | N/A (undefined) |
| R4 | 1 | 1 | 0 | 100.0000 % | N/A (undefined) |
| R5 | 1 | 1 | 0 | 100.0000 % | N/A (undefined) |
| R6 | 1 | 1 | 0 | 100.0000 % | N/A (undefined) |

#### Execution costs (quote currency)

| Segment | Fees | Modeled spread cost | Modeled slippage cost | Benchmark fees | Benchmark modeled spread cost | Benchmark modeled slippage cost |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | 1.9403 quote | 0.9701 quote | 0.9701 quote | 1.7979 quote | 0.8988 quote | 0.8988 quote |
| R2 | 2.4284 quote | 1.2144 quote | 1.2144 quote | 2.2502 quote | 1.1252 quote | 1.1252 quote |
| R3 | 2.4284 quote | 1.2144 quote | 1.2144 quote | 2.2502 quote | 1.1252 quote | 1.1252 quote |
| R4 | 2.3708 quote | 1.1856 quote | 1.1856 quote | 2.2382 quote | 1.1192 quote | 1.1192 quote |
| R5 | 2.3708 quote | 1.1856 quote | 1.1856 quote | 2.2382 quote | 1.1192 quote | 1.1192 quote |
| R6 | 2.2152 quote | 1.1077 quote | 1.1077 quote | 1.8597 quote | 0.9298 quote | 0.9298 quote |

#### Aggregate and additional metrics

| Segment | Metric | Value |
| --- | --- | --- |
| R7 | Fold count | 3 |
| R7 | Total Test trades | 3 |
| R7 | Positive Test folds | 3 |
| R7 | Positive Test fraction | 1 fraction |
| R7 | Median Test return percent | 37.0379 % |
| R7 | Minimum Test return percent | 21.5004 % |
| R7 | Maximum Test return percent | 42.7971 % |
| R7 | Median Test max drawdown percent | -4.3179 % |
| R7 | Median Test excess return pp | 17.7991 pp |
| R7 | Outperforming Test folds | 3 |
| R8 | Value | 100 index |
| R9 | Value | 142.79711 index |
| R10 | Value | 195.68621 index |
| R11 | Value | 237.75951 index |

## Train/Test and OOS Evidence

Train and held-out Test are reported separately. Test portfolios start with fresh capital. Prior strategy selection can contaminate holdouts.
Test aggregates summarize independent folds. Median fold drawdown is not continuous portfolio drawdown. Stitched OOS, if supplied, is a fold-endpoint index: not continuous execution with carried positions.

## Methodology

- Only the supplied single research result is analyzed; no market-data fetch or backtest execution.
- Numbers are copied from validated results; derived net PnL is final minus initial balance.
- Benchmark is net first evaluation open to final close under the same execution assumptions.
- Undefined metrics remain null; no pooled win rate/profit factor or continuous OOS drawdown is invented.
- Each Train and Test segment starts with fresh capital; no signals/positions cross segment ends.

## Limitations

- Historical results do not predict returns, establish safety, statistical significance or robustness.
- Structural and consistency validation does not authenticate data or results. A supplied candle hash is source metadata, not proof of truthful research.
- Spread/slippage are modeled assumptions; full fills and unlimited liquidity are assumed. Drawdown samples opens/closes.
- Consistency checks cannot verify prices, indicators, signal correctness or drawdown paths without original candles/equity. No backtest is rerun.
- Held-out validity depends on freezing rules before inspecting the same history; repeated inspection can contaminate Test.
- Stitched OOS is a fold-endpoint index of fresh-capital Test portfolios, not continuous execution with carried positions.

Source-provided notes (unverified wording, treated as data):

- Fixed predeclared strategies only; Train is diagnostic. No optimization, ranking or selection.
- Multiple historical OOS folds do not establish robustness or future profitability. Strategies selected after inspecting this history do not have independent held-out evidence.
- Each Train and Test resets capital and positions; signals never cross segment boundaries.
- Indicator-local finite seeds are anchored before the first evaluation candle and continued causally across folds. RSI/EMA/MACD/ATR seed effects can remain near thresholds.
- Stitched index compounds normalized independent Test fold returns at fold endpoints only; it is not a portfolio carrying positions, and has no continuous drawdown statistic.
- Constant modeled costs, full fills and unlimited liquidity are assumptions; drawdown samples opens/closes, not intrabar extremes. Repeated evaluation can overfit history.

## Reproducibility Metadata

- Report schema: 1.0; generator: research-reports/1
- Adapter: sba-v0.9-walk\_forward/1; source schema version: not provided (unversioned)
- Input bytes SHA256: 4eb792fbba977fba354bd04ee1fa2a2299857bf0e239cce0d17c0f34c3a3e3c2
- Canonical input SHA256: 78a5dc70fd623f8223436583a513b8f6b774bf71d1c25782ba2c79a4dfd1ee5f
- Normalized evidence SHA256: 7e932e982051a6261535adeb2924589ec8f600e68943162318e0a6553c501d14
- Source candle SHA256: ed64f95893aa94fe30b1abe2aa608abd561c38f073fbdc62bf0fc9f4299139ad
- No wall-clock generation timestamp is added. AI interpretation is not guaranteed reproducible.

Source history/initialization metadata:

| Field | Supplied value |
| --- | --- |
| Source | synthetic offline versioned fixture |
| Evaluation start | 2024-01-01T00:00:00Z |
| Evaluation end | 2024-01-05T00:00:00Z |
| First candle open | 2024-01-01T00:00:00Z |
| Last candle open | 2024-01-04T23:00:00Z |
| Candle count | 96 |
| History candle count | 111 |
| Warmup candles | 15 |
| Required warmup candles | 15 |
| Warmup policy | indicator-local seeds before first evaluation open; causal continuation |
| Indicators 1 / Type | indicator |
| Indicators 1 / Name | rsi |
| Indicators 1 / Period | 14 |
| Indicator initializations 1 / Indicator / Type | indicator |
| Indicator initializations 1 / Indicator / Name | rsi |
| Indicator initializations 1 / Indicator / Period | 14 |
| Indicator initializations 1 / Prior candle count | 15 |
| Indicator initializations 1 / History start | 2023-12-31T09:00:00Z |
| Indicator initializations 1 / Input fields | close |
| Indicator initializations 1 / Seed policy | legacy: RSI SMA/Wilder; SMA rolling; EMA first-close; configured history anchor |
| Candles sha256 | ed64f95893aa94fe30b1abe2aa608abd561c38f073fbdc62bf0fc9f4299139ad |
