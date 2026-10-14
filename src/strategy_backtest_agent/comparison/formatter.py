"""Pure Python rendering of calculated comparison results."""

from strategy_backtest_agent.comparison.models import ComparisonResult
from strategy_backtest_agent.execution import EXECUTION_WARNINGS, format_costs, format_execution
from strategy_backtest_agent.rules.formatter import format_rule


def _percent(value: float | None) -> str:
    return "N/A" if value is None else f"{value:+.2f}%"


def format_comparison(comparison: ComparisonResult) -> str:
    config, data = comparison.configuration, comparison.shared_data
    lines = [
        "Strategy Comparison",
        "─" * 32,
        f"Symbol: {config.symbol}",
        f"Timeframe: {config.timeframe}",
        f"Period: {config.period_days} days",
        f"Initial Balance: {config.initial_balance:,.2f} (quote currency)",
        f"Fee per side: {config.fee * 100:g}%",
        format_execution(config.execution_config()),
        f"Data: {data.source}",
        f"Evaluation (UTC): {data.evaluation_start.isoformat()} → "
        f"{data.evaluation_end.isoformat()}",
        f"Completed candle opens: {data.first_candle_open.isoformat()} → "
        f"{data.last_candle_open.isoformat()}",
        f"Candles: {data.candle_count}; prior warm-up: {data.warmup_candles} "
        "(excluded from results)",
        f"Warm-up policy: {data.warmup_policy}",
        f"Sort: {comparison.ranking_criterion} descending; undefined last; ties by ID",
        "",
    ]
    rows = [["Strategy", "Return", "Excess", "Max DD", "Trades", "Win rate", "Profit factor"]]
    by_id = {row.id: row for row in comparison.results}
    for id in comparison.ranking:
        row = by_id[id]
        result = row.result
        rows.append(
            [
                f"{row.name} [{id}]",
                _percent(result.total_return_percent),
                "N/A" if row.excess_return_pp is None else f"{row.excess_return_pp:+.2f} pp",
                _percent(result.max_drawdown_percent),
                str(result.total_trades),
                _percent(result.win_rate),
                "N/A" if result.profit_factor is None else f"{result.profit_factor:.2f}",
            ]
        )
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    for index, cells in enumerate(rows):
        lines.append(
            "  ".join(
                cell.ljust(width) if i == 0 else cell.rjust(width)
                for i, (cell, width) in enumerate(zip(cells, widths, strict=True))
            )
        )
        if index == 0:
            lines.append("─" * (sum(widths) + 2 * (len(widths) - 1)))
    lines.extend(["", f"Buy & Hold: {_percent(comparison.buy_and_hold_return_percent)}", ""])
    for row in comparison.results:
        lines.extend(
            [
                f"{row.name} [{row.id}]",
                f"  ENTRY: {format_rule(row.strategy.entry)}",
                f"  EXIT: {format_rule(row.strategy.exit)}",
                f"  {format_costs(row.result.costs)}",
            ]
        )
    lines.extend(["", *EXECUTION_WARNINGS])
    return "\n".join(lines)
