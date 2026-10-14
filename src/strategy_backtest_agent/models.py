"""Validated input and output models."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


class Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class StrictModel(Model):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False, strict=True)


class ExecutionConfig(StrictModel):
    fee_rate: float = Field(default=0.001, ge=0, lt=1)
    spread_bps: float = Field(default=0, ge=0)
    slippage_bps: float = Field(default=0, ge=0)

    @model_validator(mode="after")
    def positive_sell_factor(self) -> "ExecutionConfig":
        adverse = Decimal(str(self.spread_bps)) / 2 + Decimal(str(self.slippage_bps))
        if adverse >= 10000 or self.adverse_fraction >= 1:
            raise ValueError(
                "half spread + slippage must be below 10000 bps for positive sell fills"
            )
        return self

    @property
    def adverse_fraction(self) -> float:
        return (self.spread_bps / 2 + self.slippage_bps) / 10000


def normalize_execution(
    config: BaseModel, execution: ExecutionConfig | None, fee_alias: str, fee: float
) -> None:
    """Normalize construction-time aliases using revalidated values, including frozen models."""
    if execution is None:
        return None
    explicit_fee = "fee_rate" in execution.model_fields_set
    rate = execution.fee_rate if explicit_fee else fee
    if explicit_fee and fee_alias in config.model_fields_set and fee != rate:
        raise ValueError(f"{fee_alias} conflicts with execution.fee_rate")
    applied = ExecutionConfig.model_validate(
        {**execution.model_dump(warnings=False), "fee_rate": rate}
    )
    if fee == rate and execution == applied:
        return None
    validated = type(config).model_validate(
        {**config.model_dump(), fee_alias: rate, "execution": applied}
    )
    # A top-level after validator must return self for both __init__ and model_validate.
    # All assigned values have passed the complete model's validation above.
    object.__setattr__(config, fee_alias, getattr(validated, fee_alias))
    object.__setattr__(config, "execution", applied)


class ExecutionFill(StrictModel):
    side: Literal["buy", "sell"]
    reference_price: float = Field(gt=0)
    fill_price: float = Field(gt=0)
    quantity: float = Field(gt=0)
    fee: float = Field(ge=0)
    spread_adjustment_per_unit: float = Field(ge=0)
    slippage_adjustment_per_unit: float = Field(ge=0)
    modeled_spread_cost: float = Field(ge=0)
    modeled_slippage_cost: float = Field(ge=0)
    forced: bool = False


class ExecutionCostTotals(StrictModel):
    fees: float = Field(default=0, ge=0)
    modeled_spread_cost: float = Field(default=0, ge=0)
    modeled_slippage_cost: float = Field(default=0, ge=0)


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
    entry_execution: ExecutionFill | None = None
    exit_execution: ExecutionFill | None = None

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
    execution: ExecutionConfig | None = None
    rsi_period: int = Field(default=14, ge=1)
    entry_rsi: float = Field(default=30, ge=0, le=100)
    exit_rsi: float = Field(default=70, ge=0, le=100)

    @model_validator(mode="after")
    def execution_settings(self) -> "BacktestConfig":
        normalize_execution(self, self.execution, "trading_fee", self.trading_fee)
        return self

    def execution_config(self) -> ExecutionConfig:
        return self.execution or ExecutionConfig(fee_rate=self.trading_fee)

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

    execution: ExecutionConfig | None = None
    costs: ExecutionCostTotals = Field(default_factory=ExecutionCostTotals)
    benchmark_costs: ExecutionCostTotals | None = None
    equity_policy: Literal["reference_prices"] = "reference_prices"
    benchmark_policy: str = (
        "net first evaluation open to final close under the same execution costs"
    )
    execution_warnings: list[str] = Field(default_factory=list)
