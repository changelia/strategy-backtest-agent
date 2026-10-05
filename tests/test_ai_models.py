import pytest
from pydantic import ValidationError

from strategy_backtest_agent.ai.models import AIStrategyConfig, ParserOutput, StrategyExtraction


def test_defaults_and_existing_config_conversion() -> None:
    extraction = StrategyExtraction.model_validate(
        {
            "symbol": "BTCUSDT",
            "timeframe": None,
            "period_days": None,
            "initial_balance": None,
            "fee": None,
            "strategy": None,
        }
    )
    parsed = extraction.validated_config()
    assert parsed.model_dump() == {
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "period_days": 30,
        "initial_balance": 10000,
        "fee": 0.001,
        "strategy": {"type": "rsi", "period": 14, "entry_below": 30, "exit_above": 70},
    }
    config = parsed.to_backtest_config()
    assert config.symbol == "BTCUSDT"
    assert config.timeframe == "1h"
    assert config.initial_balance == 10000
    assert config.trading_fee == 0.001
    assert (config.rsi_period, config.entry_rsi, config.exit_rsi) == (14, 30, 70)


@pytest.mark.parametrize(
    "values",
    [
        {"symbol": ""},
        {"symbol": "BTC/USDT"},
        {"symbol": "btc"},
        {"timeframe": "1w"},
        {"period_days": 0},
        {"period_days": 366},
        {"period_days": "30"},
        {"period_days": True},
        {"initial_balance": 0},
        {"initial_balance": float("inf")},
        {"fee": -0.001},
        {"fee": 0.051},
        {"fee": float("nan")},
        {"unknown": 1},
        {"strategy": {"type": "macd"}},
        {"strategy": {"period": 1}},
        {"strategy": {"period": 201}},
        {"strategy": {"entry_below": 0}},
        {"strategy": {"exit_above": 100}},
        {"strategy": {"entry_below": 70, "exit_above": 30}},
        {"strategy": {"entry_below": 50, "exit_above": 50}},
    ],
)
def test_invalid_ai_configuration(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AIStrategyConfig.model_validate({"symbol": "BTCUSDT", **values})


@pytest.mark.parametrize("configuration,rejection", [(None, None), ({}, "unsupported")])
def test_parser_requires_exactly_one_outcome(configuration: object, rejection: object) -> None:
    with pytest.raises(ValidationError):
        ParserOutput.model_validate({"configuration": configuration, "rejection": rejection})
