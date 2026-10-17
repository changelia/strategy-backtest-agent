# Historical Strategy Research Report

**Out-of-Sample Validation**

Report status: deterministic

## Executive Summary

- For RSI 14 (Train), historical net return was positive; this is descriptive, not predictive evidence.
- For RSI 14 (Train), historical return was above net Buy &amp; Hold.
- For RSI 14 (Train), there were fewer than five completed trades; limited trade evidence is not proof of stability.
- For RSI 14 (Train), sampled historical equity experienced a drawdown.
- For RSI 14 (Test), historical net return was positive; this is descriptive, not predictive evidence.
- For RSI 14 (Test), historical return was above net Buy &amp; Hold.

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
| Train ratio | 0.7 |

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

### Research results

| Reference | Segment | Start UTC | End UTC |
| --- | --- | --- | --- |
| R1 | RSI 14 (Train) | 2024-01-01 00:00:00 | 2024-01-03 19:00:00 |
| R2 | RSI 14 (Test) | 2024-01-03 19:00:00 | 2024-01-05 00:00:00 |

#### Returns and benchmark

| Segment | Initial balance | Final balance | Net pnl | Total return | Net buy and hold | Excess return | Max drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R1 | 1000.0000 quote | 1815.5010 quote | 815.5010 quote | 81.5501 % | 11.3950 % | 70.1551 pp | -5.8295 % |
| R2 | 1000.0000 quote | 1215.0039 quote | 215.0039 quote | 21.5004 % | -10.6449 % | 32.1453 pp | -5.3662 % |

#### Trades

| Segment | Completed trades | Winning trades | Losing trades | Win rate | Profit factor |
| --- | --- | --- | --- | --- | --- |
| R1 | 2 | 2 | 0 | 100.0000 % | N/A (undefined) |
| R2 | 1 | 1 | 0 | 100.0000 % | N/A (undefined) |

#### Execution costs (quote currency)

| Segment | Fees | Modeled spread cost | Modeled slippage cost | Benchmark fees | Benchmark modeled spread cost | Benchmark modeled slippage cost |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | 5.5362 quote | 2.7685 quote | 2.7685 quote | 2.1141 quote | 1.0571 quote | 1.0571 quote |
| R2 | 2.2152 quote | 1.1077 quote | 1.1077 quote | 1.8934 quote | 0.9467 quote | 0.9467 quote |

#### Aggregate and additional metrics

| Segment | Metric | Value |
| --- | --- | --- |
| R2 | Return gap | -60.0497 pp |

## Train/Test and OOS Evidence

Train and held-out Test are reported separately. Test portfolios start with fresh capital. Prior strategy selection can contaminate holdouts.

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

Source-provided notes (unverified wording, treated as data):

- Test is Held-out evaluation, not guaranteed future performance. Holdout validity depends on selecting and freezing strategies before examining Test results.
- Return gap is descriptive: segment durations differ and total returns are not normalized.
- A single holdout cannot establish robustness; repeated inspection or strategy selection using Test results contaminates the holdout. No optimization or winner selection is performed.
- Finite RSI/EMA/MACD/ATR initialization can affect signals. Fills use configured modeled spread/slippage and exclude liquidity constraints; drawdown samples opens/closes, not intrabar extremes.

## Reproducibility Metadata

- Report schema: 1.0; generator: research-reports/1
- Adapter: sba-v0.9-validation/1; source schema version: not provided (unversioned)
- Input bytes SHA256: 8c577e0c4d0d6fb6d1bd9722274b23e431fa3c43f5c3a075a0db6081fe90ade6
- Canonical input SHA256: 47ccb1ae4b99e80e0003da5d544c1af7b20e609ae17f033fed9b357beb24a22c
- Normalized evidence SHA256: 2875b77aa4581b1099ff4393de27f4c46ee656762344db6825b31bd0b59df5de
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
| Warmup policy | shared prior closes: RSI=p+1; SMA=p; EMA=5\*p (finite first-close seed) |
| Indicators 1 / Type | indicator |
| Indicators 1 / Name | rsi |
| Indicators 1 / Period | 14 |
| Indicator initializations | None |
| Candles sha256 | ed64f95893aa94fe30b1abe2aa608abd561c38f073fbdc62bf0fc9f4299139ad |
