# Tagged-engine report compatibility fixtures

These are offline synthetic outputs generated using the actual tagged engines:

- `v0.8.0`: `a4e4b3e008d8634441dd64b2f505d74fd2c6b949`
- `v0.9.0`: `90bef040ccd88e705125dfe0d3d326e382cdccf2`

`generate.py` runs six native research calculations on the same fixed RSI(14)
strategy and hourly synthetic candles. Walk-Forward uses three complete rolling
folds, a 15-candle RSI prefix, fresh portfolios, execution costs and stitched OOS.
The five structured research results are serialized directly by each tag's native
report model. The standard backtest adds the flat CLI envelope to the native
BacktestResult; it is not an assertion that metadata unavailable in older CLI
outputs was emitted. The fixtures contain no live market results or credentials.

Regenerate from the repository root (temporary checkouts can be anywhere):

```bash
mkdir -p /tmp/sba-report-v080 /tmp/sba-report-v090
git archive v0.8.0 | tar -x -C /tmp/sba-report-v080
git archive v0.9.0 | tar -x -C /tmp/sba-report-v090
PYTHONPATH=/tmp/sba-report-v080/src poetry run python tests/fixtures/reports/generate.py tests/fixtures/reports/v0.8.0
PYTHONPATH=/tmp/sba-report-v090/src poetry run python tests/fixtures/reports/generate.py tests/fixtures/reports/v0.9.0
```

These sources are unversioned JSON; directory names record their known generation
provenance. The reader cannot infer an authentic producer version from arbitrary
unversioned input. In v0.8 local initialization profiles have only indicator,
prior_candle_count and history_start. `input_fields` and `seed_policy` were added
in v0.9. Comparison/validation had no profile list in v0.8. Tests ensure absent
legacy metadata is not confused with contradictory explicitly supplied values.
