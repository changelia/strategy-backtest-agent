"""Print a fixed synthetic v0.9 CLI-shaped backtest JSON; no provider or AI calls.

This fixture generator explicitly executes a backtest. The report command never does.
"""

from datetime import UTC, datetime, timedelta

from strategy_backtest_agent.backtester import run_backtest
from strategy_backtest_agent.models import BacktestConfig, Candle, ExecutionConfig
from strategy_backtest_agent.reports.inputs import canonical_bytes
from strategy_backtest_agent.rules.models import Comparison, Price, RuleStrategy, Value


def main() -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    closes = [10, 10, 10, 20, 10, 5, 10, 10]
    candles = [
        Candle(
            timestamp=start + timedelta(hours=12 * i),
            open=10,
            close=close,
            high=max(10, close),
            low=min(10, close),
            volume=1,
        )
        for i, close in enumerate(closes)
    ]
    rule = RuleStrategy(
        entry=Comparison(left=Price(), operator=">", right=Value(value=0)),
        exit=Comparison(left=Price(), operator="<", right=Value(value=0)),
    )
    config = BacktestConfig(
        timeframe="12h",
        initial_balance=1000,
        execution=ExecutionConfig(fee_rate=0.01, spread_bps=20, slippage_bps=10),
    )
    result = run_backtest(candles, config, rule)
    source = {
        **result.model_dump(mode="json"),
        "symbol": "BTCUSDT",
        "timeframe": "12h",
        "period_days": 4,
        "data_source": "synthetic offline fixture; prices are not historical BTCUSDT",
        "candle_count": len(candles),
        "start_time": candles[0].timestamp.isoformat(),
        "end_time": candles[-1].timestamp.isoformat(),
        "strategy": rule.model_dump(mode="json"),
        "trading_fee": 0.01,
        "indicator_configuration": [],
    }
    print(canonical_bytes(source).decode())


if __name__ == "__main__":
    main()
