"""Manual financial accounting, price adjustments and exact v0.6.0 numerical compatibility."""

import json
import math
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

import pytest
from conftest import make_candles
from pydantic import ValidationError
from test_rules import comparison, strategy

from strategy_backtest_agent import metrics
from strategy_backtest_agent.backtester import run_backtest
from strategy_backtest_agent.demo import demo_candles
from strategy_backtest_agent.execution import quote_execution, total_costs
from strategy_backtest_agent.models import BacktestConfig, ExecutionConfig
from strategy_backtest_agent.rules.models import RuleStrategy

PRICE = {"type": "price"}
RULE = strategy(
    comparison(PRICE, "<", {"type": "value", "value": 95}),
    comparison(PRICE, ">", {"type": "value", "value": 115}),
)
EXECUTION = ExecutionConfig(fee_rate=0.001, spread_bps=20, slippage_bps=10)


@pytest.mark.parametrize("field", ["fee_rate", "spread_bps", "slippage_bps"])
@pytest.mark.parametrize("value", [-1, math.nan, math.inf, -math.inf, True, "10"])
def test_invalid_cost_inputs(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        ExecutionConfig.model_validate({field: value})


@pytest.mark.parametrize(
    "values",
    [
        {"fee_rate": 1},
        {"spread_bps": 20000},
        {"slippage_bps": 10000},
        {"spread_bps": 10000, "slippage_bps": 5000},
        {"spread_bps": 1e308},
    ],
)
def test_economically_invalid_cost_inputs(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ExecutionConfig.model_validate(values)


@pytest.mark.parametrize(
    "spread,slippage", [(0, 0), (20, 10), (19998, 0), (0, 9999), (15998, 2000), (0.5, 0.25)]
)
def test_zero_fractional_and_extreme_valid_costs(spread: float, slippage: float) -> None:
    config = ExecutionConfig(fee_rate=0.99, spread_bps=spread, slippage_bps=slippage)
    result = run_backtest(
        make_candles([90, 110], [90, 100]), BacktestConfig(execution=config), RULE
    )
    assert 0 < result.final_balance <= result.initial_balance * 2
    assert math.isfinite(result.final_balance)
    assert result.trades[0].quantity > 0
    assert result.trades[0].exit_price > 0
    assert result.trades[0].entry_execution is not None
    assert result.trades[0].exit_execution is not None
    assert result.trades[0].entry_execution.fee >= 0
    assert result.trades[0].exit_execution.fee >= 0
    json.dumps(result.model_dump(mode="json"), allow_nan=False)


def test_half_spread_and_slippage_are_separate_from_fees() -> None:
    buy = quote_execution(100, "buy", EXECUTION)
    sell = quote_execution(110, "sell", EXECUTION)
    assert buy.fill_price == pytest.approx(100.20)
    assert sell.fill_price == pytest.approx(109.78)
    assert buy.spread_adjustment_per_unit == pytest.approx(0.10)
    assert buy.slippage_adjustment_per_unit == pytest.approx(0.10)
    assert sell.spread_adjustment_per_unit == pytest.approx(0.11)
    assert sell.slippage_adjustment_per_unit == pytest.approx(0.11)
    assert quote_execution(100, "buy", ExecutionConfig(spread_bps=20)).fill_price == pytest.approx(
        100.10
    )
    assert quote_execution(100, "sell", ExecutionConfig(spread_bps=20)).fill_price == pytest.approx(
        99.90
    )


@pytest.mark.parametrize("price", [0, -1, math.inf, math.nan, True])
def test_invalid_reference_prices(price: float) -> None:
    with pytest.raises(ValidationError):
        quote_execution(price, "buy", EXECUTION)


def test_overflowing_fills_rejected() -> None:
    with pytest.raises(ValidationError):
        quote_execution(1e308, "buy", ExecutionConfig(slippage_bps=9999))
    with pytest.raises(ValidationError):
        quote_execution(1e-323, "sell", ExecutionConfig(slippage_bps=9999))


def test_manually_calculated_quantity_fees_pnl_equity_and_net_benchmark(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candles = make_candles([90, 120, 130], [90, 100, 110])
    samples: list[float] = []
    original = metrics.max_drawdown

    def capture(equity: Sequence[float]) -> float:
        samples.extend(equity)
        return original(equity)

    monkeypatch.setattr(metrics, "max_drawdown", capture)
    result = run_backtest(candles, BacktestConfig(initial_balance=1000, execution=EXECUTION), RULE)
    # Decimal arithmetic is an independent oracle, not the implementation under test.
    quantity = Decimal(1000) / (Decimal("100.20") * Decimal("1.001"))
    entry_fee = quantity * Decimal("100.20") * Decimal("0.001")
    exit_fee = quantity * Decimal("109.78") * Decimal("0.001")
    final = quantity * Decimal("109.78") * Decimal("0.999")
    trade = result.trades[0]
    assert trade.entry_time == candles[1].timestamp and trade.exit_time == candles[2].timestamp
    assert trade.entry_price == pytest.approx(100.20) and trade.exit_price == pytest.approx(109.78)
    assert trade.quantity == pytest.approx(float(quantity), rel=1e-12)
    assert trade.entry_execution is not None and trade.exit_execution is not None
    assert (
        trade.entry_execution.reference_price == 100 and trade.exit_execution.reference_price == 110
    )
    assert trade.entry_execution.fee == pytest.approx(float(entry_fee))
    assert trade.exit_execution.fee == pytest.approx(float(exit_fee))
    assert not trade.entry_execution.forced and not trade.exit_execution.forced
    assert trade.quantity * trade.entry_price + trade.entry_execution.fee == pytest.approx(1000)
    assert result.final_balance == pytest.approx(float(final), rel=1e-12)
    assert trade.pnl == pytest.approx(float(final - 1000))
    assert trade.pnl_percent == pytest.approx(result.total_return_percent)
    assert result.winning_trades == 1 and result.losing_trades == 0 and result.win_rate == 100
    assert result.profit_factor is None
    assert result.costs.fees == pytest.approx(float(entry_fee + exit_fee))
    assert result.costs.modeled_spread_cost == pytest.approx(float(quantity * Decimal("0.21")))
    assert result.costs.modeled_slippage_cost == pytest.approx(float(quantity * Decimal("0.21")))
    assert trade.pnl == pytest.approx(
        trade.quantity * (110 - 100)
        - result.costs.fees
        - result.costs.modeled_spread_cost
        - result.costs.modeled_slippage_cost
    )
    assert samples == pytest.approx(
        [1000, 1000, 1000, float(quantity * 100), float(quantity * 120), float(final), float(final)]
    )
    assert result.max_drawdown_percent == pytest.approx((109.78 * 0.999 / 120 - 1) * 100)
    benchmark = (
        Decimal("129.74") * Decimal("0.999") / (Decimal("90.18") * Decimal("1.001")) - 1
    ) * 100
    assert result.buy_and_hold_return_percent == pytest.approx(float(benchmark))
    assert result.benchmark_costs is not None
    benchmark_quantity = Decimal(1000) / (Decimal("90.18") * Decimal("1.001"))
    assert result.benchmark_costs.fees == pytest.approx(
        float(benchmark_quantity * Decimal("0.001") * (Decimal("90.18") + Decimal("129.74")))
    )
    assert result.equity_policy == "reference_prices"


def test_forced_liquidation_adjusts_final_close_once() -> None:
    candles = make_candles([90, 110], [90, 100])
    result = run_backtest(candles, BacktestConfig(initial_balance=1000, execution=EXECUTION), RULE)
    trade = result.trades[0]
    assert trade.entry_time == trade.exit_time == candles[1].timestamp
    assert trade.exit_execution is not None and trade.exit_execution.forced
    assert trade.exit_execution.reference_price == 110
    assert trade.exit_price == pytest.approx(109.78)
    assert result.final_balance == pytest.approx(1000 / (100.20 * 1.001) * 109.78 * 0.999)
    assert trade.entry_execution is not None
    assert result.costs == total_costs([trade.entry_execution, trade.exit_execution])


def test_losing_and_winning_trades_use_net_cost_pnl() -> None:
    always = strategy(comparison(PRICE, ">", {"type": "value", "value": 0}))
    result = run_backtest(
        make_candles([100, 100, 100, 100, 110]),
        BacktestConfig(initial_balance=1000, execution=EXECUTION),
        always,
    )
    assert len(result.trades) == 2
    assert result.trades[0].pnl < 0 and result.trades[1].pnl > 0
    assert result.win_rate == 50
    assert result.profit_factor == pytest.approx(result.trades[1].pnl / -result.trades[0].pnl)
    assert result.final_balance == pytest.approx(1000 + sum(t.pnl for t in result.trades))
    fills = [
        fill
        for t in result.trades
        for fill in (t.entry_execution, t.exit_execution)
        if fill is not None
    ]
    assert result.costs == total_costs(fills)
    assert result.trades[0].quantity != result.trades[1].quantity
    assert result.costs.modeled_spread_cost == pytest.approx(
        sum(f.quantity * f.reference_price * 0.001 for f in fills)
    )


def test_costs_are_not_charged_repeatedly_at_equity_marks() -> None:
    hold = strategy(
        comparison(PRICE, ">", {"type": "value", "value": 0}),
        comparison(PRICE, "<", {"type": "value", "value": 0}),
    )
    config = BacktestConfig(execution=EXECUTION)
    short = run_backtest(make_candles([100] * 2), config, hold)
    long = run_backtest(make_candles([100] * 50), config, hold)
    assert short.final_balance == long.final_balance
    assert short.costs == long.costs and short.max_drawdown_percent == long.max_drawdown_percent


def test_no_trade_costs_are_zero_but_benchmark_is_cost_aware() -> None:
    result = run_backtest(make_candles([100] * 20), BacktestConfig(execution=EXECUTION))
    assert result.total_trades == 0 and result.final_balance == 10000
    assert (
        result.costs.fees
        == result.costs.modeled_spread_cost
        == result.costs.modeled_slippage_cost
        == 0
    )
    assert result.win_rate is result.profit_factor is None
    assert result.buy_and_hold_return_percent == pytest.approx(
        (99.8 * 0.999 / (100.2 * 1.001) - 1) * 100
    )


def test_constructed_cost_configs_are_revalidated() -> None:
    invalid = ExecutionConfig.model_construct(fee_rate=0.001, spread_bps=-1, slippage_bps=0)
    with pytest.raises(ValidationError):
        quote_execution(100, "buy", invalid)
    config = BacktestConfig.model_construct(execution=invalid)
    with pytest.raises(ValidationError):
        run_backtest(make_candles([100] * 20), config)


@pytest.mark.parametrize("case_index", range(9))
@pytest.mark.parametrize("explicit_zero", [False, True])
def test_original_v060_metrics_and_trade_fields_match_exactly(
    case_index: int, explicit_zero: bool
) -> None:
    baseline = json.loads(Path("tests/fixtures/v060-execution-baseline.json").read_text())
    assert baseline["source_commit"] == "d04a502f3e6cc212918129060656fbb94fc3f685"
    case = baseline["cases"][case_index]
    candles = demo_candles("1h", case["days"]) if "days" in case else make_candles(case["closes"])
    rules = RuleStrategy.model_validate(case["strategy"]) if case["strategy"] else None
    configuration = dict(case["config"])
    if explicit_zero:
        configuration["execution"] = {"spread_bps": 0, "slippage_bps": 0}
    result = run_backtest(
        candles,
        BacktestConfig.model_validate(configuration),
        rules,
        evaluation_start=case["evaluation_start"],
    ).model_dump(mode="json")
    expected = case["expected"]
    for key, value in expected.items():
        if key == "trades":
            assert [
                {field: trade[field] for field in old}
                for trade, old in zip(result[key], value, strict=True)
            ] == value
        else:
            assert result[key] == value


def test_nonfinite_equity_is_rejected_even_when_input_prices_are_finite() -> None:
    hold = strategy(
        comparison(PRICE, ">", {"type": "value", "value": 0}),
        comparison(PRICE, "<", {"type": "value", "value": 0}),
    )
    with pytest.raises(ValueError, match="portfolio equity"):
        run_backtest(make_candles([1, 1, 1e308, 1]), BacktestConfig(), hold)
