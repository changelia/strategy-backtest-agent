"""Readable scenario attribution; baseline differences without recommendations."""

from strategy_backtest_agent.comparison.formatter import _percent
from strategy_backtest_agent.costs.models import CostScenarioReport
from strategy_backtest_agent.execution import format_costs, format_execution
from strategy_backtest_agent.rules.formatter import format_rule


def format_cost_scenarios(report: CostScenarioReport) -> str:
    config, split = report.configuration, report.split
    lines = [
        "Execution Cost Scenarios",
        "In-sample Train only; one frozen strategy",
        f"Symbol: {config.symbol}; timeframe: {config.timeframe}; "
        f"period: {config.period_days} days",
        f"Train (UTC): [{split.train_start.isoformat()}, {split.train_end.isoformat()})",
        f"Reserved Test: [{split.test_start.isoformat()}, {split.test_end.isoformat()})",
        f"Initial balance per scenario: {config.initial_balance:,.2f}",
        f"SHA256: {report.shared_data.candles_sha256}",
        f"ENTRY: {format_rule(config.strategy.entry)}",
        f"EXIT: {format_rule(config.strategy.exit)}",
        f"Baseline: {report.baseline_id}; order is declared, not ranked",
    ]
    for row in report.results:
        result = row.train.result
        lines.extend(
            [
                "",
                f"{row.name} [{row.id}]",
                format_execution(row.execution),
                f"Final balance: {result.final_balance:,.2f}; "
                f"return: {_percent(result.total_return_percent)}; "
                f"difference vs baseline: {row.return_difference_pp:+.2f} pp",
                f"Buy & Hold (net): {_percent(result.buy_and_hold_return_percent)}; "
                f"drawdown: {_percent(result.max_drawdown_percent)}; trades: {result.total_trades}",
                format_costs(result.costs),
            ]
        )
    return "\n".join([*lines, "", *report.methodology_warnings])
