"""Local indicators with explicit warm-up periods."""

import math

import pandas as pd


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
