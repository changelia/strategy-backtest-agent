# Changelog

## v1.0.0 — Evidence-Grounded AI Research Reports

### Added

- Offline reports from one existing standard backtest, strategy comparison,
  out-of-sample validation, parameter sensitivity, execution-cost scenario or
  Walk-Forward result. Report generation never implicitly reruns research.
- Strict result adapters, normalized typed evidence, stable identifiers, source
  paths and units, deterministic observations, content/candle provenance and
  canonical evidence SHA256. Undefined financial metrics remain null.
- Reproducible Markdown and JSON exports without generated timestamps. Readable
  rules appear once; compact tables preserve every Train/Test fold, negative
  outcome, execution assumption, methodological warning and UTC boundary.
- Optional structured OpenAI interpretation with evidence references and separately
  checked numeric values. Approved explanatory templates reject unrestricted
  numerical claims, predictions and investment instructions. Missing credentials,
  provider failures and rejected interpretations preserve deterministic reports.
- Bounded untrusted input parsing, escaped Markdown metadata and atomic output
  creation that refuses existing files, parent traversal and symlink directories.
- Versioned synthetic fixtures, Markdown snapshots, AI mocks and regression tests.

### Fixed

- Legacy v0.8 RSI/SMA/EMA initialization metadata is accepted without confusing
  missing additive fields with contradictory defaults. Explicitly invalid metadata
  and incomplete advanced-indicator profiles remain rejected.
- Shared OpenAI default changed to gpt-4.1-mini. OPENAI_MODEL remains configurable
  for both strategy parsing and report interpretation.

### Compatibility and limitations

- Backtesting, indicators, fees, spreads, slippage, portfolio isolation, benchmarks
  and research calculations are unchanged from v0.9.0. Package version becomes
  1.0.0; report schema/generator versions are independent.
- The offline demo matches v0.9.0 exactly and is not a profitability example.
- Validation and supplied hashes do not authenticate research or original prices,
  prove arbitrary natural-language claims, or establish predictive value.
- AI is constrained template selection, may be unavailable, and is not guaranteed
  byte reproducible. Automated tests mock provider requests.
- POSIX safe output creation is required. No multi-file aggregation, PDF/HTML,
  charts, live trading, forecasts or investment recommendations are introduced.
