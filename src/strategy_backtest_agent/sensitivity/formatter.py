"""In-sample grid tables and return matrix; never rank or recommend variants."""

from strategy_backtest_agent.comparison.formatter import _percent
from strategy_backtest_agent.rules.formatter import format_rule
from strategy_backtest_agent.sensitivity.models import MIN_OBSERVATION_TRADES, SensitivityReport


def _table(rows: list[list[str]]) -> list[str]:
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    return [
        "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True))
        for row in rows
    ]


def format_sensitivity(report: SensitivityReport) -> str:
    config, split = report.configuration, report.split
    lines = [
        "Parameter Sensitivity Analysis",
        "In-sample sensitivity analysis — Train only",
        f"Symbol: {config.symbol}",
        f"Timeframe: {config.timeframe}",
        f"Historical period: {config.period_days} days",
        f"Train ratio: {config.train_ratio * 100:g}%",
        f"Evaluated Train (UTC): [{split.train_start.isoformat()}, {split.train_end.isoformat()})",
        f"Reserved Test (not evaluated): [{split.test_start.isoformat()}, "
        f"{split.test_end.isoformat()})",
        f"Initial balance per variant: {config.initial_balance:,.2f}; "
        f"fee per side: {config.fee * 100:g}%",
        f"Train candles: {split.train_candle_count}; warm-up: {report.shared_data.warmup_candles}",
        f"SHA256: {report.shared_data.candles_sha256}",
        "",
        "Base strategy:",
        f"  ENTRY: {format_rule(config.base_strategy.entry)}",
        f"  EXIT: {format_rule(config.base_strategy.exit)}",
        "",
        "Parameters:",
    ]
    for parameter in report.parameters:
        lines.append(f"  {parameter.path}: {parameter.values}")
        if parameter.coupled_paths:
            lines.append(f"    Explicitly coupled: {', '.join(parameter.coupled_paths)}")
    rows = [
        [
            "Variant",
            "Values",
            "Return",
            "Buy & Hold",
            "Excess (pp)",
            "Max DD",
            "Trades",
            "Win rate",
            "Profit factor",
            "Observation",
        ]
    ]
    for variant, row in zip(report.variants, report.results, strict=True):
        result = row.train.result
        rows.append(
            [
                variant.id,
                ", ".join(f"{v:g}" for v in variant.parameter_values.values()),
                _percent(result.total_return_percent),
                _percent(result.buy_and_hold_return_percent),
                "N/A"
                if row.train.excess_return_pp is None
                else f"{row.train.excess_return_pp:+.2f}",
                _percent(result.max_drawdown_percent),
                str(result.total_trades),
                _percent(result.win_rate),
                "N/A" if result.profit_factor is None else f"{result.profit_factor:.2f}",
                row.observation.replace("_", " "),
            ]
        )
    lines.extend(["", "Results (declared parameter order):", *_table(rows)])
    summary = report.summary
    lines.extend(
        [
            "",
            "Summary (evaluated grid only):",
            f"  Minimum / Median / Maximum return: {_percent(summary.minimum_return_percent)} / "
            f"{_percent(summary.median_return_percent)} / "
            f"{_percent(summary.maximum_return_percent)}",
            f"  Return range: {summary.return_range_pp:.2f} pp",
            f"  Positive return: {summary.positive_return_percent:.2f}% of variants",
            f"  Outperform Buy & Hold: "
            f"{_percent(summary.outperforming_buy_and_hold_percent)} of variants",
            f"  Insufficient trades (<{summary.minimum_observation_trades}): "
            f"{', '.join(summary.insufficient_trade_variant_ids) or 'none'}",
        ]
    )
    if report.matrix is not None:
        matrix = report.matrix
        rows = [
            [
                f"{matrix.row_parameter} / {matrix.column_parameter}",
                *(f"{value:g}" for value in matrix.column_values),
            ]
        ]
        for value, returns, trades in zip(
            matrix.row_values, matrix.returns_percent, matrix.trade_counts, strict=True
        ):
            rows.append(
                [
                    f"{value:g}",
                    *(
                        f"{result:+.2f}%" + ("*" if count < MIN_OBSERVATION_TRADES else "")
                        for result, count in zip(returns, trades, strict=True)
                    ),
                ]
            )
        lines.extend(["", "Train return matrix (* insufficient trades):", *_table(rows)])
    elif report.ordered_series is not None:
        lines.extend(
            [
                "",
                "Ordered parameter-versus-return series:",
                *(
                    f"  {point.value:g} → {_percent(point.return_percent)} "
                    f"({point.total_trades} trades)"
                    for point in report.ordered_series
                ),
            ]
        )
    lines.extend(["", *report.methodology_warnings])
    return "\n".join(lines)
