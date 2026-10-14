"""Independent financial oracles and signal/cache isolation for the final execution audit."""

import asyncio
import json
import math
from collections.abc import Sequence
from decimal import Decimal

import pytest
from conftest import make_candles
from test_comparison_engine import Provider, history, named
from test_cost_scenarios import settings as scenario_config
from test_execution import EXECUTION, PRICE, RULE
from test_rules import comparison, indicator, strategy
from test_validation_engine import small
from test_validation_models import settings as validation_config

from strategy_backtest_agent import backtester, metrics
from strategy_backtest_agent.backtester import run_backtest
from strategy_backtest_agent.costs.engine import fetch_and_run_costs
from strategy_backtest_agent.models import BacktestConfig, BacktestResult, Candle, ExecutionConfig
from strategy_backtest_agent.rules.evaluator import Context, evaluate_rule
from strategy_backtest_agent.rules.models import RuleStrategy
from strategy_backtest_agent.strategy import rsi_signals
from strategy_backtest_agent.validation.engine import run_validation


@pytest.mark.parametrize(
    "fee,spread,slippage",
    [("0", "0", "0"), ("0.001", "0", "0"), ("0.001", "20", "10"), ("0.02", "50", "30")],
)
def test_flat_price_round_trip_independent_decimal_accounting(
    fee: str, spread: str, slippage: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = Decimal(fee)
    a = (Decimal(spread) / 2 + Decimal(slippage)) / 10000
    buy, sell = Decimal(100) * (1 + a), Decimal(100) * (1 - a)
    q = Decimal(1000) / (buy * (1 + f))
    entry_fee, exit_fee = q * buy * f, q * sell * f
    final = q * sell - exit_fee
    equity: list[float] = []

    def capture(values: Sequence[float]) -> float:
        equity.extend(values)
        peak = values[0]
        worst = 0.0
        for value in values:
            peak = max(peak, value)
            worst = min(worst, (value / peak - 1) * 100)
        return worst

    monkeypatch.setattr(metrics, "max_drawdown", capture)
    hold = strategy(
        comparison(PRICE, ">", {"type": "value", "value": 0}),
        comparison(PRICE, "<", {"type": "value", "value": 0}),
    )
    result = run_backtest(
        make_candles([100] * 4),
        BacktestConfig(
            initial_balance=1000,
            execution=ExecutionConfig(
                fee_rate=float(f), spread_bps=float(spread), slippage_bps=float(slippage)
            ),
        ),
        hold,
    )
    trade = result.trades[0]
    assert trade.quantity == pytest.approx(float(q), rel=1e-12)
    assert trade.entry_execution is not None and trade.exit_execution is not None
    assert trade.entry_execution.fee == pytest.approx(float(entry_fee), rel=1e-12)
    assert trade.exit_execution.fee == pytest.approx(float(exit_fee), rel=1e-12)
    assert trade.quantity * trade.entry_price + trade.entry_execution.fee == pytest.approx(1000)
    assert result.final_balance == pytest.approx(float(final), rel=1e-12)
    assert trade.pnl == pytest.approx(float(final - 1000), abs=1e-12)
    assert result.costs.fees == pytest.approx(float(entry_fee + exit_fee))
    assert result.costs.modeled_spread_cost == pytest.approx(
        float(q * 100 * Decimal(spread) / 10000)
    )
    assert result.costs.modeled_slippage_cost == pytest.approx(
        float(q * 200 * Decimal(slippage) / 10000)
    )
    assert equity[-1] == result.final_balance
    assert min(equity) >= 0
    assert result.max_drawdown_percent == pytest.approx(float((final / 1000 - 1) * 100))
    assert result.buy_and_hold_return_percent == pytest.approx(result.total_return_percent)
    assert result.benchmark_costs == result.costs
    assert all(math.isfinite(value) for value in equity)


def test_reference_price_gain_can_be_net_loss_without_changing_execution_timing() -> None:
    candles = make_candles([90, 100.1], [90, 100])
    costless = run_backtest(candles, BacktestConfig(initial_balance=1000, trading_fee=0), RULE)
    net = run_backtest(candles, BacktestConfig(initial_balance=1000, execution=EXECUTION), RULE)
    assert costless.trades[0].pnl == pytest.approx(1)
    expected = Decimal(1000) / (Decimal("100.2") * Decimal("1.001"))
    expected *= Decimal("99.8998") * Decimal("0.999")
    assert net.final_balance == pytest.approx(float(expected))
    assert net.trades[0].pnl < 0 and net.win_rate == 0 and net.profit_factor == 0
    assert net.losing_trades == 1 and net.winning_trades == 0
    assert net.trades[0].entry_time == costless.trades[0].entry_time
    assert net.trades[0].exit_time == costless.trades[0].exit_time


@pytest.mark.parametrize("side", ["entry", "exit"])
def test_fractional_spread_slippage_attribution_reconciles_each_fill(side: str) -> None:
    result = run_backtest(
        make_candles([90, 130], [90, 100]),
        BacktestConfig(
            execution=ExecutionConfig(fee_rate=0.002, spread_bps=7.5, slippage_bps=3.25)
        ),
        RULE,
    )
    trade = result.trades[0]
    fill = trade.entry_execution if side == "entry" else trade.exit_execution
    assert fill is not None
    sign = 1 if side == "entry" else -1
    assert sign * (fill.fill_price - fill.reference_price) == pytest.approx(
        fill.spread_adjustment_per_unit + fill.slippage_adjustment_per_unit, rel=1e-11
    )
    assert sign * fill.quantity * (fill.fill_price - fill.reference_price) == pytest.approx(
        fill.modeled_spread_cost + fill.modeled_slippage_cost, rel=1e-11
    )
    assert fill.fee == pytest.approx(fill.quantity * fill.fill_price * 0.002)
    assert fill.quantity == trade.quantity


def test_train_and_test_benchmarks_are_independent_net_round_trips() -> None:
    report = run_validation(
        small([90, 110, 200, 220], [90, 100, 200, 210]),
        validation_config(
            strategies=[named("frozen", RULE)],
            timeframe="6h",
            train_ratio=0.5,
            execution=EXECUTION,
            initial_balance=1000,
        ),
    )
    row = report.results[0]
    for segment, first, last in [(row.train, "90", "110"), (row.test, "200", "220")]:
        buy, sell = Decimal(first) * Decimal("1.002"), Decimal(last) * Decimal("0.998")
        q = Decimal(1000) / (buy * Decimal("1.001"))
        final = q * sell * Decimal("0.999")
        result = segment.result
        assert result.execution == EXECUTION
        assert result.buy_and_hold_return_percent == pytest.approx(float((final / 1000 - 1) * 100))
        assert result.benchmark_costs is not None
        assert result.benchmark_costs.fees == pytest.approx(
            float(q * (buy + sell) * Decimal("0.001"))
        )
        assert result.benchmark_costs.modeled_spread_cost == pytest.approx(
            float(q * (Decimal(first) + Decimal(last)) * Decimal("0.001"))
        )
        assert "net first evaluation open" in result.benchmark_policy
    assert row.test.result.benchmark_costs is not None
    assert row.test.result.costs.fees == 0 and row.test.result.benchmark_costs.fees > 0
    assert (
        row.train.result.buy_and_hold_return_percent != row.test.result.buy_and_hold_return_percent
    )


@pytest.mark.parametrize("count,start", [(0, 0), (1, 0), (3, 1), (3, 3)])
def test_empty_single_candle_and_warmup_benchmark_boundaries(count: int, start: int) -> None:
    candles = make_candles([1000000.0, 100.0, 110.0][:count])
    result = run_backtest(candles, BacktestConfig(execution=EXECUTION), evaluation_start=start)
    assert result.trades == [] and result.final_balance == result.initial_balance
    if start == count:
        assert result.buy_and_hold_return_percent is None and result.benchmark_costs is None
    else:
        first, last = Decimal(str(candles[start].open)), Decimal(str(candles[-1].close))
        expected = last * Decimal("0.998") * Decimal("0.999")
        expected /= first * Decimal("1.002") * Decimal("1.001")
        assert result.buy_and_hold_return_percent == pytest.approx(float((expected - 1) * 100))
    assert json.loads(result.model_dump_json())["equity_policy"] == "reference_prices"
    json.dumps(result.model_dump(mode="json"), allow_nan=False)


@pytest.mark.parametrize("period", [1, 2])
def test_legacy_rsi_signal_vectors_ignore_all_execution_costs(period: int) -> None:
    candles = make_candles([100, 90, 80, 100, 120, 60, 70, 110])
    vectors = [
        rsi_signals(
            candles,
            BacktestConfig(rsi_period=period, execution=execution),
        )
        for execution in [
            ExecutionConfig(fee_rate=0),
            EXECUTION,
            ExecutionConfig(fee_rate=0.9, spread_bps=19000, slippage_bps=400),
        ]
    ]
    assert vectors[0] == vectors[1] == vectors[2]
    assert 1 in vectors[0] and -1 in vectors[0]


def test_mixed_indicator_scenarios_preserve_signals_cache_and_train_only_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = {
        "type": "or",
        "conditions": [
            comparison(indicator("rsi", 2), "<", {"type": "value", "value": 45}),
            comparison(indicator("rsi", 3), "<", {"type": "value", "value": 40}),
            comparison(indicator("ema", 2), "<", indicator("sma", 2)),
        ],
    }
    exit = {
        "type": "or",
        "conditions": [
            comparison(indicator("rsi", 2), ">", {"type": "value", "value": 65}),
            comparison(indicator("ema", 3), "<", indicator("sma", 3)),
        ],
    }
    rule = strategy(entry, exit)
    config = scenario_config(strategy=rule, train_ratio=0.5)
    candles = history(([100.0, 90.0, 80.0, 120.0, 130.0, 50.0] * 7)[:39], warmup=15)
    changed = candles[:27] + [
        c.model_copy(
            update={
                "open": 1e8 + i,
                "high": 1e8 + i,
                "low": 1e8 + i,
                "close": 1e8 + i,
                "volume": 9e8,
            }
        )
        for i, c in enumerate(candles[27:])
    ]
    calls: list[tuple[tuple[float, ...], tuple[tuple[bool, bool], ...], tuple[object, ...]]] = []
    live_traces: list[tuple[tuple[str, int, bool], ...]] = []
    active: list[tuple[str, int, bool]] = []

    def trace(rule: object, index: int, context: Context) -> bool:
        # The valid typed rule is supplied by the unchanged engine.
        from strategy_backtest_agent.rules.models import Comparison, Group

        assert isinstance(rule, Comparison | Group)
        value = evaluate_rule(rule, index, context)
        active.append((rule.model_dump_json(), index, value))
        return value

    def audited(
        source: Sequence[Candle],
        portfolio: BacktestConfig,
        strategy: RuleStrategy | None = None,
        *,
        evaluation_start: int = 0,
        context: Context | None = None,
    ) -> BacktestResult:
        assert strategy is not None and context is not None
        assert len(source) == 27 and evaluation_start == 15
        assert all(c.timestamp < candles[27].timestamp for c in source)
        cache = tuple(
            (key, tuple(None if math.isnan(v) else v for v in values))
            for key, values in sorted(context.indicators.items())
        )
        signals = tuple(
            (evaluate_rule(strategy.entry, i, context), evaluate_rule(strategy.exit, i, context))
            for i in range(evaluation_start, len(source))
        )
        before = (tuple(context.prices), signals, cache)
        calls.append(before)
        active.clear()
        result = run_backtest(
            source, portfolio, strategy, evaluation_start=evaluation_start, context=context
        )
        live_traces.append(tuple(active))
        after_cache = tuple(
            (key, tuple(None if math.isnan(v) else v for v in values))
            for key, values in sorted(context.indicators.items())
        )
        assert after_cache == cache and tuple(context.prices) == before[0]
        return result

    monkeypatch.setattr(backtester, "evaluate_rule", trace)
    monkeypatch.setattr("strategy_backtest_agent.costs.engine.run_backtest", audited)
    providers = [Provider(candles), Provider(changed)]
    reports = [asyncio.run(fetch_and_run_costs(p, config)) for p in providers]
    assert all(len(p.requests) == 1 for p in providers)
    assert len(calls) == 6 and all(call == calls[0] for call in calls)
    assert all(trace == live_traces[0] for trace in live_traces)
    assert reports[0].results == reports[1].results
    assert reports[0].split == reports[1].split
    assert (
        reports[0].shared_data.indicator_initializations
        == reports[1].shared_data.indicator_initializations
    )
    assert reports[0].shared_data.candles_sha256 != reports[1].shared_data.candles_sha256
    assert len({row.train.result.final_balance for row in reports[0].results}) > 1
    assert all(row.train.result.initial_balance == 10000 for row in reports[0].results)
