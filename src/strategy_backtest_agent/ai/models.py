"""Strict extraction schema and validated RSI or rule configuration."""

from typing import Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from strategy_backtest_agent.comparison.models import ComparisonConfig, RankingCriterion
from strategy_backtest_agent.market_data import TIMEFRAMES
from strategy_backtest_agent.models import (
    BacktestConfig,
    ExecutionConfig,
    normalize_execution,
)
from strategy_backtest_agent.models import RSIStrategy as RSIStrategy
from strategy_backtest_agent.models import StrictModel as StrictModel
from strategy_backtest_agent.rules.models import RuleStrategy
from strategy_backtest_agent.sensitivity.models import ParameterSpec, SensitivityConfig
from strategy_backtest_agent.validation.models import ValidationConfig
from strategy_backtest_agent.walk_forward.models import WalkForwardConfig


class AIStrategyConfig(StrictModel):
    symbol: str = Field(pattern=r"^[A-Z0-9]{5,20}$")
    timeframe: str = "1h"
    period_days: int = Field(default=30, gt=0, le=365)
    initial_balance: float = Field(default=10000, gt=0)
    fee: float = Field(default=0.001, ge=0, le=0.05)
    execution: ExecutionConfig | None = None
    strategy: RSIStrategy | RuleStrategy = Field(default_factory=RSIStrategy)

    @model_validator(mode="after")
    def execution_settings(self) -> "AIStrategyConfig":
        normalize_execution(self, self.execution, "fee", self.fee)
        return self

    def execution_config(self) -> ExecutionConfig:
        return self.execution or ExecutionConfig(fee_rate=self.fee)

    @field_validator("timeframe")
    @classmethod
    def supported_timeframe(cls, value: str) -> str:
        if value not in TIMEFRAMES:
            raise ValueError("unsupported timeframe")
        return value

    def to_backtest_config(self) -> BacktestConfig:
        """Map portfolio settings; rule strategies are passed separately to the engine."""
        legacy = self.strategy if isinstance(self.strategy, RSIStrategy) else RSIStrategy()
        return BacktestConfig.model_validate(
            {
                "symbol": self.symbol,
                "timeframe": self.timeframe,
                "initial_balance": self.initial_balance,
                "trading_fee": self.fee,
                "execution": self.execution,
                "rsi_period": legacy.period,
                "entry_rsi": legacy.entry_below,
                "exit_rsi": legacy.exit_above,
            }
        )


class RSIExtraction(StrictModel):
    # Required nullable fields satisfy Structured Outputs without asking AI to fill defaults.
    period: int | None
    entry_below: float | None
    exit_above: float | None


class ExecutionExtraction(StrictModel):
    fee_rate: float | None
    spread_bps: float | None
    slippage_bps: float | None


class StrategyExtraction(StrictModel):
    symbol: str | None
    timeframe: str | None
    period_days: int | None
    initial_balance: float | None
    fee: float | None
    execution: ExecutionExtraction | None = None
    strategy: RSIExtraction | RuleStrategy | None

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
            "crossover",
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


class ComparisonStrategyExtraction(StrictModel):
    name: str
    strategy: RuleStrategy


class ComparisonExtraction(StrictModel):
    symbol: str | None
    timeframe: str | None
    period_days: int | None
    initial_balance: float | None
    fee: float | None
    execution: ExecutionExtraction | None = None
    strategies: list[ComparisonStrategyExtraction] = Field(min_length=2, max_length=5)
    evaluation_end: AwareDatetime | None
    sort_by: RankingCriterion | None

    def validated_config(self) -> ComparisonConfig:
        values = self.model_dump(exclude_none=True)
        # IDs represent request order and are assigned by Python, not invented by the model.
        values["strategies"] = [
            {"id": f"strategy-{i}", **item.model_dump()}
            for i, item in enumerate(self.strategies, start=1)
        ]
        return ComparisonConfig.model_validate(values)


class ComparisonParserOutput(StrictModel):
    configuration: ComparisonExtraction | None
    rejection: (
        Literal[
            "unsupported",
            "ambiguous",
            "missing_symbol",
            "inconsistent_settings",
            "strategy_count",
        ]
        | None
    )

    @model_validator(mode="after")
    def one_outcome(self) -> "ComparisonParserOutput":
        if (self.configuration is None) == (self.rejection is None):
            raise ValueError("parser must return either configuration or rejection")
        return self


class ValidationExtraction(StrictModel):
    symbol: str | None
    timeframe: str | None
    period_days: int | None
    initial_balance: float | None
    fee: float | None
    execution: ExecutionExtraction | None = None
    strategies: list[ComparisonStrategyExtraction] = Field(min_length=1, max_length=5)
    evaluation_end: AwareDatetime | None
    train_ratio: float | None

    def validated_config(self) -> ValidationConfig:
        values = self.model_dump(exclude_none=True)
        values["strategies"] = [
            {"id": f"strategy-{i}", **item.model_dump()}
            for i, item in enumerate(self.strategies, start=1)
        ]
        return ValidationConfig.model_validate(values)


class ValidationParserOutput(StrictModel):
    configuration: ValidationExtraction | None
    rejection: (
        Literal[
            "unsupported", "ambiguous", "missing_symbol", "inconsistent_settings", "strategy_count"
        ]
        | None
    )

    @model_validator(mode="after")
    def one_outcome(self) -> "ValidationParserOutput":
        if (self.configuration is None) == (self.rejection is None):
            raise ValueError("parser must return either configuration or rejection")
        return self


class SensitivityExtraction(StrictModel):
    symbol: str | None
    timeframe: str | None
    period_days: int | None
    initial_balance: float | None
    fee: float | None
    execution: ExecutionExtraction | None = None
    evaluation_end: AwareDatetime | None
    train_ratio: float | None
    base_strategy: RuleStrategy
    parameters: list[ParameterSpec] = Field(min_length=1, max_length=3)

    def validated_config(self) -> SensitivityConfig:
        return SensitivityConfig.model_validate(self.model_dump(exclude_none=True))


class SensitivityParserOutput(StrictModel):
    configuration: SensitivityExtraction | None
    rejection: Literal["unsupported", "ambiguous", "missing_symbol", "invalid_grid"] | None

    @model_validator(mode="after")
    def one_outcome(self) -> "SensitivityParserOutput":
        if (self.configuration is None) == (self.rejection is None):
            raise ValueError("parser must return either configuration or rejection")
        return self


class WindowExtraction(StrictModel):
    mode: Literal["rolling", "expanding"] | None
    train_days: int
    test_days: int
    step_days: int | None
    max_folds: int | None


class WalkForwardExtraction(StrictModel):
    symbol: str | None
    timeframe: str | None
    period_days: int | None
    initial_balance: float | None
    fee: float | None
    execution: ExecutionExtraction | None
    strategies: list[ComparisonStrategyExtraction] = Field(min_length=1, max_length=5)
    evaluation_end: AwareDatetime | None
    windows: WindowExtraction
    stitch_oos: bool | None

    def validated_config(self) -> WalkForwardConfig:
        values = self.model_dump(exclude_none=True)
        values["strategies"] = [
            {"id": f"strategy-{i}", **item.model_dump()}
            for i, item in enumerate(self.strategies, start=1)
        ]
        return WalkForwardConfig.model_validate(values)


class WalkForwardParserOutput(StrictModel):
    configuration: WalkForwardExtraction | None
    rejection: (
        Literal[
            "unsupported", "ambiguous", "missing_symbol", "inconsistent_settings", "strategy_count"
        ]
        | None
    )

    @model_validator(mode="after")
    def one_outcome(self) -> "WalkForwardParserOutput":
        if (self.configuration is None) == (self.rejection is None):
            raise ValueError("parser must return either configuration or rejection")
        return self
