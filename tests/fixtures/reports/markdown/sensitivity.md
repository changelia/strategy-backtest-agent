# Historical Strategy Research Report

**Parameter Sensitivity (Train only)**

Report status: deterministic

## Executive Summary

- The declared Train-only grid contained positive historical returns; no variant is selected or recommended.
- For variant-001 (Variant Train), historical net return was positive; this is descriptive, not predictive evidence.
- For variant-001 (Variant Train), historical return was above net Buy &amp; Hold.
- For variant-001 (Variant Train), there were fewer than five completed trades; limited trade evidence is not proof of stability.
- For variant-001 (Variant Train), sampled historical equity experienced a drawdown.
- For variant-002 (Variant Train), historical net return was positive; this is descriptive, not predictive evidence.

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
| Parameters 1 / Path | entry.right.value |
| Parameters 1 / Coupled paths | None |
| Parameters 1 / Values | 30.0, 35.0 |
| Parameters 1 / Range | Not provided |
| Parameters 1 / Nearby | Not provided |
| Train ratio | 0.7 |

## Strategies and Rules

| Definition | Used by | Entry | Exit |
| --- | --- | --- | --- |
| S1 | variant-001 | RSI(14) &lt; 30 | RSI(14) &gt; 70 |
| S2 | variant-002 | RSI(14) &lt; 35 | RSI(14) &gt; 70 |

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
| R1 | variant-001 (Variant Train) | 2024-01-01 00:00:00 | 2024-01-03 19:00:00 |
| R2 | variant-002 (Variant Train) | 2024-01-01 00:00:00 | 2024-01-03 19:00:00 |
| R3 | Declared sensitivity grid (Overall) | 2024-01-01 00:00:00 | 2024-01-03 19:00:00 |

#### Returns and benchmark

| Segment | Initial balance | Final balance | Net pnl | Total return | Net buy and hold | Excess return | Max drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R1 | 1000.0000 quote | 1815.5010 quote | 815.5010 quote | 81.5501 % | 11.3950 % | 70.1551 pp | -5.8295 % |
| R2 | 1000.0000 quote | 1582.6477 quote | 582.6477 quote | 58.2648 % | 11.3950 % | 46.8698 pp | -12.3235 % |

#### Trades

| Segment | Completed trades | Winning trades | Losing trades | Win rate | Profit factor |
| --- | --- | --- | --- | --- | --- |
| R1 | 2 | 2 | 0 | 100.0000 % | N/A (undefined) |
| R2 | 2 | 2 | 0 | 100.0000 % | N/A (undefined) |

#### Execution costs (quote currency)

| Segment | Fees | Modeled spread cost | Modeled slippage cost | Benchmark fees | Benchmark modeled spread cost | Benchmark modeled slippage cost |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | 5.5362 quote | 2.7685 quote | 2.7685 quote | 2.1141 quote | 1.0571 quote | 1.0571 quote |
| R2 | 5.1156 quote | 2.5581 quote | 2.5581 quote | 2.1141 quote | 1.0571 quote | 1.0571 quote |

#### Aggregate and additional metrics

| Segment | Metric | Value |
| --- | --- | --- |
| R3 | Variant count | 2 |
| R3 | Minimum return percent | 58.2648 % |
| R3 | Median return percent | 69.9074 % |
| R3 | Maximum return percent | 81.5501 % |
| R3 | Return range pp | 23.2853 pp |
| R3 | Positive return percent | 100.0000 % |
| R3 | Outperforming buy and hold percent | 100.0000 % |
| R3 | Minimum observation trades | 5 |
| R3 | Similarity tolerance pp | 5.0000 pp |

## Parameter Sensitivity

Train only. Test is reserved and not evaluated. These descriptive results neither select an optimal strategy nor establish independent OOS validation.

## Methodology

- Only the supplied single research result is analyzed; no market-data fetch or backtest execution.
- Numbers are copied from validated results; derived net PnL is final minus initial balance.
- Benchmark is net first evaluation open to final close under the same execution assumptions.
- Undefined metrics remain null; no pooled win rate/profit factor or continuous OOS drawdown is invented.
- Train only; no Test results are present.

## Limitations

- Historical results do not predict returns, establish safety, statistical significance or robustness.
- Structural and consistency validation does not authenticate data or results. A supplied candle hash is source metadata, not proof of truthful research.
- Spread/slippage are modeled assumptions; full fills and unlimited liquidity are assumed. Drawdown samples opens/closes.
- Consistency checks cannot verify prices, indicators, signal correctness or drawdown paths without original candles/equity. No backtest is rerun.
- Train-only research. Test is reserved and not evaluated by this workflow; no independent OOS claim is supported.

Source-provided notes (unverified wording, treated as data):

- All performance is in-sample sensitivity analysis on Train only. Test is reserved and not evaluated; no strategy is ranked, selected or recommended.
- Repeated parameter experimentation can overfit Train. Freeze a preselected configuration before a separate explicit held-out evaluation; a previously inspected Test is contaminated.
- Statistics describe only this declared grid, not future profitability or robustness. Zero-trade and low-trade configurations are not evidence of stability.
- Neighbor observations use declared candidate order, a 5 pp similarity tolerance and at least 5 trades per configuration. These are descriptive conventions, not significance tests.
- RSI/EMA/MACD/ATR initialization is finite. Each indicator uses its own anchored prior history; adding grid periods cannot move an existing indicator seed. Fills use configured modeled spread/slippage and exclude liquidity constraints; drawdown samples opens and closes, not intrabar extremes.

## Reproducibility Metadata

- Report schema: 1.0; generator: research-reports/1
- Adapter: sba-v0.9-sensitivity/1; source schema version: not provided (unversioned)
- Input bytes SHA256: 9ec117dca8f4dc431f236ba47bbc47a0d297b5e58eb096cafcbc57c0a158b0cd
- Canonical input SHA256: 19cdd6f07150d9d29c8be579ebb0308a32951c54bd91485ceeaa78bfa15a9bc4
- Normalized evidence SHA256: 6415aad4ed1a71df377441ab80fb9284e6b20760eabd02fdb6fcddfee653c0c1
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
| Warmup policy | indicator-local prior closes anchored at first Train open: RSI=p+1; SMA=p; EMA=5\*p; MACD=10\*(slow+signal); Bollinger=p (population std); ATR=20\*p; finite indicator-local seeds independent of other grid periods |
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
