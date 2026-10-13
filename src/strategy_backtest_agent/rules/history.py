"""UTC evaluation boundaries and finite historical initialization policy."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from strategy_backtest_agent.market_data import TIMEFRAMES, MarketDataProvider
from strategy_backtest_agent.models import Candle
from strategy_backtest_agent.rules.evaluator import warmup_count
from strategy_backtest_agent.rules.models import RuleStrategy


def interval_duration(timeframe: str) -> timedelta:
    if timeframe not in TIMEFRAMES:
        raise ValueError("unsupported timeframe")
    units = {"m": 60, "h": 3600, "d": 86400}
    return timedelta(seconds=int(timeframe[:-1]) * units[timeframe[-1]])


async def fetch_rule_history(
    provider: MarketDataProvider,
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    strategy: RuleStrategy,
) -> tuple[list[Candle], int]:
    """Fetch prior closes; fail explicitly if history is incomplete or discontinuous."""
    return await fetch_history(provider, symbol, timeframe, start, end, warmup_count(strategy))


async def fetch_history(
    provider: MarketDataProvider,
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    required: int,
) -> tuple[list[Candle], int]:
    """One provider call for the requested window plus a validated prior-candle count."""
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("evaluation boundaries must be aware and increasing")
    if type(required) is not int or required < 0:
        raise ValueError("required warm-up must be a nonnegative integer")
    start, end = start.astimezone(UTC), end.astimezone(UTC)
    duration = interval_duration(timeframe)
    candles = await provider.fetch_candles(symbol, timeframe, start - required * duration, end)
    return candles, validate_history(candles, timeframe, start, end, required)


def validate_history(
    candles: Sequence[Candle],
    timeframe: str,
    start: datetime,
    end: datetime,
    required: int,
) -> int:
    """Locate the shared boundary and reject missing, unfinished or out-of-range data."""
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("evaluation boundaries must be aware and increasing")
    if type(required) is not int or required < 0:
        raise ValueError("required warm-up must be a nonnegative integer")
    duration = interval_duration(timeframe)
    if any(not start - required * duration <= c.timestamp < end for c in candles):
        raise ValueError("provider returned candles outside requested range")
    if any(c.timestamp + duration > end for c in candles):
        raise ValueError("history contains unfinished candles")
    if any(
        b.timestamp - a.timestamp != duration for a, b in zip(candles, candles[1:], strict=False)
    ):
        raise ValueError("historical candles must be continuous and increasing")
    boundary = sum(c.timestamp < start for c in candles)
    if boundary < required:
        raise ValueError(
            f"insufficient warm-up history: need {required} prior candles, got {boundary}"
        )
    if boundary == len(candles):
        raise ValueError("no completed candles in requested evaluation period")
    if candles[boundary].timestamp >= start + duration:
        raise ValueError("historical data does not cover evaluation start")
    if candles[-1].timestamp + 2 * duration <= end:
        raise ValueError("historical data does not cover evaluation end")
    return boundary
