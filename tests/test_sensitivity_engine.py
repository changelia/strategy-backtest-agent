"""Synthetic financial oracles, identical Train boundaries and no Test computations."""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from test_comparison_engine import END, Provider, history
from test_rules import comparison, indicator, strategy
from test_sensitivity_grid import PRICE, ZERO, settings, spec
from test_validation_engine import small

from strategy_backtest_agent import indicators, metrics
from strategy_backtest_agent.backtester import run_backtest
from strategy_backtest_agent.models import BacktestConfig, BacktestResult, Candle
from strategy_backtest_agent.rules.evaluator import Context, dependencies, prepare_context
from strategy_backtest_agent.rules.models import RuleStrategy
from strategy_backtest_agent.sensitivity import engine
from strategy_backtest_agent.sensitivity.engine import fetch_and_analyze, run_sensitivity
from strategy_backtest_agent.sensitivity.grid import expand_grid


def test_manually_calculated_distinct_signals_fees_equity_benchmark_and_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # threshold 9 enters on first Train close=8 at second Train open=7.
    # threshold 5 never enters. Both are force-closed/bounded within Train.
    base = strategy(
        comparison(PRICE, "<", {"type": "value", "value": 9}), comparison(PRICE, "<", ZERO)
    )
    candles = small([8, 5, 100, 100], [10, 7, 100, 100])
    samples: list[list[float]] = []
    original = metrics.max_drawdown

    def capture(equity: Sequence[float]) -> float:
        samples.append(list(equity))
        return original(equity)

    monkeypatch.setattr(metrics, "max_drawdown", capture)
    config = settings(
        base_strategy=base,
        parameters=[spec(values=[9, 5])],
        timeframe="6h",
        train_ratio=0.5,
        initial_balance=1000,
        fee=0.01,
    )
    report = run_sensitivity(candles, config)
    traded, flat = [row.train.result for row in report.results]
    quantity = 1000 / 7.07
    final = quantity * 5 * 0.99
    expected_return = (final / 1000 - 1) * 100
    benchmark = (5 * 0.99 / 10.1 - 1) * 100
    assert traded.total_trades == 1
    assert traded.trades[0].entry_time == traded.trades[0].exit_time == candles[1].timestamp
    assert traded.trades[0].entry_price == 7 and traded.trades[0].exit_price == 5
    assert traded.trades[0].quantity == pytest.approx(quantity)
    assert traded.trades[0].pnl == pytest.approx(final - 1000)
    assert traded.final_balance == pytest.approx(final)
    assert traded.total_return_percent == pytest.approx(expected_return)
    assert traded.max_drawdown_percent == pytest.approx(expected_return)
    assert traded.win_rate == 0 and traded.profit_factor == 0
    assert samples[0] == pytest.approx([1000, 1000, 1000, quantity * 7, final])
    assert samples[1] == [1000] * 5
    assert flat.final_balance == 1000 and flat.total_return_percent == 0
    assert flat.total_trades == 0 and flat.win_rate is flat.profit_factor is None
    for row in report.results:
        assert row.train.result.initial_balance == 1000
        assert row.train.result.buy_and_hold_return_percent == pytest.approx(benchmark)
        assert row.train.excess_return_pp == pytest.approx(
            row.train.result.total_return_percent - benchmark
        )
        assert row.train.start == report.split.train_start == candles[0].timestamp
        assert row.train.end == report.split.train_end == candles[2].timestamp
        assert row.train.candle_count == 2
        assert row.observation == "insufficient_trades"
    assert report.summary.minimum_return_percent == pytest.approx(expected_return)
    assert report.summary.maximum_return_percent == 0
    assert report.summary.median_return_percent == pytest.approx(expected_return / 2)
    assert report.summary.return_range_pp == pytest.approx(-expected_return)
    assert report.summary.positive_return_percent == 0
    assert report.summary.outperforming_buy_and_hold_percent == 100
    assert report.summary.insufficient_trade_variant_ids == ["variant-001", "variant-002"]
    assert report.ordered_series is not None
    assert [point.value for point in report.ordered_series] == [9, 5]


def test_manual_regular_exit_uses_next_train_open() -> None:
    base = strategy(
        comparison(PRICE, "<", {"type": "value", "value": 9}),
        comparison(PRICE, ">", {"type": "value", "value": 11}),
    )
    candles = history([8, 12] + [10.0] * 22, warmup=0)
    candles[1] = candles[1].model_copy(update={"open": 7, "low": 7})
    candles[2] = candles[2].model_copy(update={"open": 15, "high": 15})
    report = run_sensitivity(
        candles,
        settings(
            base_strategy=base,
            parameters=[spec(values=[9, 7])],
            train_ratio=0.5,
            initial_balance=1000,
            fee=0.01,
        ),
    )
    result = report.results[0].train.result
    assert result.trades[0].entry_time == candles[1].timestamp
    assert result.trades[0].exit_time == candles[2].timestamp
    assert result.final_balance == pytest.approx(1000 / 7.07 * 15 * 0.99)
    assert report.results[1].train.result.total_trades == 0


def test_final_train_signal_cannot_execute_in_test() -> None:
    base = strategy(
        comparison(PRICE, ">", {"type": "value", "value": 15}), comparison(PRICE, "<", ZERO)
    )
    report = run_sensitivity(
        small([10, 20, 100, 100]),
        settings(
            base_strategy=base,
            parameters=[spec(values=[15, 25])],
            timeframe="6h",
            train_ratio=0.5,
            fee=0,
        ),
    )
    assert all(row.train.result.total_trades == 0 for row in report.results)
    assert all(row.train.result.final_balance == 10000 for row in report.results)


@pytest.mark.parametrize("name,required", [("rsi", 5), ("sma", 4), ("ema", 20)])
def test_fetch_once_maximum_warmup_unique_cache_and_portfolio_isolation(
    name: str,
    required: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = {"rsi": indicators.rsi, "sma": indicators.sma, "ema": indicators.ema}[name]
    calls: list[tuple[int, int]] = []

    def capture(series: pd.Series, period: int) -> pd.Series:
        calls.append((period, len(series)))
        return original(series, period)

    monkeypatch.setattr(indicators, name, capture)
    base = strategy(comparison(indicator(name, 2), ">", ZERO), comparison(PRICE, "<", ZERO))
    config = settings(
        base_strategy=base,
        parameters=[spec("entry.left.period", values=[2, 3, 4])],
        train_ratio=0.5,
        initial_balance=1000,
        fee=0.01,
    )
    closes = ([10.0, 9.0, 12.0, 8.0, 13.0] * 10)[: 24 + required]
    candles = history(closes, warmup=required)
    provider = Provider(candles)
    report = asyncio.run(fetch_and_analyze(provider, config, data_source="fixture"))
    assert provider.requests == [("BTCUSDT", "1h", END - timedelta(hours=24 + required), END)]
    assert calls == [(period, required + 12) for period in [2, 3, 4]]
    assert (
        report.shared_data.required_warmup_candles == report.shared_data.warmup_candles == required
    )
    assert [(i.name, i.period) for i in report.shared_data.indicators] == [
        (name, p) for p in [2, 3, 4]
    ]
    # Independent uncached runs must exactly match the shared-cache coordinator.
    for variant, row in zip(report.variants, report.results, strict=True):
        assert row.train.result == run_backtest(
            candles[: required + 12],
            config.to_backtest_config(),
            variant.strategy,
            evaluation_start=required,
        )
        assert row.train.result.final_balance == pytest.approx(
            1000 + sum(t.pnl for t in row.train.result.trades)
        )
        assert (
            row.train.start == report.split.train_start and row.train.end == report.split.train_end
        )


@pytest.mark.parametrize("name,required", [("rsi", 4), ("sma", 3), ("ema", 15)])
def test_test_prices_never_change_variants_metrics_statistics_or_observations(
    name: str, required: int
) -> None:
    base = strategy(comparison(indicator(name, 2), ">", ZERO), comparison(PRICE, "<", ZERO))
    config = settings(
        base_strategy=base, parameters=[spec("entry.left.period", values=[2, 3])], train_ratio=0.5
    )
    candles = history(([10.0, 12.0, 8.0] * 20)[: 24 + required], warmup=required)
    altered = [
        c
        if i < required + 12
        else c.model_copy(update={"open": 1000, "close": 1000, "high": 1000, "low": 1000})
        for i, c in enumerate(candles)
    ]
    first, second = run_sensitivity(candles, config), run_sensitivity(altered, config)
    assert first.variants == second.variants and first.parameters == second.parameters
    assert first.results == second.results and first.summary == second.summary
    assert first.split == second.split and first.neighbors == second.neighbors
    assert first.ordered_series == second.ordered_series
    assert first.shared_data.candles_sha256 != second.shared_data.candles_sha256


def test_backtester_never_receives_test_candles_or_context(monkeypatch: pytest.MonkeyPatch) -> None:
    config = settings(train_ratio=0.5)
    candles = history([10.0] * 27)
    calls: list[tuple[int, int]] = []

    def inspect(
        source: Sequence[Candle],
        portfolio: BacktestConfig,
        rules: RuleStrategy,
        *,
        evaluation_start: int,
        context: Context,
    ) -> BacktestResult:
        calls.append((len(source), evaluation_start))
        assert source == candles[:15]
        assert context.prices == [c.close for c in candles[:15]]
        assert all(len(values) == 15 for values in context.indicators.values())
        return run_backtest(
            source, portfolio, rules, evaluation_start=evaluation_start, context=context
        )

    monkeypatch.setattr(engine, "run_backtest", inspect)
    report = run_sensitivity(candles, config)
    assert calls == [(15, 3)] * 3
    assert all("test" not in row.model_dump() for row in report.results)
    assert "ranking" not in report.model_dump() and "winner" not in report.model_dump()


def test_causal_cache_every_prefix_and_period() -> None:
    config = settings(
        parameters=[spec("entry.left.period", values=[2, 3, 4], coupled_paths=["exit.left.period"])]
    )
    _, variants = expand_grid(config.base_strategy, config.parameters)
    train = history(([10.0, 12.0, 8.0, 14.0, 9.0] * 6)[:29], warmup=5)[:21]
    keys = set().union(*(dependencies(v.strategy) for v in variants))
    cache = prepare_context(train, keys)
    for index in range(1, len(train) + 1):
        prefix = prepare_context(train[:index], keys)
        for key in keys:
            assert cache.indicators[key][:index] == pytest.approx(
                prefix.indicators[key], nan_ok=True
            )


def test_fixed_end_reproducibility_and_inferred_end() -> None:
    config = settings()
    candles = history([10.0] * 27)
    first = run_sensitivity(candles, config)
    assert run_sensitivity(candles, config) == first
    assert run_sensitivity(candles, settings(evaluation_end=None)) == first
    assert first.configuration.evaluation_end == first.shared_data.evaluation_end == END


def test_moving_end_resolved_once(monkeypatch: pytest.MonkeyPatch) -> None:
    class Clock(datetime):
        @classmethod
        def now(cls, tz: object = None) -> "Clock":
            return cls(2024, 1, 2, tzinfo=UTC)

    monkeypatch.setattr(engine, "datetime", Clock)
    provider = Provider(history([10.0] * 27))
    report = asyncio.run(fetch_and_analyze(provider, settings(evaluation_end=None)))
    assert len(provider.requests) == 1
    assert provider.requests[0][3] == report.configuration.evaluation_end == END


def test_invalid_mutated_grid_rejected_before_provider_call() -> None:
    config = settings()
    config.parameters.append(config.parameters[0])
    provider = Provider(history([10.0] * 27))
    with pytest.raises(ValueError, match="unique"):
        asyncio.run(fetch_and_analyze(provider, config))
    assert not provider.requests


@pytest.mark.parametrize("kind", ["empty", "warmup", "gap", "unfinished", "outside", "coverage"])
def test_invalid_history(kind: str) -> None:
    candles = history([10.0] * 27)
    source = {
        "empty": [],
        "warmup": candles[1:],
        "gap": candles[:4] + candles[5:],
        "unfinished": history([10.0] * 27, end=END + timedelta(minutes=1)),
        "outside": history([10.0] * 28, warmup=4),
        "coverage": candles[:-2],
    }[kind]
    with pytest.raises(ValueError):
        run_sensitivity(source, settings())


def test_insufficient_train_or_reserved_test_candles() -> None:
    base = strategy(comparison(PRICE, "<", {"type": "value", "value": 9}))
    with pytest.raises(ValueError, match="each segment"):
        run_sensitivity(
            small([10.0] * 4),
            settings(base_strategy=base, parameters=[spec()], timeframe="6h", train_ratio=0.9),
        )


def test_conflicting_and_naive_boundaries() -> None:
    for end in (END + timedelta(hours=1), END.replace(tzinfo=None)):
        with pytest.raises(ValueError, match="conflicts|aware"):
            run_sensitivity(history([10.0] * 27), settings(), evaluation_end=end)


def test_unaligned_window_uses_completed_candle_partition() -> None:
    config = settings(evaluation_end=END + timedelta(minutes=30))
    report = run_sensitivity(history([10.0] * 27)[1:], config)
    assert report.shared_data.candle_count == 23
    assert report.split.train_candle_count == 16 and report.split.test_candle_count == 7
    assert report.split.train_start == datetime(2024, 1, 1, 1, tzinfo=UTC)
    assert report.split.test_end == END


def test_test_price_changes_leave_two_dimensional_matrix_unchanged() -> None:
    config = settings(parameters=[spec(), spec("exit.right.value", values=[65, 70, 75])])
    candles = history(([10.0, 12.0, 8.0] * 9), warmup=3)
    cut = 3 + 16
    altered = candles[:cut] + [
        c.model_copy(
            update={
                "open": 1000,
                "close": 1000,
                "high": 1000,
                "low": 1000,
            }
        )
        for c in candles[cut:]
    ]
    a, b = run_sensitivity(candles, config), run_sensitivity(altered, config)
    assert a.matrix is not None and a.matrix == b.matrix
    assert a.results == b.results and a.summary == b.summary and a.neighbors == b.neighbors
