"""Deterministic adverse fill adjustments and quote-currency attribution, without market data."""

from collections.abc import Iterable
from typing import Literal

from pydantic import Field

from strategy_backtest_agent.models import (
    ExecutionConfig,
    ExecutionCostTotals,
    ExecutionFill,
    StrictModel,
)

EXECUTION_WARNINGS = (
    "OHLC prices are mid-price proxies; historical Binance candles do not provide bid/ask quotes.",
    "Spread and slippage are illustrative modeled adjustments, "
    "not separately observed historical costs.",
    "Open positions are marked at reference prices; costs apply only on actual fills. "
    "Full fills, fractional quantities and unlimited liquidity are assumed; "
    "no impact or partial fills.",
)


class ExecutionQuote(StrictModel):
    side: Literal["buy", "sell"]
    reference_price: float = Field(gt=0)
    fill_price: float = Field(gt=0)
    fee_rate: float = Field(ge=0, lt=1)
    spread_adjustment_per_unit: float = Field(ge=0)
    slippage_adjustment_per_unit: float = Field(ge=0)

    def fill(self, quantity: float, *, forced: bool = False) -> ExecutionFill:
        return ExecutionFill(
            side=self.side,
            reference_price=self.reference_price,
            fill_price=self.fill_price,
            quantity=quantity,
            fee=quantity * self.fill_price * self.fee_rate,
            spread_adjustment_per_unit=self.spread_adjustment_per_unit,
            slippage_adjustment_per_unit=self.slippage_adjustment_per_unit,
            modeled_spread_cost=quantity * self.spread_adjustment_per_unit,
            modeled_slippage_cost=quantity * self.slippage_adjustment_per_unit,
            forced=forced,
        )


def quote_execution(
    reference_price: float, side: Literal["buy", "sell"], config: ExecutionConfig
) -> ExecutionQuote:
    """Apply half the full spread plus adverse slippage once, directly to a reference price."""
    config = ExecutionConfig.model_validate(config.model_dump(warnings=False))
    factor = 1 + config.adverse_fraction if side == "buy" else 1 - config.adverse_fraction
    return ExecutionQuote(
        side=side,
        reference_price=reference_price,
        fill_price=reference_price * factor,
        fee_rate=config.fee_rate,
        spread_adjustment_per_unit=reference_price * (config.spread_bps / 2 / 10000),
        slippage_adjustment_per_unit=reference_price * (config.slippage_bps / 10000),
    )


def total_costs(fills: Iterable[ExecutionFill]) -> ExecutionCostTotals:
    items = list(fills)
    return ExecutionCostTotals(
        fees=sum(item.fee for item in items),
        modeled_spread_cost=sum(item.modeled_spread_cost for item in items),
        modeled_slippage_cost=sum(item.modeled_slippage_cost for item in items),
    )


def format_execution(config: ExecutionConfig) -> str:
    return (
        f"Execution: fee {config.fee_rate * 100:g}% per side; "
        f"full spread {config.spread_bps:g} bps; "
        f"adverse slippage {config.slippage_bps:g} bps per side; "
        "OHLC mid-price proxies; equity at reference prices"
    )


def format_costs(costs: ExecutionCostTotals) -> str:
    return (
        f"Fees charged: {costs.fees:.4f}; modeled spread cost: {costs.modeled_spread_cost:.4f}; "
        f"modeled slippage cost: {costs.modeled_slippage_cost:.4f} (quote currency)"
    )
