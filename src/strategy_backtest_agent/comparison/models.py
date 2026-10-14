"""Validated independent strategies with one set of global trading assumptions."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from strategy_backtest_agent.market_data import TIMEFRAMES
from strategy_backtest_agent.models import (
    BacktestConfig,
    BacktestResult,
    Model,
    RSIStrategy,
    StrictModel,
)
from strategy_backtest_agent.rules.models import Indicator, RuleStrategy
from strategy_backtest_agent.strategy import legacy_rules

RankingCriterion = Literal["total_return", "excess_return", "max_drawdown", "profit_factor"]
RANKING_CRITERIA: tuple[RankingCriterion, ...] = (
    "total_return",
    "excess_return",
    "max_drawdown",
    "profit_factor",
)
WARMUP_POLICY = "shared prior closes: RSI=p+1; SMA=p; EMA=5*p (finite first-close seed)"


class NamedStrategy(StrictModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=80)
    strategy: RuleStrategy | RSIStrategy

    @field_validator("name")
    @classmethod
    def readable_name(cls, value: str) -> str:
        if not value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("strategy name must be nonempty and contain no control characters")
        return value.strip()

    def to_rules(self) -> RuleStrategy:
        if isinstance(self.strategy, RuleStrategy):
            return self.strategy
        rules = legacy_rules(
            BacktestConfig(
                rsi_period=self.strategy.period,
                entry_rsi=self.strategy.entry_below,
                exit_rsi=self.strategy.exit_above,
            )
        )
        assert rules is not None  # legacy RSI model is within the DSL period limits
        return rules


class MarketConfig(StrictModel):
    symbol: str = Field(pattern=r"^[A-Z0-9]{5,20}$")
    timeframe: str = "1h"
    period_days: int = Field(default=30, gt=0, le=365)
    initial_balance: float = Field(default=10000, gt=0)
    fee: float = Field(default=0.001, ge=0, le=0.05)
    evaluation_end: AwareDatetime | None = None

    @field_validator("timeframe")
    @classmethod
    def supported_timeframe(cls, value: str) -> str:
        if value not in TIMEFRAMES:
            raise ValueError("unsupported timeframe")
        return value

    @field_validator("evaluation_end")
    @classmethod
    def utc_end(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(UTC) if value is not None else None

    def to_backtest_config(self) -> BacktestConfig:
        return BacktestConfig.model_validate(
            {
                "symbol": self.symbol,
                "timeframe": self.timeframe,
                "initial_balance": self.initial_balance,
                "trading_fee": self.fee,
            }
        )


class SharedConfig(MarketConfig):
    strategies: list[NamedStrategy] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def unique_ids(self) -> "SharedConfig":
        ids = [strategy.id for strategy in self.strategies]
        if len(ids) != len(set(ids)):
            raise ValueError("strategy IDs must be unique")
        return self


class ComparisonConfig(SharedConfig):
    strategies: list[NamedStrategy] = Field(min_length=2, max_length=5)
    sort_by: RankingCriterion = "total_return"


class SharedData(Model):
    source: str = Field(min_length=1)
    evaluation_start: AwareDatetime
    evaluation_end: AwareDatetime
    first_candle_open: AwareDatetime
    last_candle_open: AwareDatetime
    candle_count: int = Field(gt=0)
    history_candle_count: int = Field(gt=0)
    warmup_candles: int = Field(ge=0)
    required_warmup_candles: int = Field(ge=0)
    warmup_policy: str = WARMUP_POLICY
    indicators: list[Indicator]
    candles_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class StrategyResult(Model):
    id: str
    name: str
    strategy: RuleStrategy
    result: BacktestResult
    excess_return_pp: float | None


class ComparisonResult(Model):
    configuration: ComparisonConfig
    shared_data: SharedData
    buy_and_hold_return_percent: float | None
    results: list[StrategyResult]
    ranking_criterion: RankingCriterion
    ranking: list[str]
