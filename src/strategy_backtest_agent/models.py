"""Validated input and output models."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


class Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class Candle(Model):
    timestamp: AwareDatetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        """Keep all candle timestamps in UTC, including locally supplied data."""
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_prices(self) -> "Candle":
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError("OHLC prices must lie within low and high")
        return self


class Trade(Model):
    entry_time: AwareDatetime
    entry_price: float = Field(gt=0)
    exit_time: AwareDatetime
    exit_price: float = Field(gt=0)
    quantity: float = Field(gt=0)
    pnl: float
    pnl_percent: float

    @field_validator("entry_time", "exit_time")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        """Use UTC consistently for trade timestamps."""
        return value.astimezone(UTC)


class BacktestConfig(Model):
    symbol: str = Field(default="BTCUSDT", pattern=r"^[A-Z0-9]+$")
    timeframe: Literal[
        "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"
    ] = "1h"
    initial_balance: float = Field(default=10000, gt=0)
    trading_fee: float = Field(default=0.001, ge=0, lt=1)
    rsi_period: int = Field(default=14, ge=1)
    entry_rsi: float = Field(default=30, ge=0, le=100)
    exit_rsi: float = Field(default=70, ge=0, le=100)

    @model_validator(mode="after")
    def validate_thresholds(self) -> "BacktestConfig":
        if self.entry_rsi >= self.exit_rsi:
            raise ValueError("entry_rsi must be below exit_rsi")
        return self


class BacktestResult(Model):
    initial_balance: float
    final_balance: float
    total_return_percent: float
    buy_and_hold_return_percent: float | None
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float | None
    max_drawdown_percent: float
    profit_factor: float | None
    trades: list[Trade]
