"""Complete local OHLCV provider; no Binance or OpenAI calls.

The provider generates every requested hourly candle, including any requested prior
warm-up history. This is artificial data, not another built-in market-data service.
"""

from datetime import UTC, datetime, timedelta

from strategy_backtest_agent import (
    AIStrategyConfig,
    BacktestClient,
    Candle,
    Comparison,
    Indicator,
    RuleStrategy,
    Value,
)


class LocalHourlyProvider:
    async def fetch_candles(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Candle]:
        if symbol != "BTCUSDT" or timeframe != "1h":
            raise ValueError("This example supports BTCUSDT 1h only")
        epoch = datetime(2020, 1, 1, tzinfo=UTC)
        cursor = start
        candles = []
        while cursor < end:
            hour = int((cursor - epoch).total_seconds() // 3600)
            close = 100.0 + (hour % 48) / 2
            candles.append(
                Candle(
                    timestamp=cursor,
                    open=close,
                    high=close + 1,
                    low=close - 1,
                    close=close,
                    volume=10.0,
                )
            )
            cursor += timedelta(hours=1)
        return candles


client = BacktestClient(market_data_provider=LocalHourlyProvider())
config = AIStrategyConfig(
    symbol="BTCUSDT",
    timeframe="1h",
    period_days=3,
    strategy=RuleStrategy(
        entry=Comparison(
            left=Indicator(name="rsi", period=14), operator="<", right=Value(value=30.0)
        ),
        exit=Comparison(
            left=Indicator(name="rsi", period=14), operator=">", right=Value(value=70.0)
        ),
    ),
)
result = client.run(config=config, evaluation_end=datetime(2024, 7, 1, tzinfo=UTC))
assert result.data_source == "custom"
print(result.summary())
print("Source:", result.data_source)
result.save_report("custom-report.md")
result.save_report("custom-report.json", format="json")
