"""Small deterministic synthetic dataset, requiring no network or saved data."""

import math
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from strategy_backtest_agent.models import Candle

if TYPE_CHECKING:
    from strategy_backtest_agent.comparison.models import SharedConfig


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


def research_demo_candles(config: "SharedConfig") -> list[Candle]:
    """Supply exact warm-up and evaluation candles to existing research engines."""
    from strategy_backtest_agent.comparison.engine import required_warmup
    from strategy_backtest_agent.rules.history import interval_duration

    duration = interval_duration(config.timeframe)
    required = required_warmup(config)
    extra_days = math.ceil(required * duration.total_seconds() / 86400)
    candles = demo_candles(config.timeframe, config.period_days + extra_days)
    end = candles[-1].timestamp + duration
    if config.evaluation_end is not None and config.evaluation_end != end:
        raise ValueError("--demo requires evaluation_end 2024-07-01T00:00:00Z or null")
    count = config.period_days * 86400 // int(duration.total_seconds()) + required
    return candles[-count:]
