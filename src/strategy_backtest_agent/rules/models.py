"""Closed, typed rule language; no executable expressions."""

from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from strategy_backtest_agent.models import Model, StrictModel


class Price(Model):
    type: Literal["price"] = "price"


class Value(Model):
    type: Literal["value"] = "value"
    value: float = Field(strict=True)


class Indicator(Model):
    type: Literal["indicator"] = "indicator"
    name: Literal["rsi", "sma", "ema"]
    period: int = Field(strict=True, ge=2, le=1000)

    @model_validator(mode="after")
    def period_limit(self) -> "Indicator":
        if self.name == "rsi" and self.period > 500:
            raise ValueError("RSI period must be at most 500")
        return self


class MACDIndicator(Model):
    type: Literal["indicator"] = "indicator"
    name: Literal["macd"]
    fast_period: int = Field(default=12, strict=True, ge=1, le=1000)
    slow_period: int = Field(default=26, strict=True, ge=1, le=1000)
    signal_period: int = Field(default=9, strict=True, ge=1, le=1000)
    component: Literal["macd", "signal", "histogram"] = "macd"

    @model_validator(mode="after")
    def ordered(self) -> "MACDIndicator":
        if self.fast_period >= self.slow_period:
            raise ValueError("MACD fast_period must be strictly less than slow_period")
        return self


class BollingerIndicator(Model):
    type: Literal["indicator"] = "indicator"
    name: Literal["bollinger"]
    period: int = Field(default=20, strict=True, ge=1, le=1000)
    multiplier: float = Field(default=2.0, strict=True, gt=0)
    component: Literal["upper", "middle", "lower"]


class ATRIndicator(Model):
    type: Literal["indicator"] = "indicator"
    name: Literal["atr"]
    period: int = Field(default=14, strict=True, ge=1, le=1000)


TechnicalIndicator = Indicator | MACDIndicator | BollingerIndicator | ATRIndicator
INDICATOR_TYPES = (Indicator, MACDIndicator, BollingerIndicator, ATRIndicator)
Operand = Price | Value | TechnicalIndicator


class IndicatorInitialization(StrictModel):
    indicator: TechnicalIndicator
    prior_candle_count: int = Field(ge=0)
    history_start: AwareDatetime
    input_fields: list[str] = Field(default_factory=lambda: ["close"])
    seed_policy: str = "legacy finite initialization"


class Comparison(Model):
    type: Literal["comparison"] = "comparison"
    left: Operand
    operator: Literal["<", "<=", ">", ">="]
    right: Operand


class Group(Model):
    type: Literal["and", "or"]
    conditions: list["Rule"] = Field(min_length=1, max_length=20)


Rule = Comparison | Group
Group.model_rebuild()


class RuleStrategy(Model):
    type: Literal["rules"] = "rules"
    entry: Rule
    exit: Rule

    @model_validator(mode="after")
    def complexity(self) -> "RuleStrategy":
        def count(rule: Rule, depth: int) -> int:
            if depth > 5:
                raise ValueError("maximum rule depth is 5 (root is depth 1)")
            if isinstance(rule, Comparison):
                return 1
            return sum(count(child, depth + 1) for child in rule.conditions)

        if count(self.entry, 1) + count(self.exit, 1) > 20:
            raise ValueError("maximum comparisons per strategy is 20")
        return self
