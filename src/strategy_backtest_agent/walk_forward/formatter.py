"""Readable per-fold diagnostics and explicitly defined OOS statistics."""

from strategy_backtest_agent.comparison.formatter import _percent
from strategy_backtest_agent.execution import EXECUTION_WARNINGS, format_costs, format_execution
from strategy_backtest_agent.rules.formatter import format_rule
from strategy_backtest_agent.walk_forward.models import WalkForwardReport


def _points(value: float | None) -> str:
    return "N/A" if value is None else f"{value:+.2f} pp"


def format_walk_forward(report: WalkForwardReport) -> str:
    config, data = report.configuration, report.shared_data
    train, test, step = config.windows.counts(config.timeframe)
    lines = [
        "Walk-Forward Analysis",
        f"Symbol: {config.symbol}; timeframe: {config.timeframe}",
        f"Evaluation UTC: [{data.evaluation_start}, {data.evaluation_end})",
        format_execution(config.execution_config()),
        f"Windows: {config.windows.mode}; Train {train}, Test {test}, step {step} candles",
        f"Unused trailing candles: {report.unused_trailing_candles}",
        f"Data: {data.source}; SHA256: {data.candles_sha256}",
        f"Warm-up: {data.required_warmup_candles}; {data.warmup_policy}",
    ]
    for named in config.strategies:
        rule = named.to_rules()
        lines.extend(
            [
                f"{named.name} [{named.id}]",
                f"ENTRY: {format_rule(rule.entry)}",
                f"EXIT: {format_rule(rule.exit)}",
            ]
        )
    for row in report.results:
        lines.append(f"\n{row.fold_id} / {row.name} [{row.strategy_id}]")
        for label, segment in (("Train", row.train), ("Test", row.test)):
            result = segment.result
            factor = "N/A" if result.profit_factor is None else f"{result.profit_factor:.4f}"
            lines.extend(
                [
                    f"{label} UTC [{segment.start}, {segment.end}); candles {segment.candle_count}",
                    f"  Balance: {result.initial_balance:.2f} → {result.final_balance:.2f}",
                    f"  Return: {result.total_return_percent:+.4f}%; "
                    f"net Buy & Hold: {_percent(result.buy_and_hold_return_percent)}; "
                    f"excess: {_points(segment.excess_return_pp)}",
                    f"  Trades: {result.total_trades}; "
                    f"drawdown: {result.max_drawdown_percent:.4f}%; "
                    f"win rate: {_percent(result.win_rate)}; "
                    f"profit factor: {factor}",
                    f"  {format_costs(result.costs)}",
                ]
            )
    lines.append("\nAggregate OOS summary (Test only)")
    lines.append(report.aggregate_policy)
    for summary in report.summaries:
        lines.extend(
            [
                f"{summary.strategy_id}: {summary.fold_count} folds; "
                f"{summary.total_test_trades} completed Test trades",
                f"  Positive folds: {summary.positive_test_folds}/{summary.fold_count} "
                f"({summary.positive_test_fraction:.2%}); "
                f"outperforming net Buy & Hold: {summary.outperforming_test_folds}",
                f"  Test return median: {_percent(summary.median_test_return_percent)}; "
                f"range: {_percent(summary.minimum_test_return_percent)} to "
                f"{_percent(summary.maximum_test_return_percent)}",
                f"  Median fold drawdown: {_percent(summary.median_test_max_drawdown_percent)}; "
                f"median excess: {_points(summary.median_test_excess_return_pp)}",
            ]
        )
        if summary.stitched_oos_index is not None:
            lines.append("  Stitched OOS fold-endpoint index (independent portfolios):")
            lines.extend(
                f"    {point.time.isoformat()}: {point.value:.6f}"
                for point in summary.stitched_oos_index
            )
    lines.extend([*report.methodology_warnings, *EXECUTION_WARNINGS])
    return "\n".join(lines)
