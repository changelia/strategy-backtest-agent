"""Closed, typed rule language; no executable expressions."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from strategy_backtest_agent.models import Model


class Price(Model):
    type: Literal["price"] = "price"


class Value(Model):
    type: Literal["value"] = "value"
    value: float


class Indicator(Model):
    type: Literal["indicator"] = "indicator"
    name: Literal["rsi", "sma", "ema"]
    period: int = Field(strict=True, ge=2, le=1000)

    @model_validator(mode="after")
    def period_limit(self) -> "Indicator":
        if self.name == "rsi" and self.period > 500:
            raise ValueError("RSI period must be at most 500")
        return self


Operand = Annotated[Price | Value | Indicator, Field(discriminator="type")]


class Comparison(Model):
    type: Literal["comparison"] = "comparison"
    left: Operand
    operator: Literal["<", "<=", ">", ">="]
    right: Operand


class Group(Model):
    type: Literal["and", "or"]
    conditions: list["Rule"] = Field(min_length=1, max_length=20)


Rule = Annotated[Comparison | Group, Field(discriminator="type")]
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
