"""Hand-calculated descriptive summaries, adjacency, matrices and trade sufficiency."""

from datetime import timedelta

import pytest
from test_comparison_engine import END
from test_sensitivity_grid import RSI, spec

from strategy_backtest_agent.models import BacktestResult
from strategy_backtest_agent.sensitivity.analysis import describe_grid
from strategy_backtest_agent.sensitivity.grid import expand_grid
from strategy_backtest_agent.sensitivity.models import VariantResult
from strategy_backtest_agent.validation.models import SegmentResult


def result(
    id: str, return_percent: float, trades: int = 5, benchmark: float | None = 0
) -> VariantResult:
    return VariantResult(
        variant_id=id,
        observation="no_neighbors",
        train=SegmentResult(
            start=END - timedelta(hours=12),
            end=END,
            candle_count=12,
            warmup_candles=3,
            excess_return_pp=return_percent - benchmark if benchmark is not None else None,
            result=BacktestResult(
                initial_balance=1000,
                final_balance=1000 * (1 + return_percent / 100),
                total_return_percent=return_percent,
                buy_and_hold_return_percent=benchmark,
                total_trades=trades,
                winning_trades=0,
                losing_trades=0,
                win_rate=None,
                max_drawdown_percent=0,
                profit_factor=None,
                trades=[],
            ),
        ),
    )


def test_manual_summary_and_matrix_ordering() -> None:
    definitions, variants = expand_grid(
        RSI, [spec(values=[35, 25]), spec("exit.right.value", values=[75, 65])]
    )
    rows = [
        result(v.id, r, benchmark=5)
        for v, r in zip(variants, [-10.0, 0.0, 10.0, 30.0], strict=True)
    ]
    summary, edges, series, matrix = describe_grid(definitions, variants, rows)
    assert summary.minimum_return_percent == -10
    assert summary.median_return_percent == 5
    assert summary.maximum_return_percent == 30
    assert summary.return_range_pp == 40
    assert summary.positive_return_percent == 50
    assert summary.outperforming_buy_and_hold_percent == 50
    assert series is None and matrix is not None
    assert matrix.row_values == [35, 25] and matrix.column_values == [75, 65]
    assert matrix.returns_percent == [[-10, 0], [10, 30]]
    assert matrix.variant_ids == [["variant-001", "variant-002"], ["variant-003", "variant-004"]]
    assert len(edges) == 4
    assert (
        edges[0].first_variant_id == "variant-001" and edges[0].second_variant_id == "variant-003"
    )
    assert edges[0].return_difference_pp == 20
    assert all(edge.sufficient_trades for edge in edges)


@pytest.mark.parametrize(
    "returns,expected",
    [
        ([10.0, 11.0, 12.0], "similar_to_all_neighbors"),
        ([0.0, 30.0, 0.0], "isolated_positive_spike"),
        ([0.0, 10.0, 20.0], "mixed_neighbors"),
    ],
)
def test_descriptive_neighbor_observations(returns: list[float], expected: str) -> None:
    parameters, variants = expand_grid(RSI, [spec()])
    rows = [result(v.id, r) for v, r in zip(variants, returns, strict=True)]
    summary, edges, series, matrix = describe_grid(parameters, variants, rows)
    assert rows[1].observation == expected
    assert summary.median_return_percent == sorted(returns)[1]
    assert series is not None and matrix is None
    assert [p.value for p in series] == [25, 30, 35]
    assert len(edges) == 2


@pytest.mark.parametrize("trades", [0, 1, 4])
def test_insufficient_trade_variants_cannot_be_labeled_stable_or_spikes(trades: int) -> None:
    definitions, variants = expand_grid(RSI, [spec()])
    rows = [result(v.id, 0, trades=trades) for v in variants]
    summary, edges, _, _ = describe_grid(definitions, variants, rows)
    assert all(row.observation == "insufficient_trades" for row in rows)
    assert summary.insufficient_trade_variant_ids == [v.id for v in variants]
    assert all(not edge.sufficient_trades for edge in edges)


def test_low_trade_neighbor_prevents_region_claim() -> None:
    definitions, variants = expand_grid(RSI, [spec()])
    rows = [result(v.id, 10, trades=0 if i == 0 else 5) for i, v in enumerate(variants)]
    describe_grid(definitions, variants, rows)
    assert rows[1].observation == "insufficient_neighbor_trades"


def test_singleton_grid_and_null_benchmark() -> None:
    definitions, variants = expand_grid(RSI, [spec(values=[30])])
    rows = [result(variants[0].id, 0, benchmark=None)]
    summary, edges, _, matrix = describe_grid(definitions, variants, rows)
    assert summary.median_return_percent == summary.return_range_pp == 0
    assert summary.outperforming_buy_and_hold_percent is None
    assert rows[0].observation == "no_neighbors"
    assert edges == [] and matrix is None


def test_three_dimensions_have_edges_but_no_matrix_or_series() -> None:
    definitions, variants = expand_grid(
        RSI,
        [
            spec(values=[25, 35]),
            spec("exit.right.value", values=[65, 75]),
            spec("entry.left.period", values=[2, 3]),
        ],
    )
    rows = [result(v.id, 0) for v in variants]
    summary, edges, series, matrix = describe_grid(definitions, variants, rows)
    assert len(edges) == 12 and summary.variant_count == 8
    assert series is None and matrix is None
