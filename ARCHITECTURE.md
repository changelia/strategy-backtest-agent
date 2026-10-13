# Strategy rule architecture

The existing `BacktestConfig`, candle/trade models, indicators, execution accounting,
and metrics remain the core. No dependencies or version changes accompany this extension.

```text
Natural language → ai/parser.py → AIStrategyConfig (RSI or RuleStrategy)
                                 ↓
                    rules/history.py: fetch prior + requested UTC history
                                 ↓
                    rules/evaluator.py: unique indicator cache
                                 ↓
                    backtester.py: evaluate the previous completed candle
                                 ↓
                    existing next-open execution, fees, equity and metrics
                                 ↓
                    cli.py: deterministic summary or JSON
```

`rules/models.py` defines price, finite value and indicator operands, comparisons,
and recursive boolean groups. Literal tags close the language; extra fields are
forbidden. Tree validation limits depth to 5 and total comparisons to 20. Typed
unions produce `anyOf` with recursive references in the API schema; the SDK makes
all fields required. This uses the documented recursive schema support in
[OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
The parser revalidates returned data even if an injected SDK model bypassed construction
validation. Unsupported concepts and transition events are rejected rather than simplified.

`prepare_indicators` collects unique dependencies across both rules and builds each
series once. Evaluation resolves values at a single historical index. Every comparison
first checks finiteness. AND/OR recursively combine comparisons, without negation.
The evaluator has no provider, SDK, CLI or financial accounting dependency.

`run_backtest` validates the supplied rule tree again and initializes a portfolio at
`evaluation_start`. It skips prior candles for execution/equity purposes while retaining
prior indicator values. At each subsequent open it checks the previous evaluation close,
selecting exit when holding and entry when flat. A final signal has no following open;
existing final-close liquidation remains. Fees, sizing, reconciliation, open/close
equity marks, drawdown and summaries use the original accounting implementation.

Legacy RSI settings become equivalent comparison rules for periods 2–500. Older
period limits outside the DSL keep the legacy signal function. Legacy paths retain
in-range initialization to preserve v0.2.0 outputs. Regression tests force the old
signal path and compare all metrics and trades against DSL execution on identical data.

The CLI's explicit rule path calls `fetch_rule_history` once. It extends the requested
start by the largest requirement: RSI p+1, SMA p, EMA 5p prior intervals. It checks
continuous history, adequate initialization and evaluation coverage. Binance's existing
sequential 1000-row pagination, 0.2-second pauses and fail-fast rate-limit behavior remain.
Pre-range candles are excluded from benchmark and equity and never generate signals.
Read the README warm-up policy for UTC boundary behavior and seed convergence limits.

Python callers providing candles directly control initialization history and the
boundary index. The engine validates increasing timestamps but does not enforce the
provider's continuous-history policy for those callers, preserving existing behavior.
No arbitrary expressions, generated executable source, or dynamic code execution are used.
