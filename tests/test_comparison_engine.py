"""One dataset/cache, independent accounting, stable rankings and recorded boundaries."""

import asyncio
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from conftest import make_candles
from test_rules import comparison, indicator, strategy

from strategy_backtest_agent import indicators
from strategy_backtest_agent.backtester import run_backtest
from strategy_backtest_agent.comparison.engine import (
    fetch_and_compare,
    rank_results,
    run_comparison,
)
from strategy_backtest_agent.comparison.models import (
    ComparisonConfig,
    NamedStrategy,
    StrategyResult,
)
from strategy_backtest_agent.models import BacktestResult, Candle
from strategy_backtest_agent.rules.evaluator import Context

END = datetime(2024, 1, 2, tzinfo=UTC)


def config(*, entries: list[NamedStrategy] | None = None, **updates: object) -> ComparisonConfig:
    if entries is None:
        entries = [
            NamedStrategy.model_validate(
                {
                    "id": f"rsi-{threshold}",
                    "name": f"RSI {threshold}/70",
                    "strategy": {"type": "rsi", "period": 2, "entry_below": threshold},
                }
            )
            for threshold in (25, 30)
        ]
    return ComparisonConfig.model_validate(
        {
            "symbol": "BTCUSDT",
            "period_days": 1,
            "evaluation_end": END,
            "strategies": entries,
            **updates,
        }
    )


def history(closes: list[float], warmup: int = 3, end: datetime = END) -> list[Candle]:
    assert len(closes) == 24 + warmup
    start = end - timedelta(hours=len(closes))
    return [
        c.model_copy(update={"timestamp": start + timedelta(hours=i)})
        for i, c in enumerate(make_candles(closes))
    ]


class Provider:
    def __init__(self, candles: list[Candle]) -> None:
        self.candles = candles
        self.requests: list[tuple[str, str, datetime, datetime]] = []

    async def fetch_candles(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Candle]:
        self.requests.append((symbol, timeframe, start, end))
        return self.candles


def named(id: str, rule: object) -> NamedStrategy:
    return NamedStrategy.model_validate({"id": id, "name": id, "strategy": rule})


def test_shared_fetch_max_warmup_and_identical_benchmark() -> None:
    entries = [
        named("rsi", {"type": "rsi"}),
        named("ema", strategy(comparison(indicator("ema", 200)))),
        named("sma", strategy(comparison(indicator("sma", 50)))),
    ]
    candles = history([10.0] * 1024, 1000)
    provider = Provider(candles)
    result = asyncio.run(
        fetch_and_compare(provider, config(entries=entries), data_source="fixture")
    )
    assert provider.requests == [("BTCUSDT", "1h", END - timedelta(hours=1024), END)]
    assert result.shared_data.warmup_candles == 1000
    assert result.shared_data.candle_count == 24
    assert result.shared_data.evaluation_start == END - timedelta(days=1)
    assert result.configuration.evaluation_end == END
    assert len({r.result.buy_and_hold_return_percent for r in result.results}) == 1
    assert result.shared_data.source == "fixture"


def test_shared_cache_periods_and_no_leakage(monkeypatch: pytest.MonkeyPatch) -> None:
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
    shared = strategy(
        {
            "type": "and",
            "conditions": [
                comparison(indicator("rsi", 2)),
                comparison({"type": "price"}, ">", indicator("ema", 2)),
            ],
        }
    )
    separate = strategy(comparison(indicator("ema", 3), ">=", indicator("ema", 2)))
    settings = config(entries=[named("a", shared), named("b", shared), named("c", separate)])
    candles = history([10.0] * 39, 15)
    first = run_comparison(candles, settings)
    assert sorted(calls) == [("ema", 2), ("ema", 3), ("rsi", 2)]
    calls.clear()
    second = run_comparison(candles, settings)
    assert sorted(calls) == [("ema", 2), ("ema", 3), ("rsi", 2)]
    assert first == second


def test_independent_portfolios_fees_reconciliation_and_baseline() -> None:
    candles = history([10, 9, 8, 12, 13, 5, 4, 8, 9] * 3)
    settings = config(initial_balance=1000, fee=0.01)
    comparison_result = run_comparison(candles, settings)
    assert comparison_result.buy_and_hold_return_percent is not None
    for item, row in zip(settings.strategies, comparison_result.results, strict=True):
        assert row.result == run_backtest(
            candles, settings.to_backtest_config(), item.to_rules(), evaluation_start=3
        )
        result = row.result
        assert result.total_trades > 1
        assert result.initial_balance == 1000
        assert result.final_balance == pytest.approx(1000 + sum(t.pnl for t in result.trades))
        available = 1000.0
        for trade in result.trades:
            assert trade.quantity == pytest.approx(available / (trade.entry_price * 1.01))
            available = trade.quantity * trade.exit_price * 0.99
            assert trade.entry_time >= candles[4].timestamp
        assert row.excess_return_pp == pytest.approx(
            result.total_return_percent - comparison_result.buy_and_hold_return_percent
        )


def test_warmup_no_trades_equity_or_benchmark_and_forced_close() -> None:
    always = strategy(
        comparison({"type": "price"}, ">", {"type": "value", "value": 0}),
        comparison({"type": "price"}, "<", {"type": "value", "value": 0}),
    )
    settings = config(
        entries=[named("always", always), named("rsi", {"type": "rsi", "period": 2})], fee=0
    )
    candles = history([1000, 500, 100] + [10.0] * 23 + [20])
    result = run_comparison(candles, settings)
    row = result.results[0].result
    assert row.trades[0].entry_time == candles[4].timestamp
    assert row.trades[0].exit_time == candles[-1].timestamp
    assert row.trades[0].quantity == 1000
    assert row.final_balance == 20000
    assert row.max_drawdown_percent == 0
    assert result.buy_and_hold_return_percent == 100
    assert result.shared_data.first_candle_open == candles[3].timestamp


def test_comparison_legacy_rsi_uses_shared_prior_initialization() -> None:
    candles = history([10, 9, 8] + [7.0] * 24)
    settings = config(fee=0)
    result = run_comparison(candles, settings)
    assert result.results[0].result.trades[0].entry_time == candles[4].timestamp
    assert (
        run_backtest(
            candles[3:], settings.to_backtest_config(), settings.strategies[0].to_rules()
        ).total_trades
        == 0
    )


def test_no_trades_and_null_metrics() -> None:
    result = run_comparison(history([10.0] * 27), config())
    for row in result.results:
        assert row.result.total_trades == 0
        assert row.result.final_balance == 10000
        assert row.result.max_drawdown_percent == 0
        assert row.result.win_rate is None
        assert row.result.profit_factor is None
    assert result.ranking == ["rsi-25", "rsi-30"]


def test_no_lookahead_and_drawdown() -> None:
    settings = config(fee=0)
    first = history([10, 9, 8, 7, 3.5, 1, 7] + [7.0] * 20)
    changed = history([10, 9, 8, 7, 3.5, 1, 700] + [700.0] * 20)
    a = run_comparison(first, settings).results[0].result
    b = run_comparison(changed, settings).results[0].result
    assert a.trades[0].entry_time == b.trades[0].entry_time == first[4].timestamp
    assert a.trades[0].quantity == b.trades[0].quantity
    assert a.max_drawdown_percent == pytest.approx((1 / 3.5 - 1) * 100)


def test_final_signal_does_not_execute() -> None:
    rules = strategy(comparison({"type": "price"}, ">", {"type": "value", "value": 15}))
    settings = config(entries=[named("a", rules), named("b", rules)])
    result = run_comparison(history([10.0] * 23 + [20], warmup=0), settings)
    assert all(row.result.total_trades == 0 for row in result.results)


@pytest.mark.parametrize("kind", ["empty", "short", "gap", "unfinished", "outside"])
def test_invalid_shared_history(kind: str) -> None:
    candles = history([10.0] * 27)
    source = {
        "empty": [],
        "short": candles[1:],
        "gap": candles[:4] + candles[5:],
        "unfinished": history([10.0] * 27, end=END + timedelta(minutes=1)),
        "outside": history([10.0] * 28, warmup=4),
    }[kind]
    with pytest.raises(ValueError):
        run_comparison(source, config())


def test_hash_and_fixed_boundaries() -> None:
    candles = history([10.0] * 27)
    first = run_comparison(candles, config())
    assert run_comparison(candles, config()) == first
    changed = run_comparison(history([10.0] * 26 + [11]), config())
    assert changed.shared_data.candles_sha256 != first.shared_data.candles_sha256
    assert first.shared_data.evaluation_end == END
    assert run_comparison(candles, config(evaluation_end=None)) == first


@pytest.mark.parametrize(
    "criterion", ["total_return", "excess_return", "max_drawdown", "profit_factor"]
)
def test_rankings_nulls_and_ties(criterion: str) -> None:
    from typing import cast

    from strategy_backtest_agent.comparison.models import RankingCriterion

    rule = strategy(comparison({"type": "price"}))

    def row(id: str, metric: float | None) -> StrategyResult:
        result = BacktestResult(
            initial_balance=10000,
            final_balance=10000,
            total_return_percent=metric or 0,
            buy_and_hold_return_percent=0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=None,
            max_drawdown_percent=metric or 0,
            profit_factor=metric,
            trades=[],
        )
        return StrategyResult(id=id, name=id, strategy=rule, result=result, excess_return_pp=metric)

    low, high = (1, 2) if criterion == "profit_factor" else (-10, -5)
    rows = [row("z", low), row("c", high), row("b", high)]
    assert rank_results(rows, cast(RankingCriterion, criterion)) == ["b", "c", "z"]
    if criterion in ("profit_factor", "excess_return"):
        rows.append(row("a", None))
        assert rank_results(rows, cast(RankingCriterion, criterion)) == ["b", "c", "z", "a"]


def test_stale_prepared_context_rejected() -> None:
    settings = config()
    candles = history([10.0] * 27)
    with pytest.raises(ValueError, match="context"):
        run_backtest(
            candles,
            settings.to_backtest_config(),
            settings.strategies[0].to_rules(),
            context=Context([1.0] * 27, {}),
        )
    with pytest.raises(ValueError, match="context"):
        run_backtest(
            candles,
            settings.to_backtest_config(),
            settings.strategies[0].to_rules(),
            context=Context([10.0] * 27, {}),
        )
