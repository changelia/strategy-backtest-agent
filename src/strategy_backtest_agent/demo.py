"""Small deterministic synthetic dataset, requiring no network or saved data."""

import math
from datetime import UTC, datetime, timedelta

from strategy_backtest_agent.models import Candle


def demo_candles(timeframe: str, days: int) -> list[Candle]:
    """Generate completed candles ending at a fixed UTC boundary."""
    unit = 60 if timeframe.endswith("m") else 3600 if timeframe.endswith("h") else 86400
    seconds = int(timeframe[:-1]) * unit
    count = days * 86400 // seconds
    # Bound resource use for accidental multi-year/minute demo requests.
    if count > 300_000:
        raise ValueError(
            "demo is limited to 300,000 candles; reduce days or use a larger timeframe"
        )
    end = datetime(2024, 7, 1, tzinfo=UTC)
    start = end - timedelta(seconds=count * seconds)
    candles = []
    previous = 30000.0
    for i in range(count):
        close = 30000 + 3000 * math.sin((i + 1) * 2 * math.pi / 96) + 0.5 * i
        candles.append(
            Candle(
                timestamp=start + timedelta(seconds=i * seconds),
                open=previous,
                high=max(previous, close) * 1.001,
                low=min(previous, close) * 0.999,
                close=close,
                volume=10,
            )
        )
        previous = close
    return candles
