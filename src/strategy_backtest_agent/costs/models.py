"""Strict illustrative execution scenarios, not market-cost estimates or optimization."""

from pydantic import Field, field_validator, model_validator

from strategy_backtest_agent.comparison.models import MarketConfig, NamedStrategy
from strategy_backtest_agent.execution import EXECUTION_WARNINGS
from strategy_backtest_agent.models import ExecutionConfig, StrictModel
from strategy_backtest_agent.rules.models import RuleStrategy
from strategy_backtest_agent.sensitivity.models import SensitivitySharedData
from strategy_backtest_agent.validation.models import ChronologicalSplit, SegmentResult

WARNINGS = (
    "Execution-cost scenarios are in-sample Train research on one frozen strategy. Test is "
    "reserved, not evaluated. No strategy or cost parameters are optimized or recommended.",
    "Scenario costs are illustrative assumptions, not measured Binance spreads or slippage. "
    "Fees inherit the shared rate unless a scenario explicitly supplies fee_rate.",
    *EXECUTION_WARNINGS,
)


class CostScenario(StrictModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=80)
    spread_bps: float = Field(default=0, ge=0)
    slippage_bps: float = Field(default=0, ge=0)
    fee_rate: float | None = Field(default=None, ge=0, lt=1)

    @field_validator("name")
    @classmethod
    def readable_name(cls, value: str) -> str:
        return NamedStrategy.readable_name(value)

    def execution_config(self, shared_fee: float) -> ExecutionConfig:
        return ExecutionConfig(
            fee_rate=shared_fee if self.fee_rate is None else self.fee_rate,
            spread_bps=self.spread_bps,
            slippage_bps=self.slippage_bps,
        )

    @model_validator(mode="after")
    def valid_costs(self) -> "CostScenario":
        self.execution_config(0.001)
        return self


class CostScenarioConfig(MarketConfig):
    strategy: RuleStrategy
    train_ratio: float = Field(default=0.70, ge=0.50, le=0.90)
    scenarios: list[CostScenario] = Field(min_length=2, max_length=8)

    @model_validator(mode="after")
    def valid_scenarios(self) -> "CostScenarioConfig":
        if len({scenario.id for scenario in self.scenarios}) != len(self.scenarios):
            raise ValueError("scenario IDs must be unique")
        baseline = self.scenarios[0]
        if baseline.spread_bps != 0 or baseline.slippage_bps != 0:
            raise ValueError("first scenario must be baseline with zero spread and slippage")
        if self.execution is not None and (
            self.execution.spread_bps or self.execution.slippage_bps
        ):
            raise ValueError("specify spread/slippage in scenarios, not at the shared level")
        for scenario in self.scenarios:
            scenario.execution_config(self.fee)
        return self


class CostScenarioResult(StrictModel):
    id: str
    name: str
    execution: ExecutionConfig
    train: SegmentResult
    return_difference_pp: float


class CostScenarioReport(StrictModel):
    configuration: CostScenarioConfig
    shared_data: SensitivitySharedData
    split: ChronologicalSplit
    baseline_id: str
    results: list[CostScenarioResult]
    methodology_warnings: list[str]
