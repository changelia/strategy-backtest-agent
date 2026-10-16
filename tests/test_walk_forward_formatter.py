"""Human-readable percentage points retain full JSON precision."""

from test_walk_forward import history, settings

from strategy_backtest_agent.walk_forward.engine import run_walk_forward
from strategy_backtest_agent.walk_forward.formatter import format_walk_forward


def test_display_percentage_points_are_rounded_without_changing_json() -> None:
    config = settings(fee=0.001, execution={"spread_bps": 10, "slippage_bps": 5})
    report = run_walk_forward(history(config), config)
    raw_json = report.model_dump_json()
    output = format_walk_forward(report)
    for row in report.results:
        for segment in (row.train, row.test):
            value = segment.excess_return_pp
            assert value is not None
            assert f"excess: {value:+.2f} pp" in output
    summary = report.summaries[0]
    assert summary.median_test_excess_return_pp is not None
    assert f"median excess: {summary.median_test_excess_return_pp:+.2f} pp" in output
    assert report.model_dump_json() == raw_json


def test_display_undefined_percentage_points_as_na() -> None:
    from strategy_backtest_agent.walk_forward.formatter import _points

    assert _points(None) == "N/A"
    assert _points(-2.123456) == "-2.12 pp"
    assert _points(3.456789) == "+3.46 pp"
