"""Readable validation results, with no ranking or performance claims."""

from strategy_backtest_agent.comparison.formatter import _percent
from strategy_backtest_agent.rules.formatter import format_rule
from strategy_backtest_agent.validation.models import ValidationReport


def format_validation(report: ValidationReport) -> str:
    config, data = report.configuration, report.shared_data
    lines = [
        "Strategy Validation",
        f"Symbol: {config.symbol}",
        f"Timeframe: {config.timeframe}",
        f"Period: {config.period_days} days",
        f"Split: {100 * config.train_ratio:g}% Train / {100 * (1 - config.train_ratio):g}% Test",
        f"Fee per side: {config.fee * 100:g}%",
        f"Data: {data.source}; SHA256: {data.candles_sha256}",
        f"Warm-up: {data.warmup_candles} prior candles; {data.warmup_policy}",
    ]
    for row in report.results:
        lines.extend(
            [
                "",
                f"{row.name} [{row.id}]",
                f"ENTRY: {format_rule(row.strategy.entry)}",
                f"EXIT: {format_rule(row.strategy.exit)}",
            ]
        )
        for label, segment in (("Train", row.train), ("Test — Held-out evaluation", row.test)):
            result = segment.result
            lines.extend(
                [
                    f"{label}:",
                    f"  UTC [{segment.start.isoformat()}, {segment.end.isoformat()})",
                    f"  Candles: {segment.candle_count}; "
                    f"preceding history: {segment.warmup_candles}",
                    f"  Initial Balance: {result.initial_balance:,.2f}",
                    f"  Final Balance: {result.final_balance:,.2f}",
                    f"  Return: {_percent(result.total_return_percent)}",
                    f"  Buy & Hold: {_percent(result.buy_and_hold_return_percent)}",
                    "  Excess Return: "
                    + (
                        "N/A"
                        if segment.excess_return_pp is None
                        else f"{segment.excess_return_pp:+.2f} pp"
                    ),
                    f"  Max Drawdown: {_percent(result.max_drawdown_percent)}",
                    f"  Trades: {result.total_trades}",
                    f"  Win Rate: {_percent(result.win_rate)}",
                    "  Profit Factor: "
                    + (
                        "N/A (undefined)"
                        if result.profit_factor is None
                        else f"{result.profit_factor:.2f}"
                    ),
                ]
            )
        lines.append(f"Return gap (Test − Train): {row.return_gap_pp:+.2f} pp")
    lines.extend(["", *report.methodology_warnings])
    return "\n".join(lines)
