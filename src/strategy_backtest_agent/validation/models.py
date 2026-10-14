"""Strict chronological validation configuration and reports; no new strategy language."""

from decimal import Decimal

from pydantic import AwareDatetime, Field, model_validator

from strategy_backtest_agent.comparison.models import SharedConfig, SharedData
from strategy_backtest_agent.models import BacktestResult, StrictModel
from strategy_backtest_agent.rules.models import RuleStrategy

WARNINGS = (
    "Test is Held-out evaluation, not guaranteed future performance. Holdout validity depends "
    "on selecting and freezing strategies before examining Test results.",
    "Return gap is descriptive: segment durations differ and total returns are not normalized.",
    "A single holdout cannot establish robustness; repeated inspection or strategy selection "
    "using Test results contaminates the holdout. "
    "No optimization or winner selection is performed.",
    "Finite RSI/EMA initialization can affect signals. "
    "Fills use configured modeled spread/slippage and exclude "
    "liquidity constraints; drawdown samples opens/closes, not intrabar extremes.",
)


def train_count(candle_count: int, ratio: float) -> int:
    """Floor the decimal ratio without binary float undercount at integer boundaries."""
    return int(Decimal(candle_count) * Decimal(str(ratio)))


class ValidationConfig(SharedConfig):
    train_ratio: float = Field(default=0.70, ge=0.50, le=0.90)


class ChronologicalSplit(StrictModel):
    train_ratio: float = Field(ge=0.50, le=0.90)
    train_start: AwareDatetime
    train_end: AwareDatetime
    test_start: AwareDatetime
    test_end: AwareDatetime
    train_candle_count: int = Field(ge=2)
    test_candle_count: int = Field(ge=2)
    policy: str = "floor(N * train_ratio); contiguous half-open UTC candle intervals [start, end)"

    @model_validator(mode="after")
    def chronological(self) -> "ChronologicalSplit":
        if not self.train_start < self.train_end == self.test_start < self.test_end:
            raise ValueError("segments must be chronological, contiguous and non-overlapping")
        total = self.train_candle_count + self.test_candle_count
        if train_count(total, self.train_ratio) != self.train_candle_count:
            raise ValueError("candle counts must match the requested split")
        return self


class SegmentResult(StrictModel):
    start: AwareDatetime
    end: AwareDatetime
    candle_count: int = Field(ge=2)
    warmup_candles: int = Field(ge=0)
    result: BacktestResult
    excess_return_pp: float | None


class StrategyValidationResult(StrictModel):
    id: str
    name: str
    strategy: RuleStrategy
    train: SegmentResult
    test: SegmentResult
    return_gap_pp: float


class ValidationReport(StrictModel):
    configuration: ValidationConfig
    shared_data: SharedData
    split: ChronologicalSplit
    results: list[StrategyValidationResult]
    methodology_warnings: list[str]
