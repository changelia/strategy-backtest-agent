"""Local indicators with explicit warm-up periods."""

import math
from collections.abc import Sequence

import pandas as pd

from strategy_backtest_agent.models import Candle


def _validate(series: pd.Series, period: int) -> None:
    if period < 1:
        raise ValueError("period must be positive")
    if not all(math.isfinite(float(value)) for value in series):
        raise ValueError("indicator input must contain finite values")


def sma(series: pd.Series, period: int) -> pd.Series:
    """Return the simple moving average after period observations."""
    _validate(series, period)
    return series.astype(float).rolling(period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """Return an EMA seeded with the first value, hiding its warm-up."""
    _validate(series, period)
    return series.astype(float).ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Return Wilder RSI with an SMA seed; flat windows have RSI 50."""
    _validate(series, period)
    result = pd.Series(float("nan"), index=series.index, dtype=float)
    if len(series) <= period:
        return result
    changes = series.astype(float).diff()
    gains = changes.clip(lower=0)
    losses = -changes.clip(upper=0)
    gain = float(gains.iloc[1 : period + 1].mean())
    loss = float(losses.iloc[1 : period + 1].mean())
    for i in range(period, len(series)):
        if i > period:
            gain = (gain * (period - 1) + float(gains.iloc[i])) / period
            loss = (loss * (period - 1) + float(losses.iloc[i])) / period
        result.iloc[i] = (
            50 if gain == loss == 0 else (100 if loss == 0 else 100 - 100 / (1 + gain / loss))
        )
    return result


def _positive_period(period: int) -> None:
    if type(period) is not int or period < 1:
        raise ValueError("period must be a positive integer")


def macd(
    series: pd.Series, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9
) -> dict[str, pd.Series]:
    """First-close adjust=False EMAs; signal seeds at first available MACD (slow-1).

    Fast/slow are hidden until their own periods; signal is hidden until signal_period
    available MACD observations. Returned line is available at slow_period-1,
    signal/histogram at slow_period+signal_period-2. No future observations seed an EMA.
    """
    for period in (fast_period, slow_period, signal_period):
        _positive_period(period)
    if fast_period >= slow_period:
        raise ValueError("MACD fast period must be strictly less than slow period")
    _validate(series, slow_period)
    line = ema(series, fast_period) - ema(series, slow_period)
    available = line.iloc[slow_period - 1 :]
    signal = pd.Series(float("nan"), index=series.index, dtype=float)
    if len(available):
        signal.iloc[slow_period - 1 :] = ema(available, signal_period).set_axis(
            signal.index[slow_period - 1 :]
        )
    histogram = line - signal
    if any(
        not math.isfinite(float(v))
        for part in (
            line.iloc[slow_period - 1 :],
            signal.iloc[slow_period + signal_period - 2 :],
            histogram.iloc[slow_period + signal_period - 2 :],
        )
        for v in part
    ):
        raise ValueError("MACD calculation produced non-finite values")
    return {"macd": line, "signal": signal, "histogram": histogram}


def bollinger(series: pd.Series, period: int = 20, multiplier: float = 2.0) -> dict[str, pd.Series]:
    """SMA middle with population rolling standard deviation (ddof=0)."""
    _positive_period(period)
    if isinstance(multiplier, bool) or not math.isfinite(multiplier) or multiplier <= 0:
        raise ValueError("Bollinger multiplier must be positive and finite")
    _validate(series, period)
    middle = sma(series, period)
    deviation = series.astype(float).rolling(period, min_periods=period).std(ddof=0)
    upper, lower = middle + multiplier * deviation, middle - multiplier * deviation
    if any(
        not math.isfinite(float(v))
        for part in (middle, upper, lower)
        for v in part.iloc[period - 1 :]
    ):
        raise ValueError("Bollinger calculation produced non-finite values")
    return {"middle": middle, "upper": upper, "lower": lower}


def atr(candles: Sequence[Candle], period: int = 14) -> pd.Series:
    """TR[0]=high-low; ATR SMA seed at period-1, then Wilder (p-1)*ATR/p+TR/p.

    Subsequent true ranges include gaps from the previous close. Revalidate OHLCV,
    including constructed model instances, before using high/low inputs.
    """
    _positive_period(period)
    history = [Candle.model_validate(c.model_dump(warnings=False)) for c in candles]
    if any(a.timestamp >= b.timestamp for a, b in zip(history, history[1:], strict=False)):
        raise ValueError("ATR candles must be strictly increasing")
    ranges = [
        max(
            c.high - c.low,
            abs(c.high - history[i - 1].close) if i else c.high - c.low,
            abs(c.low - history[i - 1].close) if i else c.high - c.low,
        )
        for i, c in enumerate(history)
    ]
    result = pd.Series(float("nan"), index=range(len(history)), dtype=float)
    if len(history) < period:
        return result
    value = sum(ranges[:period]) / period
    for i in range(period - 1, len(history)):
        if i >= period:
            value = value * ((period - 1) / period) + ranges[i] / period
        if not math.isfinite(value):
            raise ValueError("ATR calculation produced non-finite values")
        result.iloc[i] = value
    return result
