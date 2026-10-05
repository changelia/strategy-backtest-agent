from datetime import datetime

import pytest
from conftest import make_candles
from pydantic import ValidationError

from strategy_backtest_agent.models import BacktestConfig, Candle


@pytest.mark.parametrize(
    "kwargs",
    [
        {"initial_balance": 0},
        {"trading_fee": 1},
        {"trading_fee": -0.1},
        {"entry_rsi": 80},
        {"rsi_period": 0},
        {"initial_balance": float("inf")},
        {"symbol": "bad/symbol"},
    ],
)
def test_invalid_config(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        BacktestConfig.model_validate(kwargs)


def test_invalid_candle() -> None:
    data = make_candles([10])[0].model_dump()
    for update in ({"high": 9}, {"volume": -1}, {"close": 0}, {"timestamp": datetime(2024, 1, 1)}):
        with pytest.raises(ValidationError):
            Candle.model_validate(data | update)


def test_unsupported_timeframe() -> None:
    with pytest.raises(ValidationError):
        BacktestConfig.model_validate({"timeframe": "2w"})


def test_local_candle_and_trade_times_normalized_to_utc() -> None:
    from datetime import UTC, timedelta, timezone

    from strategy_backtest_agent.models import Trade

    local = datetime(2024, 1, 1, 4, tzinfo=timezone(timedelta(hours=4)))
    candle = Candle(timestamp=local, open=10, high=10, low=10, close=10, volume=1)
    assert candle.timestamp.tzinfo == UTC
    assert candle.timestamp.hour == 0
    trade = Trade(
        entry_time=local,
        exit_time=local,
        entry_price=10,
        exit_price=10,
        quantity=1,
        pnl=0,
        pnl_percent=0,
    )
    assert trade.entry_time.tzinfo == trade.exit_time.tzinfo == UTC
    assert '"entry_time":"2024-01-01T00:00:00Z"' in trade.model_dump_json()
