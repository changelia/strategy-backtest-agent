"""Strict extraction schema and validated RSI configuration."""

from typing import Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from strategy_backtest_agent.market_data import TIMEFRAMES
from strategy_backtest_agent.models import BacktestConfig, Model


class StrictModel(Model):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False, strict=True)


class RSIStrategy(StrictModel):
    type: Literal["rsi"] = "rsi"
    period: int = Field(default=14, ge=2, le=200)
    entry_below: float = Field(default=30, gt=0, lt=100)
    exit_above: float = Field(default=70, gt=0, lt=100)

    @model_validator(mode="after")
    def thresholds(self) -> "RSIStrategy":
        if self.entry_below >= self.exit_above:
            raise ValueError("entry threshold must be lower than exit threshold")
        return self


class AIStrategyConfig(StrictModel):
    symbol: str = Field(pattern=r"^[A-Z0-9]{5,20}$")
    timeframe: str = "1h"
    period_days: int = Field(default=30, gt=0, le=365)
    initial_balance: float = Field(default=10000, gt=0)
    fee: float = Field(default=0.001, ge=0, le=0.05)
    strategy: RSIStrategy = Field(default_factory=RSIStrategy)

    @field_validator("timeframe")
    @classmethod
    def supported_timeframe(cls, value: str) -> str:
        if value not in TIMEFRAMES:
            raise ValueError("unsupported timeframe")
        return value

    def to_backtest_config(self) -> BacktestConfig:
        """Map validated AI settings to the existing engine without changing semantics."""
        return BacktestConfig.model_validate(
            {
                "symbol": self.symbol,
                "timeframe": self.timeframe,
                "initial_balance": self.initial_balance,
                "trading_fee": self.fee,
                "rsi_period": self.strategy.period,
                "entry_rsi": self.strategy.entry_below,
                "exit_rsi": self.strategy.exit_above,
            }
        )


class RSIExtraction(StrictModel):
    # Required nullable fields satisfy Structured Outputs without asking AI to fill defaults.
    period: int | None
    entry_below: float | None
    exit_above: float | None


class StrategyExtraction(StrictModel):
    symbol: str | None
    timeframe: str | None
    period_days: int | None
    initial_balance: float | None
    fee: float | None
    strategy: RSIExtraction | None

    def validated_config(self) -> AIStrategyConfig:
        """Apply defaults only to omitted values, preserving explicit invalid values."""
        values = self.model_dump(exclude_none=True)
        return AIStrategyConfig.model_validate(values)


class ParserOutput(StrictModel):
    configuration: StrategyExtraction | None
    rejection: (
        Literal[
            "unsupported",
            "ambiguous",
            "missing_symbol",
            "macd",
            "bollinger_bands",
            "short_selling",
            "leverage",
            "stop_loss",
            "take_profit",
            "multiple_conditions",
            "multiple_symbols",
            "live_trading",
            "prediction",
        ]
        | None
    )

    @model_validator(mode="after")
    def one_outcome(self) -> "ParserOutput":
        if (self.configuration is None) == (self.rejection is None):
            raise ValueError("parser must return either configuration or rejection")
        return self
