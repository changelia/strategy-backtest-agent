"""Strict fixed-strategy protocol and reproducible report models."""

from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from strategy_backtest_agent.comparison.models import SharedConfig
from strategy_backtest_agent.models import StrictModel
from strategy_backtest_agent.rules.history import interval_duration
from strategy_backtest_agent.rules.models import RuleStrategy
from strategy_backtest_agent.sensitivity.models import SensitivitySharedData
from strategy_backtest_agent.validation.models import SegmentResult

WARNINGS = (
    "Fixed predeclared strategies only; Train is diagnostic. "
    "No optimization, ranking or selection.",
    "Multiple historical OOS folds do not establish robustness or future profitability. "
    "Strategies selected after inspecting this history do not have independent held-out evidence.",
    "Each Train and Test resets capital and positions; signals never cross segment boundaries.",
    "Indicator-local finite seeds are anchored before the first evaluation candle and continued "
    "causally across folds. RSI/EMA/MACD/ATR seed effects can remain near thresholds.",
    "Stitched index compounds normalized independent Test fold returns at fold endpoints only; "
    "it is not a portfolio carrying positions, and has no continuous drawdown statistic.",
    "Constant modeled costs, full fills and unlimited liquidity are assumptions; drawdown "
    "samples opens/closes, not intrabar extremes. Repeated evaluation can overfit history.",
)


class WalkForwardWindowConfig(StrictModel):
    mode: Literal["rolling", "expanding"] = "rolling"
    train_days: int = Field(gt=0)
    test_days: int = Field(gt=0)
    step_days: int | None = Field(default=None, gt=0)
    max_folds: int = Field(default=50, ge=2, le=100)

    @model_validator(mode="after")
    def nonoverlap(self) -> "WalkForwardWindowConfig":
        if self.step_days is not None and self.step_days < self.test_days:
            raise ValueError(
                "step must be at least Test duration; overlapping Test windows rejected"
            )
        return self

    def counts(self, timeframe: str) -> tuple[int, int, int]:
        seconds = int(interval_duration(timeframe).total_seconds())
        values = (self.train_days, self.test_days, self.step_days or self.test_days)
        if any(days * 86400 % seconds for days in values):
            raise ValueError("window durations must align to exact timeframe candle counts")
        counts = tuple(days * 86400 // seconds for days in values)
        if min(counts[:2]) < 2:
            raise ValueError("each segment requires at least two candles")
        return counts[0], counts[1], counts[2]


class WalkForwardConfig(SharedConfig):
    windows: WalkForwardWindowConfig
    stitch_oos: bool = False

    @model_validator(mode="after")
    def protocol(self) -> "WalkForwardConfig":
        train, test, step = self.windows.counts(self.timeframe)
        total_seconds = self.period_days * 86400
        duration = int(interval_duration(self.timeframe).total_seconds())
        if total_seconds % duration:
            raise ValueError("historical duration must align to candles")
        count = 1 + (total_seconds // duration - train - test) // step
        if count < 2:
            raise ValueError("walk-forward requires at least two complete folds")
        if count > self.windows.max_folds:
            raise ValueError("complete fold count exceeds max_folds; change the declared protocol")
        if self.stitch_oos and step != test:
            raise ValueError("stitched OOS requires contiguous Test windows; gaps unsupported")
        return self


class WalkForwardFold(StrictModel):
    id: str
    train_start: AwareDatetime
    train_end: AwareDatetime
    test_start: AwareDatetime
    test_end: AwareDatetime
    train_candle_count: int = Field(ge=2)
    test_candle_count: int = Field(ge=2)

    @model_validator(mode="after")
    def chronological(self) -> "WalkForwardFold":
        if not self.train_start < self.train_end == self.test_start < self.test_end:
            raise ValueError("Train must strictly precede contiguous Test")
        return self


class FoldStrategyResult(StrictModel):
    fold_id: str
    strategy_id: str
    name: str
    strategy: RuleStrategy
    train: SegmentResult
    test: SegmentResult


class IndexPoint(StrictModel):
    time: AwareDatetime
    value: float = Field(ge=0)


class WalkForwardSummary(StrictModel):
    strategy_id: str
    fold_count: int
    total_test_trades: int
    positive_test_folds: int
    positive_test_fraction: float
    median_test_return_percent: float
    minimum_test_return_percent: float
    maximum_test_return_percent: float
    median_test_max_drawdown_percent: float
    median_test_excess_return_pp: float | None
    outperforming_test_folds: int
    stitched_oos_index: list[IndexPoint] | None


class WalkForwardReport(StrictModel):
    configuration: WalkForwardConfig
    shared_data: SensitivitySharedData
    folds: list[WalkForwardFold]
    unused_trailing_candles: int = Field(ge=0)
    results: list[FoldStrategyResult]
    summaries: list[WalkForwardSummary]
    window_policy: str = (
        "Exact candle counts; half-open UTC intervals; complete folds only; "
        "step >= Test count; reject excess folds instead of truncating"
    )
    aggregate_policy: str = (
        "Test only: unweighted fold medians and extrema; positive means return > 0; "
        "outperformance means net excess > 0; no pooled win rate, profit factor or drawdown"
    )
    methodology_warnings: list[str]
