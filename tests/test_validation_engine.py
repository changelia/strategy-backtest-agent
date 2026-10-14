"""Synthetic accounting oracles and chronological leakage/portfolio isolation checks."""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from conftest import make_candles
from test_comparison_engine import END, Provider, history, named
from test_rules import comparison, indicator, strategy
from test_validation_models import settings

from strategy_backtest_agent import indicators, metrics
from strategy_backtest_agent.backtester import run_backtest
from strategy_backtest_agent.models import BacktestConfig, BacktestResult, Candle
from strategy_backtest_agent.rules.evaluator import Context, dependencies, prepare_context
from strategy_backtest_agent.rules.models import RuleStrategy
from strategy_backtest_agent.validation import engine
from strategy_backtest_agent.validation.engine import fetch_and_validate, run_validation

PRICE = {"type": "price"}
ZERO = {"type": "value", "value": 0}
ALWAYS = strategy(comparison(PRICE, ">", ZERO), comparison(PRICE, "<", ZERO))


def small(closes: list[float], opens: list[float] | None = None) -> list[Candle]:
    return [
        candle.model_copy(update={"timestamp": END - timedelta(hours=24 - 6 * i)})
        for i, candle in enumerate(make_candles(closes, opens))
    ]


@pytest.mark.parametrize("ratio,train_count", [(0.5, 12), (0.7, 16), (0.9, 21)])
def test_partition_coverage_order_and_boundaries(ratio: float, train_count: int) -> None:
    candles = history([10.0] * 27)
    report = run_validation(candles, settings(train_ratio=ratio))
    split = report.split
    assert split.train_candle_count == train_count
    assert split.test_candle_count == 24 - train_count
    assert split.train_end == split.test_start == candles[3 + train_count].timestamp
    train = [c for c in candles if split.train_start <= c.timestamp < split.train_end]
    test = [c for c in candles if split.test_start <= c.timestamp < split.test_end]
    assert train + test == candles[3:]
    assert set(c.timestamp for c in train).isdisjoint(c.timestamp for c in test)
    assert train[-1].timestamp < test[0].timestamp
    assert split.test_end == END


def test_manually_calculated_fees_forced_close_benchmark_equity_and_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Two evaluation candles per segment. Signals at first closes execute at second opens.
    candles = small([8, 5, 6, 12], [10, 10, 5, 8])
    observed: list[list[float]] = []
    original = metrics.max_drawdown

    def capture(equity: Sequence[float]) -> float:
        observed.append(list(equity))
        return original(equity)

    monkeypatch.setattr(metrics, "max_drawdown", capture)
    report = run_validation(
        candles,
        settings(
            strategies=[named("always", ALWAYS)],
            timeframe="6h",
            train_ratio=0.5,
            fee=0.01,
            initial_balance=1000,
        ),
    )
    row = report.results[0]
    for segment, entry_index, quantity, final, benchmark in (
        (row.train, 1, 1000 / 10.1, 1000 / 10.1 * 5 * 0.99, (5 * 0.99 / 10.1 - 1) * 100),
        (row.test, 3, 1000 / 8.08, 1000 / 8.08 * 12 * 0.99, (12 * 0.99 / 5.05 - 1) * 100),
    ):
        result = segment.result
        assert result.initial_balance == 1000
        assert result.final_balance == pytest.approx(final)
        assert result.total_return_percent == pytest.approx((final / 1000 - 1) * 100)
        assert result.buy_and_hold_return_percent == pytest.approx(benchmark)
        assert segment.excess_return_pp == pytest.approx(result.total_return_percent - benchmark)
        assert result.total_trades == 1
        trade = result.trades[0]
        assert trade.entry_time == trade.exit_time == candles[entry_index].timestamp
        assert trade.entry_price == candles[entry_index].open
        assert trade.exit_price == candles[entry_index].close
        assert trade.quantity == pytest.approx(quantity)
        assert trade.pnl == pytest.approx(final - 1000)
    assert observed[0] == pytest.approx(
        [1000, 1000, 1000, 1000 / 1.01, row.train.result.final_balance]
    )
    assert observed[1] == pytest.approx(
        [1000, 1000, 1000, 1000 / 1.01, row.test.result.final_balance]
    )
    assert row.train.result.max_drawdown_percent == pytest.approx(
        (row.train.result.final_balance / 1000 - 1) * 100
    )
    assert row.test.result.max_drawdown_percent == pytest.approx((1 / 1.01 - 1) * 100)
    assert row.train.result.win_rate == 0
    assert row.train.result.profit_factor == 0
    assert row.test.result.win_rate == 100
    assert row.test.result.profit_factor is None
    assert row.return_gap_pp == pytest.approx(
        row.test.result.total_return_percent - row.train.result.total_return_percent
    )


def test_manual_exit_timing_uses_previous_close_and_next_open() -> None:
    rules = strategy(
        comparison(PRICE, "<", {"type": "value", "value": 9}),
        comparison(PRICE, ">", {"type": "value", "value": 11}),
    )
    candles = history([8.0] * 24, warmup=0)
    # Train: buy following index 0 close at index 1 open=7; sell following index 1 close=12
    # at index 2 open=15. Remaining segment closes=10 prevent additional entries.
    candles = [
        c.model_copy(
            update={"open": o, "close": cprice, "high": max(o, cprice), "low": min(o, cprice)}
        )
        for c, o, cprice in zip(candles, [10, 7, 15] + [10] * 21, [8, 12] + [10] * 22, strict=True)
    ]
    result = run_validation(
        candles,
        settings(
            strategies=[named("levels", rules)], train_ratio=0.5, fee=0.01, initial_balance=1000
        ),
    ).results[0]
    trade = result.train.result.trades[0]
    assert trade.entry_time == candles[1].timestamp
    assert trade.exit_time == candles[2].timestamp
    assert trade.entry_price == 7 and trade.exit_price == 15
    assert result.train.result.final_balance == pytest.approx(1000 / 7.07 * 15 * 0.99)
    assert result.test.result.final_balance == 1000
    assert result.test.result.total_trades == 0


def test_final_train_signal_cannot_enter_at_test_open() -> None:
    rules = strategy(
        comparison(PRICE, ">", {"type": "value", "value": 15}), comparison(PRICE, "<", ZERO)
    )
    candles = small([10, 20, 10, 10])
    row = run_validation(
        candles,
        settings(strategies=[named("boundary", rules)], timeframe="6h", train_ratio=0.5, fee=0),
    ).results[0]
    assert row.train.result.total_trades == row.test.result.total_trades == 0
    assert row.train.result.final_balance == row.test.result.final_balance == 10000


def test_open_train_position_liquidates_locally_and_test_starts_flat() -> None:
    candles = history([10.0] * 11 + [20] + [100.0] * 12, warmup=0)
    rules = strategy(
        comparison(PRICE, "<", {"type": "value", "value": 50}), comparison(PRICE, "<", ZERO)
    )
    row = run_validation(
        candles,
        settings(
            strategies=[named("train-only", rules)], train_ratio=0.5, fee=0, initial_balance=1000
        ),
    ).results[0]
    assert row.train.result.trades[0].exit_time == candles[11].timestamp
    assert row.train.result.trades[0].exit_price == 20
    assert row.train.result.final_balance == 2000
    assert row.test.result.initial_balance == row.test.result.final_balance == 1000
    assert row.test.result.total_trades == 0
    assert row.test.result.max_drawdown_percent == 0


@pytest.mark.parametrize("name,required", [("rsi", 3), ("sma", 2), ("ema", 10)])
def test_cache_causal_prefix_and_future_changes_do_not_affect_train(
    name: str, required: int
) -> None:
    rules = strategy(comparison(indicator(name, 2), ">", ZERO), comparison(PRICE, "<", ZERO))
    config = settings(strategies=[named("causal", rules)], train_ratio=0.5)
    candles = history([10.0] * (24 + required), warmup=required)
    altered = [
        c
        if i < required + 12
        else c.model_copy(update={"open": 1000, "high": 1000, "low": 1000, "close": 1000})
        for i, c in enumerate(candles)
    ]
    a, b = run_validation(candles, config), run_validation(altered, config)
    assert a.results[0].train == b.results[0].train
    context = prepare_context(altered, dependencies(rules))
    prefix = prepare_context(candles[: required + 12], dependencies(rules))
    assert context.indicators[(name, 2)][: required + 12] == pytest.approx(
        prefix.indicators[(name, 2)], nan_ok=True
    )
    assert a.results[0].test.result.trades[0].entry_time == candles[required + 13].timestamp


def test_train_execution_receives_no_future_candles_or_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, int]] = []

    def inspect(
        candles: Sequence[Candle],
        config: BacktestConfig,
        strategy: RuleStrategy,
        *,
        evaluation_start: int,
        context: Context,
    ) -> BacktestResult:
        calls.append((len(candles), evaluation_start))
        assert len(context.prices) == len(candles)
        assert all(len(v) == len(candles) for v in context.indicators.values())
        return run_backtest(
            candles, config, strategy, evaluation_start=evaluation_start, context=context
        )

    monkeypatch.setattr(engine, "run_backtest", inspect)
    run_validation(history([10.0] * 27), settings(train_ratio=0.5))
    assert calls == [(15, 3), (27, 15), (15, 3), (27, 15)]


def test_test_indicators_initialize_from_train_history() -> None:
    rules = strategy(
        comparison(indicator("sma", 2), ">", {"type": "value", "value": 15}),
        comparison(PRICE, "<", ZERO),
    )
    candles = history([10.0] * 2 + [10.0] * 11 + [30, 10] + [10.0] * 11, warmup=2)
    config = settings(strategies=[named("sma", rules)], train_ratio=0.5, fee=0)
    row = run_validation(candles, config).results[0]
    assert row.test.warmup_candles == 14
    assert row.test.result.trades[0].entry_time == candles[15].timestamp
    # Without prior Train close=30 the first Test SMA is unavailable and no trade occurs.
    assert run_backtest(candles[14:], config.to_backtest_config(), rules).total_trades == 0


def test_shared_provider_max_warmup_cache_and_independent_strategies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int]] = []
    original_rsi, original_ema = indicators.rsi, indicators.ema

    def rsi(series: pd.Series, period: int) -> pd.Series:
        calls.append(("rsi", period))
        return original_rsi(series, period)

    def ema(series: pd.Series, period: int) -> pd.Series:
        calls.append(("ema", period))
        return original_ema(series, period)

    monkeypatch.setattr(indicators, "rsi", rsi)
    monkeypatch.setattr(indicators, "ema", ema)
    entries = [
        named("a", {"type": "rsi", "period": 2}),
        named("b", {"type": "rsi", "period": 2}),
        named("c", strategy(comparison(indicator("ema", 2)))),
    ]
    provider = Provider(history([10, 9, 8, 12, 13, 5, 4, 8, 9] * 3 + [10.0] * 7, warmup=10))
    report = asyncio.run(
        fetch_and_validate(provider, settings(strategies=entries, train_ratio=0.5))
    )
    assert provider.requests == [("BTCUSDT", "1h", END - timedelta(hours=34), END)]
    assert sorted(calls) == [("ema", 2), ("rsi", 2)]
    assert report.shared_data.required_warmup_candles == 10
    for segment in ("train", "test"):
        a, b = (
            getattr(report.results[0], segment).result,
            getattr(report.results[1], segment).result,
        )
        assert a == b and a is not b
        assert a.initial_balance == 10000
        assert a.final_balance == pytest.approx(10000 + sum(t.pnl for t in a.trades))


@pytest.mark.parametrize("kind", ["empty", "short", "gap", "unfinished", "outside", "coverage"])
def test_insufficient_or_invalid_history(kind: str) -> None:
    candles = history([10.0] * 27)
    source = {
        "empty": [],
        "short": candles[1:],
        "gap": candles[:4] + candles[5:],
        "unfinished": history([10.0] * 27, end=END + timedelta(minutes=1)),
        "outside": history([10.0] * 28, warmup=4),
        "coverage": candles[:-2],
    }[kind]
    with pytest.raises(ValueError):
        run_validation(source, settings())


@pytest.mark.parametrize("ratio", [0.75, 0.9])
def test_insufficient_segment_does_not_change_split(ratio: float) -> None:
    with pytest.raises(ValueError, match="each segment"):
        run_validation(
            small([10.0] * 4),
            settings(strategies=[named("a", ALWAYS)], timeframe="6h", train_ratio=ratio),
        )


def test_zero_trades_null_metrics_repeated_hash_and_fixed_boundaries() -> None:
    config = settings()
    candles = history([10.0] * 27)
    report = run_validation(candles, config)
    assert run_validation(candles, config) == report
    assert run_validation(candles, settings(evaluation_end=None)) == report
    assert report.configuration.evaluation_end == report.shared_data.evaluation_end == END
    assert (
        run_validation(history([10.0] * 26 + [11]), config).shared_data.candles_sha256
        != report.shared_data.candles_sha256
    )
    for row in report.results:
        assert row.return_gap_pp == 0
        for segment in (row.train, row.test):
            assert segment.result.total_trades == 0
            assert segment.result.final_balance == 10000
            assert segment.result.win_rate is segment.result.profit_factor is None


def test_unaligned_fixed_end_utc_and_actual_segment_bounds() -> None:
    end = END + timedelta(minutes=30)
    report = run_validation(history([10.0] * 27)[1:], settings(evaluation_end=end))
    assert report.shared_data.candle_count == 23
    assert report.split.train_start == datetime(2024, 1, 1, 1, tzinfo=UTC)
    assert report.split.test_end == END
    assert report.shared_data.evaluation_end == end


def test_moving_end_resolved_once(monkeypatch: pytest.MonkeyPatch) -> None:
    class Clock(datetime):
        @classmethod
        def now(cls, tz: object = None) -> "Clock":
            return cls(2024, 1, 2, tzinfo=UTC)

    monkeypatch.setattr(engine, "datetime", Clock)
    provider = Provider(history([10.0] * 27))
    report = asyncio.run(fetch_and_validate(provider, settings(evaluation_end=None)))
    assert provider.requests[0][3] == report.configuration.evaluation_end == END
    assert len(provider.requests) == 1


def test_mutated_configuration_rejected_before_fetch() -> None:
    config = settings()
    config.strategies.append(config.strategies[0])
    provider = Provider(history([10.0] * 27))
    with pytest.raises(ValueError, match="unique"):
        asyncio.run(fetch_and_validate(provider, config))
    assert not provider.requests


def test_conflicting_or_naive_end_rejected() -> None:
    for end in (END + timedelta(hours=1), END.replace(tzinfo=None)):
        with pytest.raises(ValueError, match="conflicts|aware"):
            run_validation(history([10.0] * 27), settings(), evaluation_end=end)
