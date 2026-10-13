"""Finite initialization history stays separate from the evaluation portfolio."""

import asyncio
from datetime import UTC, datetime, timedelta, timezone

import pytest
from conftest import make_candles
from test_rules import comparison, indicator, strategy

from strategy_backtest_agent.backtester import run_backtest
from strategy_backtest_agent.models import BacktestConfig, Candle
from strategy_backtest_agent.rules.evaluator import prepare_indicators, warmup_count
from strategy_backtest_agent.rules.history import fetch_rule_history
from strategy_backtest_agent.rules.models import RuleStrategy


class Provider:
    def __init__(self, candles: list[Candle]) -> None:
        self.candles = candles
        self.request: tuple[datetime, datetime] | None = None

    async def fetch_candles(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Candle]:
        self.request = (start, end)
        return [c for c in self.candles if start <= c.timestamp < end]


def fetch(
    provider: Provider, start: datetime, end: datetime, rules: RuleStrategy
) -> tuple[list[Candle], int]:
    return asyncio.run(fetch_rule_history(provider, "BTCUSDT", "1h", start, end, rules))


@pytest.mark.parametrize(
    "name,period,expected", [("sma", 20, 20), ("rsi", 14, 15), ("ema", 200, 1000)]
)
def test_policy(name: str, period: int, expected: int) -> None:
    assert warmup_count(strategy(comparison(indicator(name, period)))) == expected


def test_requested_range_and_utc_boundaries() -> None:
    candles = make_candles([10] * 20)
    provider = Provider(candles)
    start = candles[10].timestamp.astimezone(timezone(timedelta(hours=4)))
    end = candles[-1].timestamp + timedelta(hours=1)
    rules = strategy(comparison(indicator("ema", 2)))
    history, boundary = fetch(provider, start, end, rules)
    assert provider.request == (candles[0].timestamp, end)
    assert boundary == 10
    assert history[boundary:] == candles[10:]
    assert history[boundary].timestamp.tzinfo == UTC


@pytest.mark.parametrize("kind", ["short", "gap", "late_start", "early_end", "empty"])
def test_insufficient_history_reports_limitation(kind: str) -> None:
    candles = make_candles([10] * 20)
    source = {
        "short": candles[1:],
        "gap": candles[:3] + candles[4:],
        "late_start": candles[:10] + candles[12:],
        "early_end": candles[:-2],
        "empty": [],
    }[kind]
    with pytest.raises(ValueError, match="history|continuous|evaluation"):
        fetch(
            Provider(source),
            candles[10].timestamp,
            candles[-1].timestamp + timedelta(hours=1),
            strategy(comparison(indicator("ema", 2))),
        )


def test_no_warmup_trades_equity_or_benchmark_contamination() -> None:
    candles = make_candles([1000.0, 500.0, 10.0, 10.0, 10.0, 20.0])
    rules = strategy(
        comparison({"type": "price"}, ">", {"type": "value", "value": 0}),
        comparison({"type": "price"}, "<", {"type": "value", "value": 0}),
    )
    config = BacktestConfig(trading_fee=0, initial_balance=1000)
    result = run_backtest(candles, config, rules, evaluation_start=3)
    assert result.trades[0].entry_time == candles[4].timestamp
    assert result.trades[0].quantity == 100
    assert result.final_balance == 2000
    assert result.buy_and_hold_return_percent == 100
    assert result.max_drawdown_percent == 0


def test_ema_first_close_seed_and_convergence() -> None:
    candles = make_candles([100.0] + [10.0] * 10)
    rules = strategy(comparison(indicator("ema", 2)))
    context = prepare_indicators(candles, rules)
    values = context.indicators[("ema", 2)]
    assert values[1] == pytest.approx(100 / 3 + 20 / 3)
    assert values[10] == pytest.approx(10 + 90 * (1 / 3) ** 10)
    # Finite history converges; it does not erase seed dependence exactly.
    assert values[10] > 10


def test_history_cannot_change_with_future_prices() -> None:
    rule = strategy(comparison(indicator("ema", 2)))
    first = prepare_indicators(make_candles([10, 9, 8, 12]), rule)
    second = prepare_indicators(make_candles([10, 9, 8, 1000]), rule)
    assert first.indicators[("ema", 2)][1:3] == second.indicators[("ema", 2)][1:3]


@pytest.mark.parametrize("boundary", [-1, 4])
def test_invalid_evaluation_index(boundary: int) -> None:
    with pytest.raises(ValueError, match="evaluation_start"):
        run_backtest(make_candles([10, 10]), BacktestConfig(), evaluation_start=boundary)


def test_explicit_rsi_warmup_intentionally_changes_initial_signals() -> None:
    from strategy_backtest_agent.strategy import legacy_rules

    candles = make_candles([10, 9, 8, 7, 6, 5])
    config = BacktestConfig(rsi_period=2, trading_fee=0)
    rules = legacy_rules(config)
    assert rules is not None
    # Earlier Wilder seed enables a first evaluation-close signal. Legacy mode
    # starts its seed inside the requested period and has no executable signal here.
    initialized = run_backtest(candles, config, rules, evaluation_start=3)
    legacy = run_backtest(candles[3:], config)
    assert initialized.total_trades == 1
    assert legacy.total_trades == 0
    assert initialized.trades[0].entry_time == candles[4].timestamp
    assert initialized.buy_and_hold_return_percent == legacy.buy_and_hold_return_percent
