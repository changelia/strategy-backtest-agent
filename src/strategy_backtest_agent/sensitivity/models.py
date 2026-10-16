"""Strict grid and report models using the existing strategy language."""

from typing import Literal

from pydantic import Field, model_validator

from strategy_backtest_agent.comparison.models import MarketConfig, SharedData
from strategy_backtest_agent.models import StrictModel
from strategy_backtest_agent.rules.models import IndicatorInitialization as IndicatorInitialization
from strategy_backtest_agent.rules.models import RuleStrategy
from strategy_backtest_agent.validation.models import ChronologicalSplit, SegmentResult

MAX_VARIANTS = 25
MAX_DIMENSIONS = 3
MIN_OBSERVATION_TRADES = 5
SIMILARITY_TOLERANCE_PP = 5.0
Number = int | float
INITIALIZATION_POLICY = (
    "indicator-local prior closes anchored at first Train open: RSI=p+1; SMA=p; "
    "EMA=5*p; MACD=10*(slow+signal); Bollinger=p (population std); ATR=20*p; "
    "finite indicator-local seeds independent of other grid periods"
)

WARNINGS = (
    "All performance is in-sample sensitivity analysis on Train only. Test is reserved and "
    "not evaluated; no strategy is ranked, selected or recommended.",
    "Repeated parameter experimentation can overfit Train. Freeze a preselected configuration "
    "before a separate explicit held-out evaluation; a previously inspected Test is contaminated.",
    "Statistics describe only this declared grid, not future profitability or robustness. "
    "Zero-trade and low-trade configurations are not evidence of stability.",
    "Neighbor observations use declared candidate order, a 5 pp similarity tolerance and at "
    "least 5 trades per configuration. These are descriptive conventions, not significance tests.",
    "RSI/EMA/MACD/ATR initialization is finite. "
    "Each indicator uses its own anchored prior history; "
    "adding grid periods cannot move an existing indicator seed. "
    "Fills use configured modeled spread/slippage and exclude liquidity constraints; "
    "drawdown samples opens and closes, not intrabar extremes.",
)


class SensitivitySharedData(SharedData):
    warmup_policy: str = INITIALIZATION_POLICY
    indicator_initializations: list[IndicatorInitialization]


class NumericRange(StrictModel):
    start: Number
    stop: Number
    step: Number = Field(gt=0)

    @model_validator(mode="after")
    def increasing(self) -> "NumericRange":
        if self.stop < self.start:
            raise ValueError("range stop must be >= start")
        return self


class NearbyValues(StrictModel):
    step: Number | None = Field(default=None, gt=0)
    steps: int = Field(default=1, ge=1, le=12)


class ParameterSpec(StrictModel):
    path: str = Field(min_length=1, max_length=200)
    coupled_paths: list[str] = Field(default_factory=list, max_length=39)
    values: list[Number] | None = Field(default=None, min_length=1, max_length=MAX_VARIANTS)
    range: NumericRange | None = None
    nearby: NearbyValues | None = None

    @model_validator(mode="after")
    def one_source(self) -> "ParameterSpec":
        if sum(source is not None for source in (self.values, self.range, self.nearby)) != 1:
            raise ValueError("specify exactly one of values, range or nearby")
        paths = [self.path, *self.coupled_paths]
        if len(paths) != len(set(paths)):
            raise ValueError("parameter paths must be unique, including coupled_paths")
        if self.values is not None and len(self.values) != len(set(self.values)):
            raise ValueError("duplicate candidate values are not allowed")
        return self


class SensitivityConfig(MarketConfig):
    base_strategy: RuleStrategy
    parameters: list[ParameterSpec] = Field(min_length=1, max_length=MAX_DIMENSIONS)
    train_ratio: float = Field(default=0.70, ge=0.50, le=0.90)

    @model_validator(mode="after")
    def valid_grid(self) -> "SensitivityConfig":
        # Runtime import keeps the grid's typed model dependencies acyclic.
        from strategy_backtest_agent.sensitivity.grid import expand_grid

        expand_grid(self.base_strategy, self.parameters)
        return self


class ParameterDefinition(StrictModel):
    path: str
    coupled_paths: list[str]
    base_value: Number
    values: list[Number]


class ParameterVariant(StrictModel):
    id: str
    coordinates: list[int]
    parameter_values: dict[str, Number]
    strategy: RuleStrategy


Observation = Literal[
    "insufficient_trades",
    "no_neighbors",
    "insufficient_neighbor_trades",
    "similar_to_all_neighbors",
    "isolated_positive_spike",
    "mixed_neighbors",
]


class VariantResult(StrictModel):
    variant_id: str
    train: SegmentResult
    observation: Observation


class NeighborComparison(StrictModel):
    first_variant_id: str
    second_variant_id: str
    parameter_path: str
    return_difference_pp: float
    sufficient_trades: bool


class SeriesPoint(StrictModel):
    value: Number
    variant_id: str
    return_percent: float
    total_trades: int


class ReturnMatrix(StrictModel):
    row_parameter: str
    column_parameter: str
    row_values: list[Number]
    column_values: list[Number]
    variant_ids: list[list[str]]
    returns_percent: list[list[float]]
    trade_counts: list[list[int]]


class SensitivitySummary(StrictModel):
    variant_count: int
    minimum_return_percent: float
    median_return_percent: float
    maximum_return_percent: float
    return_range_pp: float
    positive_return_percent: float
    outperforming_buy_and_hold_percent: float | None
    insufficient_trade_variant_ids: list[str]
    minimum_observation_trades: int = MIN_OBSERVATION_TRADES
    similarity_tolerance_pp: float = SIMILARITY_TOLERANCE_PP


class SensitivityReport(StrictModel):
    configuration: SensitivityConfig
    shared_data: SensitivitySharedData
    split: ChronologicalSplit
    parameters: list[ParameterDefinition]
    variants: list[ParameterVariant]
    results: list[VariantResult]
    summary: SensitivitySummary
    neighbors: list[NeighborComparison]
    ordered_series: list[SeriesPoint] | None
    matrix: ReturnMatrix | None
    execution_assumptions: str = (
        "fresh full-cash long-only portfolio per variant; completed Train close signals at "
        "next Train open; configured execution costs; forced liquidation at final Train close; "
        "no trades, benchmark, equity or indicator preparation on Test"
    )
    methodology_warnings: list[str]
