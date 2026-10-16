# Walk-forward financial correctness audit

Verdict: RELEASE READY under the documented fixed-strategy research protocol.
No financial calculation or causality defect was confirmed. The human-readable
percentage-point display was corrected to signed two-decimal output; undefined
values display N/A. JSON precision is unchanged.

## Evidence

Full offline suite: 842 passing tests (809 previous, 33 added). Ruff, formatting
and full mypy pass. No external market-data or OpenAI calls are required by tests.
Existing compare, validate, sensitivity, costs and AI regression suites pass.

`tests/test_walk_forward_audit.py` adds 31 parameterized cases:

- Hand-calculated multiple roundtrips, fees, full spread, adverse slippage,
  benchmark returns and benchmark cost attribution in rolling and expanding modes.
- Final-open entry followed by final-close forced liquidation, ordinary exit at
  final open without duplicate liquidation, and in-segment trade timestamps.
- Train-only profitable position with completely flat, fresh-capital Test segments.
- Future-data mutation, additional later folds and byte-identical JSON replay for
  RSI, SMA and EMA in both modes.
- Truncated history/cache execution inputs; no future candle reaches a segment.
- Identical Test execution and initialization metadata between window modes.
- Test-only aggregates unaffected by replacement of Train diagnostics.
- Explicit normalized stitched index oracle: +100%, -50%, 0% gives
  100 -> 200 -> 100 -> 100, with fresh capital in each Test fold.
- Zero-trade portfolios, zero strategy costs, cost-adjusted benchmark, null win
  rate/profit factor, positive-fold counts and net benchmark outperformance.
- Hand-calculated drawdown including entry costs and final liquidation economics.
- Final Train signal never executing at first Test open.
- Actual eligible cached RSI/SMA/EMA values and initialization dates unchanged by
  introducing a longer-period strategy, under both window modes.

`tests/test_walk_forward_formatter.py` adds two display regression cases,
covering signed precision, undefined values and unchanged JSON serialization.
Existing `tests/test_walk_forward.py` covers exact fold placement, incomplete
trailing windows, invalid/overlapping steps, fold limits and shared fetch/cache.

## Findings and interpretation

Rolling and expanding use the same causal dependency-local initialization anchored
before the first evaluation candle. Expanding Train is a single continuous segment;
internal days and prior fold boundaries do not liquidate it. Each separate Train or
Test starts a new portfolio. Signals use completed segment candles and execute at
the next segment open. Only an outstanding position liquidates at segment final
close; an already closed or zero-trade portfolio has no forced liquidation.

No parameter mutation, optimization, ranking or strategy selection occurs. Train
results are diagnostics and cannot influence Test execution or summary statistics.
Per-fold drawdowns are summarized by median, never claimed as continuous drawdown.
Stitched output is a fold-endpoint index of independently normalized net Test
returns. It includes liquidation costs, carries no positions, and rejects Test gaps.

## Remaining limitations

Fixed configurations and identical historical candles are required for exact replay.
Moving the evaluation start changes the declared indicator initialization boundary.
Finite RSI/EMA seeds can affect threshold-adjacent signals. Multiple OOS folds do
not certify robustness or independence after inspecting the same history. Constant
illustrative costs, full fills, unlimited liquidity and open/close drawdown sampling
remain the existing execution assumptions. Stitched output omits intrafold equity
and has no continuous drawdown claim. Durations are whole days; no adaptive
optimization or gap treatment is supported.

Package version remains 0.7.0. No push, merge, version bump or tag was performed.
