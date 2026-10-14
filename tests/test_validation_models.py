"""Strict validation globals and split metadata."""

import math

import pytest
from pydantic import ValidationError
from test_comparison_engine import END, config

from strategy_backtest_agent.validation.models import ChronologicalSplit, ValidationConfig


def settings(**updates: object) -> ValidationConfig:
    values = config().model_dump()
    values.pop("sort_by")
    return ValidationConfig.model_validate({**values, **updates})


@pytest.mark.parametrize("ratio", [0.5, 0.7, 0.9])
def test_valid_ratios(ratio: float) -> None:
    assert settings(train_ratio=ratio).train_ratio == ratio


@pytest.mark.parametrize("ratio", [0.49, 0.91, 0, 1, True, "0.7", math.nan, math.inf])
def test_invalid_ratios(ratio: object) -> None:
    with pytest.raises(ValidationError):
        settings(train_ratio=ratio)


@pytest.mark.parametrize("count", [1, 2, 5])
def test_strategy_counts_and_default(count: int) -> None:
    base = settings().strategies[0].model_dump()
    entries = [{**base, "id": f"s{i}"} for i in range(count)]
    assert len(settings(strategies=entries).strategies) == count
    assert settings().train_ratio == 0.7


@pytest.mark.parametrize("kind", ["none", "six", "duplicate", "sort", "optimization", "override"])
def test_invalid_config(kind: str) -> None:
    entries = [item.model_dump() for item in settings().strategies]
    changes: dict[str, object] = {}
    if kind == "none":
        changes["strategies"] = []
    elif kind == "six":
        changes["strategies"] = [{**entries[0], "id": f"s{i}"} for i in range(6)]
    elif kind == "duplicate":
        changes["strategies"] = [entries[0], entries[0]]
    elif kind == "override":
        changes["strategies"] = [{**entries[0], "fee": 0.01}]
    else:
        changes["sort_by" if kind == "sort" else "optimization"] = "total_return"
    with pytest.raises(ValidationError):
        settings(**changes)


def test_split_rejects_overlap_and_wrong_count() -> None:
    from datetime import timedelta

    values = {
        "train_ratio": 0.5,
        "train_start": END - timedelta(hours=4),
        "train_end": END - timedelta(hours=2),
        "test_start": END - timedelta(hours=2),
        "test_end": END,
        "train_candle_count": 2,
        "test_candle_count": 2,
    }
    ChronologicalSplit.model_validate(values)
    with pytest.raises(ValidationError, match="chronological"):
        ChronologicalSplit.model_validate({**values, "test_start": END - timedelta(hours=3)})
    with pytest.raises(ValidationError, match="counts"):
        ChronologicalSplit.model_validate({**values, "train_candle_count": 3})


def test_decimal_ratio_does_not_undercount_integer_boundary() -> None:
    from strategy_backtest_agent.validation.models import train_count

    assert train_count(90, 0.7) == 63
    assert train_count(100, 0.58) == 58
    assert train_count(24, 0.7) == 16
