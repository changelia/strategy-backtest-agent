"""Shared settings are structurally global; strategies cannot override them."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from strategy_backtest_agent.comparison.models import ComparisonConfig, NamedStrategy
from strategy_backtest_agent.rules.models import Comparison


def settings(count: int = 2, /, **updates: object) -> dict[str, object]:
    return {
        "symbol": "BTCUSDT",
        "strategies": [
            {"id": f"rsi-{i}", "name": f"RSI {i}", "strategy": {"type": "rsi"}}
            for i in range(count)
        ],
        **updates,
    }


@pytest.mark.parametrize("count", [2, 5])
def test_valid_strategies_and_normalization(count: int) -> None:
    config = ComparisonConfig.model_validate(settings(count))
    assert len(config.strategies) == count
    entry = config.strategies[0].to_rules().entry
    assert isinstance(entry, Comparison)
    assert entry.operator == "<"
    assert config.to_backtest_config().initial_balance == 10000
    assert ComparisonConfig.model_validate_json(config.model_dump_json()) == config


@pytest.mark.parametrize("count", [0, 1, 6])
def test_strategy_count(count: int) -> None:
    with pytest.raises(ValidationError):
        ComparisonConfig.model_validate(settings(count))


def test_duplicate_ids() -> None:
    with pytest.raises(ValidationError, match="unique"):
        ComparisonConfig.model_validate(
            {
                "symbol": "BTCUSDT",
                "strategies": [{"id": "same", "name": "RSI", "strategy": {"type": "rsi"}}] * 2,
            }
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", ""),
        ("name", "  "),
        ("name", "line\nbreak"),
        ("name", "\x1b[31m"),
        ("id", ""),
        ("id", "space id"),
        ("name", "x" * 81),
        ("strategy", {"type": "macd"}),
        ("strategy", {"type": "rsi", "period": 1}),
        ("strategy", {"type": "rules", "entry": {"type": "and", "conditions": []}, "exit": {}}),
    ],
)
def test_invalid_named_strategy(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        NamedStrategy.model_validate(
            {"id": "rsi", "name": "RSI", "strategy": {"type": "rsi"}, field: value}
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("symbol", "BTC/USDT"),
        ("symbol", "btcusdt"),
        ("timeframe", "1w"),
        ("period_days", 0),
        ("period_days", 366),
        ("period_days", True),
        ("period_days", "90"),
        ("initial_balance", 0),
        ("initial_balance", float("inf")),
        ("fee", -0.001),
        ("fee", 0.051),
        ("fee", float("nan")),
        ("sort_by", "winner"),
        ("evaluation_end", datetime(2024, 1, 1)),
    ],
)
def test_invalid_shared_settings(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        ComparisonConfig.model_validate(settings(**{field: value}))


@pytest.mark.parametrize(
    "field,value",
    [
        ("symbol", "ETHUSDT"),
        ("timeframe", "4h"),
        ("initial_balance", 5000),
        ("fee", 0.01),
        ("period_days", 10),
    ],
)
def test_per_strategy_overrides_are_forbidden(field: str, value: object) -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        ComparisonConfig.model_validate(
            {
                "symbol": "BTCUSDT",
                "strategies": [
                    {"id": "a", "name": "A", "strategy": {"type": "rsi"}, field: value},
                    {"id": "b", "name": "B", "strategy": {"type": "rsi"}},
                ],
            }
        )


def test_fixed_end_is_utc() -> None:
    end = datetime(2024, 1, 2, 4, tzinfo=timezone(timedelta(hours=4)))
    config = ComparisonConfig.model_validate(settings(evaluation_end=end))
    assert config.evaluation_end == datetime(2024, 1, 2, tzinfo=UTC)
