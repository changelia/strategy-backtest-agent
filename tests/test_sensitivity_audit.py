"""Final audit: non-flat recursive initialization and complete held-out data isolation."""

import asyncio
from collections.abc import Sequence
from datetime import datetime

import pandas as pd
import pytest
from test_comparison_engine import history
from test_rules import comparison, indicator, strategy
from test_sensitivity_grid import PRICE, ZERO, settings, spec

from strategy_backtest_agent import backtester, indicators
from strategy_backtest_agent.backtester import run_backtest
from strategy_backtest_agent.metrics import summarize
from strategy_backtest_agent.models import BacktestConfig, BacktestResult, Candle, Trade
from strategy_backtest_agent.rules.evaluator import (
    Context,
    evaluate_rule,
    indicator_warmup,
    prepare_context,
)
from strategy_backtest_agent.rules.indicator_specs import indicator_key
from strategy_backtest_agent.rules.models import Rule, RuleStrategy
from strategy_backtest_agent.sensitivity import engine
from strategy_backtest_agent.sensitivity.cache import prepare_train_context
from strategy_backtest_agent.sensitivity.engine import fetch_and_analyze, run_sensitivity


class Archive:
    """One unchanged market archive; requests return only their requested UTC range."""

    def __init__(self, candles: list[Candle]) -> None:
        self.candles = candles
        self.requests: list[tuple[datetime, datetime]] = []

    async def fetch_candles(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Candle]:
        self.requests.append((start, end))
        return [c for c in self.candles if start <= c.timestamp < end]


def recursive_archive(name: str) -> list[Candle]:
    evaluation = [100.0, 110.0, 90.0, 120.0, 80.0, 130.0, 70.0, 140.0, 60.0, 150.0, 50.0, 160.0]
    if name == "rsi":
        prior = [120.0, 80.0, 110.0, 100.0, 103.0, 97.0, 104.0]
    else:
        prior = [1e6, 900000.0, 1100000.0, 800000.0, 1200000.0] * 4 + [
            100.0,
            101.0,
            99.0,
            102.0,
            98.0,
            103.0,
            97.0,
            104.0,
            96.0,
            105.0,
        ]
    return history(prior + evaluation + [500.0] * 12, warmup=len(prior))


@pytest.mark.parametrize("name,threshold", [("rsi", 36.4), ("ema", 104.0)])
def test_recursive_original_variant_stays_identical_when_longer_period_is_added(
    name: str,
    threshold: float,
) -> None:
    candles = recursive_archive(name)
    base = strategy(
        comparison(indicator(name, 2), "<", {"type": "value", "value": threshold}),
        comparison(PRICE, "<", ZERO),
    )
    reports = []
    for values in ([2], [2, 6]):
        provider = Archive(candles)
        config = settings(
            base_strategy=base,
            parameters=[spec("entry.left.period", values=values)],
            train_ratio=0.5,
            fee=0.01,
            initial_balance=1000,
        )
        reports.append(asyncio.run(fetch_and_analyze(provider, config)))
        assert len(provider.requests) == 1
    alone, expanded = reports
    assert alone.split == expanded.split
    assert alone.variants[0].strategy == expanded.variants[0].strategy
    assert alone.results[0].train.result == expanded.results[0].train.result
    # Own finite initialization: first Train signal buys at second open=110,
    # force-closes at final Train close=160. No Test price=500 is used.
    expected_final = 1000 / (110 * 1.01) * 160 * 0.99
    result = alone.results[0].train.result
    assert result.final_balance == pytest.approx(expected_final)
    assert result.total_return_percent == pytest.approx(42.574257425742545)
    prior = len(candles) - 24
    assert result.trades[0].entry_time == candles[prior + 1].timestamp
    assert result.trades[0].exit_time == candles[prior + 11].timestamp


@pytest.mark.parametrize("name,required", [("rsi", 3), ("sma", 2), ("ema", 10)])
def test_every_test_ohlcv_change_leaves_all_train_computations_identical(
    name: str,
    required: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    low, high = ([35, 45], [65, 75]) if name == "rsi" else ([100, 110], [120, 130])
    base = strategy(
        {
            "type": "and",
            "conditions": [comparison(indicator(name, 2)), comparison(PRICE, ">", ZERO)],
        },
        {
            "type": "or",
            "conditions": [
                comparison(indicator(name, 2), ">", {"type": "value", "value": high[0]}),
                comparison(PRICE, "<", ZERO),
            ],
        },
    )
    config = settings(
        base_strategy=base,
        train_ratio=0.5,
        parameters=[
            spec("entry.conditions.0.right.value", values=low),
            spec("exit.conditions.0.right.value", values=high),
        ],
    )
    evaluation = [100.0, 110.0, 90.0, 120.0, 80.0, 130.0, 70.0, 140.0, 60.0, 150.0, 50.0, 160.0] * 2
    candles = history(([103.0, 97.0, 104.0, 96.0] * 3)[:required] + evaluation, warmup=required)
    cut = required + 12
    changed = candles[:cut] + [
        Candle(
            timestamp=c.timestamp,
            open=10000 + i * 37,
            close=0.1 + i * 0.02,
            high=20000 + i * 74,
            low=0.05 + i * 0.01,
            volume=1e6 + i,
        )
        for i, c in enumerate(candles[cut:])
    ]
    assert changed[:cut] == candles[:cut]
    assert all(a != b for a, b in zip(candles[cut:], changed[cut:], strict=True))
    executions: list[int] = []
    indicator_calls: list[tuple[str, int]] = []
    signal_indices: list[int] = []
    equity_samples: list[list[float]] = []
    original_backtest, original_signal, original_summary = (
        run_backtest,
        evaluate_rule,
        summarize,
    )
    original_indicator = {"rsi": indicators.rsi, "sma": indicators.sma, "ema": indicators.ema}[name]

    def checked_indicator(series: pd.Series, period: int) -> pd.Series:
        assert series.tolist() == [c.close for c in candles[:cut]][-len(series) :]
        indicator_calls.append((name, period))
        return original_indicator(series, period)

    def checked_backtest(
        source: Sequence[Candle],
        portfolio: BacktestConfig,
        rules: RuleStrategy,
        *,
        evaluation_start: int,
        context: Context,
    ) -> BacktestResult:
        assert source == candles[:cut]
        assert evaluation_start == required
        assert context.prices == [c.close for c in candles[:cut]]
        executions.append(len(source))
        return original_backtest(
            source, portfolio, rules, evaluation_start=evaluation_start, context=context
        )

    def checked_signal(rule: Rule, index: int, context: Context) -> bool:
        assert required <= index < cut - 1
        signal_indices.append(index)
        return original_signal(rule, index, context)

    def checked_summary(
        initial: float,
        final: float,
        trades: list[Trade],
        equity: Sequence[float],
        benchmark: float | None,
    ) -> BacktestResult:
        equity_samples.append(list(equity))
        assert all(
            candles[required].timestamp < t.entry_time < candles[cut].timestamp for t in trades
        )
        assert all(t.exit_time < candles[cut].timestamp for t in trades)
        return original_summary(initial, final, trades, equity, benchmark)

    monkeypatch.setattr(indicators, name, checked_indicator)
    monkeypatch.setattr(engine, "run_backtest", checked_backtest)
    monkeypatch.setattr(backtester, "evaluate_rule", checked_signal)
    monkeypatch.setattr(backtester, "summarize", checked_summary)
    first = run_sensitivity(candles, config)
    first_signals = list(signal_indices)
    signal_indices.clear()
    second = run_sensitivity(changed, config)
    assert first.results == second.results
    assert first.summary == second.summary and first.neighbors == second.neighbors
    assert first.variants == second.variants and first.parameters == second.parameters
    assert first.matrix == second.matrix and first.ordered_series == second.ordered_series
    assert first.split == second.split and first.configuration == second.configuration
    assert first.shared_data.model_dump(
        exclude={"candles_sha256"}
    ) == second.shared_data.model_dump(exclude={"candles_sha256"})
    assert first.shared_data.candles_sha256 != second.shared_data.candles_sha256
    assert equity_samples[:4] == equity_samples[4:]
    assert first_signals == signal_indices
    assert executions == [cut] * 8  # Four variants per run, all on Train only.
    assert indicator_calls == [(name, 2)] * 2  # Unique cached key, once per run.
    assert any(row.train.result.total_trades for row in first.results)
    assert all("test" not in row.model_dump() for row in first.results)


@pytest.mark.parametrize("name", ["rsi", "sma", "ema"])
def test_anchored_cache_matches_independent_initialization_and_every_train_prefix(
    name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candles = recursive_archive(name)
    boundary = len(candles) - 24
    train = candles[: boundary + 12]
    keys = {(name, 2), (name, 6)}
    original = {"rsi": indicators.rsi, "sma": indicators.sma, "ema": indicators.ema}[name]
    calls: list[tuple[int, int]] = []

    def capture(series: pd.Series, period: int) -> pd.Series:
        calls.append((period, len(series)))
        return original(series, period)

    monkeypatch.setattr(indicators, name, capture)
    cache, initializations = prepare_train_context(train, boundary, keys)
    assert calls == [(p, indicator_warmup(name, p) + 12) for p in (2, 6)]
    assert cache.prices == [c.close for c in train]
    for profile in initializations:
        key = indicator_key(profile.indicator)
        required = indicator_warmup(*key)
        assert profile.prior_candle_count == required
        assert profile.history_start == candles[boundary - required].timestamp
        start = boundary - required
        assert len(cache.indicators[key]) == len(train)
        assert all(pd.isna(value) for value in cache.indicators[key][:start])
        independent = prepare_context(train[start:], {key})
        assert cache.indicators[key][start:] == pytest.approx(
            independent.indicators[key], nan_ok=True
        )
        for index in range(boundary, len(train)):
            prefix, _ = prepare_train_context(train[: index + 1], boundary, keys)
            assert prefix.indicators[key] == pytest.approx(
                cache.indicators[key][: index + 1], nan_ok=True
            )


def test_mixed_recursive_cache_keys_do_not_collide_or_move_each_others_seeds() -> None:
    candles = recursive_archive("ema")
    boundary = len(candles) - 24
    train = candles[: boundary + 12]
    keys = {("rsi", 2), ("ema", 2)}
    original, anchors = prepare_train_context(train, boundary, keys)
    expanded, expanded_anchors = prepare_train_context(
        train, boundary, keys | {("rsi", 6), ("ema", 6)}
    )
    for key in keys:
        assert original.indicators[key] == pytest.approx(expanded.indicators[key], nan_ok=True)
        assert next(p for p in anchors if indicator_key(p.indicator) == key) == next(
            p for p in expanded_anchors if indicator_key(p.indicator) == key
        )
    assert original.indicators[("rsi", 2)][boundary:] != original.indicators[("ema", 2)][boundary:]


@pytest.mark.parametrize("name", ["rsi", "ema"])
def test_recorded_initialization_and_finite_history_limitation(name: str) -> None:
    candles = recursive_archive(name)
    boundary = len(candles) - 24
    train = candles[: boundary + 12]
    context, profiles = prepare_train_context(train, boundary, {(name, 2)})
    required = indicator_warmup(name, 2)
    assert len(profiles) == 1
    # Older unused data cannot alter the anchored seed, but revising a candle
    # inside the indicator's recorded finite initialization window can.
    older = list(train)
    older[0] = older[0].model_copy(update={"open": 2e6, "close": 2e6, "high": 2e6, "low": 2e6})
    same, _ = prepare_train_context(older, boundary, {(name, 2)})
    assert context.indicators[(name, 2)] == pytest.approx(same.indicators[(name, 2)], nan_ok=True)
    recent = list(train)
    index = boundary - required
    recent[index] = recent[index].model_copy(
        update={"open": 2e6, "close": 2e6, "high": 2e6, "low": 2e6}
    )
    different, _ = prepare_train_context(recent, boundary, {(name, 2)})
    assert context.indicators[(name, 2)][boundary] != different.indicators[(name, 2)][boundary]


@pytest.mark.parametrize("boundary", [-1, 0, 3, 4])
def test_anchored_cache_rejects_missing_history_or_invalid_evaluation_start(boundary: int) -> None:
    candles = recursive_archive("rsi")[:4]
    with pytest.raises(ValueError, match="prior history|evaluation_start"):
        prepare_train_context(candles, boundary, {("ema", 2)})


@pytest.mark.parametrize("name,threshold", [("rsi", 36.4), ("ema", 104.0)])
def test_grid_stability_with_unaligned_fixed_end(name: str, threshold: float) -> None:
    from datetime import timedelta

    from test_comparison_engine import END

    candles = recursive_archive(name)
    base = strategy(
        comparison(indicator(name, 2), "<", {"type": "value", "value": threshold}),
        comparison(PRICE, "<", ZERO),
    )
    reports = [
        asyncio.run(
            fetch_and_analyze(
                Archive(candles),
                settings(
                    base_strategy=base,
                    parameters=[spec("entry.left.period", values=values)],
                    evaluation_end=END + timedelta(minutes=30),
                ),
            )
        )
        for values in ([2], [2, 6])
    ]
    assert reports[0].split == reports[1].split
    assert reports[0].split.train_start == END - timedelta(hours=23)
    assert reports[0].results[0].train.result == reports[1].results[0].train.result
    short_anchors = [
        next(
            p
            for p in report.shared_data.indicator_initializations
            if indicator_key(p.indicator)[1] == 2
        )
        for report in reports
    ]
    assert short_anchors[0] == short_anchors[1]
    assert short_anchors[0].history_start == reports[0].split.train_start - timedelta(
        hours=indicator_warmup(name, 2)
    )


@pytest.mark.parametrize("name,threshold", [("rsi", 36.4), ("ema", 104.0)])
def test_all_twelve_json_sections_repeat_with_finite_anchored_metadata(
    name: str, threshold: float
) -> None:
    import json

    from strategy_backtest_agent.sensitivity.models import SensitivityReport

    candles = recursive_archive(name)
    base = strategy(
        comparison(indicator(name, 2), "<", {"type": "value", "value": threshold}),
        comparison(PRICE, "<", ZERO),
    )
    config = settings(base_strategy=base, parameters=[spec("entry.left.period", values=[2, 6])])
    first = asyncio.run(fetch_and_analyze(Archive(candles), config))
    second = asyncio.run(fetch_and_analyze(Archive(candles), config))
    payload = json.loads(first.model_dump_json())
    repeated = json.loads(second.model_dump_json())
    assert len(payload) == 12
    assert all(payload[section] == repeated[section] for section in payload)
    encoded = json.dumps(payload, allow_nan=False)
    assert SensitivityReport.model_validate_json(encoded) == first
    assert "indicator_initializations" in payload["shared_data"]
