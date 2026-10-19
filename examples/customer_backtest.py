"""Offline customer backtest; run in a fresh directory with the package installed."""

from pathlib import Path

from strategy_backtest_agent import BacktestClient, BacktestConfig, ExecutionConfig

client = BacktestClient()
config = BacktestConfig(
    symbol="BTCUSDT",
    timeframe="1h",
    initial_balance=10000.0,
    trading_fee=0.001,
    rsi_period=14,
    entry_rsi=30.0,
    exit_rsi=70.0,
    execution=ExecutionConfig(fee_rate=0.001, spread_bps=10.0, slippage_bps=5.0),
)
result = client.run(config=config, days=30, demo=True)
print(result.summary())
print(f"Net Buy & Hold: {result.buy_and_hold_return_percent:.2f}%")
with Path("backtest-result.json").open("x", encoding="utf-8") as stream:
    stream.write(result.to_json())
result.save_report("backtest-report.md")
result.save_report("backtest-report.json", format="json")
print("Saved backtest-result.json, backtest-report.md and backtest-report.json")
