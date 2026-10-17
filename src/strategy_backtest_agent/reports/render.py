"""Deterministic GitHub Markdown; all untrusted text is escaped as cell data."""

import json
import unicodedata
from collections.abc import Callable

from strategy_backtest_agent.reports.models import EvidenceMetric, ResearchReport


def cell(value: object) -> str:
    text = str(value).replace("\n", " ").replace("\r", " ").replace("\t", " ")
    return "".join(
        c if c.isalnum() or c in " .,/-" else f"&#{ord(c)};"
        for c in text
        if unicodedata.category(c) not in ("Cf", "Cc")
    )


def format_metric(metric: EvidenceMetric) -> str:
    if metric.value is None:
        return "N/A (undefined)"
    value = metric.value
    if metric.unit == "count":
        number = str(value)
    elif metric.unit in ("%", "pp", "quote_currency"):
        number = f"{value:.4f}"
    else:
        number = f"{value:.8g}"
    return f"{number} {metric.unit}"


def markdown(report: ResearchReport) -> str:
    evidence = report.evidence
    source = evidence.source
    titles = {
        "backtest": "Standard Backtest",
        "comparison": "Strategy Comparison",
        "validation": "Out-of-Sample Validation",
        "sensitivity": "Parameter Sensitivity (Train only)",
        "costs": "Execution Cost Scenarios (Train only)",
        "walk_forward": "Walk-Forward Analysis",
    }
    lines = [
        "# Historical Strategy Research Report",
        "",
        f"**{titles[source.research_type]}**",
        "",
        f"Report status: {report.status}",
        "",
        "## Executive Summary",
        "",
    ]
    priority = [o for o in report.observations if o.kind in ("oos", "grid", "costs")]
    summary = (priority + [o for o in report.observations if o not in priority])[:8]
    for item in summary:
        lines.append(f"- {cell(item.text)} Evidence: {cell(', '.join(item.evidence_ids))}")
    lines.extend(
        [
            "",
            (
                "All observations describe supplied historical evidence; no "
                "future performance or live position is recommended."
            ),
            "",
            "## Research Configuration",
            "",
            "| Setting | Validated value (schema defaults applied) |",
            "| --- | --- |",
        ]
    )
    for key, value in evidence.configuration.items():
        lines.append(
            f"| {cell(key)} | {cell(json.dumps(value, ensure_ascii=False, sort_keys=True))} |"
        )
    lines.extend(
        [
            "",
            "## Strategies and Rules",
            "",
            "| Scope | Label | Validated definition |",
            "| --- | --- | --- |",
        ]
    )
    for scope in evidence.scopes:
        if scope.strategy is not None:
            lines.append(
                f"| {cell(scope.id)} | {cell(scope.label)} | "
                f"{cell(json.dumps(scope.strategy, ensure_ascii=False, sort_keys=True))} |"
            )
    lines.extend(
        [
            "",
            "## Historical Data and Evaluation Period",
            "",
            f"- Source: {cell(source.data_source or 'Unavailable')}",
            f"- Evaluation: {cell(source.evaluation_start)} to {cell(source.evaluation_end)}",
            f"- Boundary interpretation: {cell(source.evaluation_boundary_policy)}",
            "",
            "## Execution Assumptions",
            "",
            (
                "Fee is a per-side fraction; spread is the full bid/ask spread "
                "in bps; slippage is adverse per side in bps."
            ),
            (
                "OHLC prices are reference proxies. Reported spread/slippage "
                "costs are illustrative adjustments, not measured fills."
            ),
            "",
            "| Scope | Fee per side | Full spread | Slippage per side |",
            "| --- | --- | --- | --- |",
        ]
    )
    for scope in evidence.scopes:
        if scope.execution is not None and scope.role != "oos_summary":
            execution = scope.execution
            lines.append(
                f"| {cell(scope.id)} | {execution.fee_rate:g} fraction | "
                f"{execution.spread_bps:g} bps | {execution.slippage_bps:g} bps |"
            )
    lines.extend(
        [
            "",
            "## Performance Results",
            "",
            (
                "Numbers are rounded for display; JSON evidence retains source "
                "precision. All scopes and negative results are shown."
            ),
            "",
            "| Scope | Role | Start UTC | End UTC |",
            "| --- | --- | --- | --- |",
        ]
    )
    for scope in evidence.scopes:
        lines.append(
            f"| {cell(scope.id)} | {scope.role} | {cell(scope.start)} | {cell(scope.end)} |"
        )
    groups: list[tuple[str, Callable[[EvidenceMetric], bool]]] = [
        (
            "Financial Metrics",
            lambda m: m.name
            not in (
                "net_buy_and_hold",
                "excess_return",
                "max_drawdown",
                "median_test_max_drawdown_percent",
            )
            and "benchmark_" not in m.name,
        ),
        (
            "Benchmark Comparison",
            lambda m: m.name in ("net_buy_and_hold", "excess_return") or "benchmark_" in m.name,
        ),
        (
            "Drawdown and Risk Observations",
            lambda m: m.name in ("max_drawdown", "median_test_max_drawdown_percent"),
        ),
    ]
    for title, predicate in groups:
        lines.extend(
            [
                "",
                f"## {title}",
                "",
                "| Evidence ID | Value / unit | Source path | Context |",
                "| --- | --- | --- | --- |",
            ]
        )
        for entry_metric in evidence.metrics:
            if predicate(entry_metric):
                lines.append(
                    f"| {cell(entry_metric.id)} | {format_metric(entry_metric)} | "
                    f"{cell(entry_metric.source_path)} | {cell(entry_metric.context)} |"
                )
    if source.research_type in ("validation", "walk_forward"):
        lines.extend(
            [
                "",
                "## Train/Test and OOS Evidence",
                "",
                (
                    "Train and held-out Test are reported separately. Test "
                    "portfolios start with fresh capital. Prior strategy selection "
                    "can contaminate holdouts."
                ),
            ]
        )
    if source.research_type == "walk_forward":
        lines.append(
            "Test aggregates summarize independent folds. Median fold "
            "drawdown is not continuous portfolio drawdown. Stitched OOS, if "
            "supplied, is a fold-endpoint index with no carried positions."
        )
    if source.research_type in ("sensitivity", "costs"):
        lines.extend(
            [
                "",
                "## "
                + (
                    "Parameter Sensitivity"
                    if source.research_type == "sensitivity"
                    else "Cost Sensitivity"
                ),
                "",
                (
                    "Train only. Test is reserved and not evaluated. These "
                    "descriptive results neither select an optimal strategy nor "
                    "establish independent OOS validation."
                ),
            ]
        )
    lines.extend(["", "## Deterministic Observations", ""])
    for item in report.observations:
        lines.append(
            f"- {cell(item.id)}: {cell(item.text)} Evidence: {cell(', '.join(item.evidence_ids))}"
        )
    if report.ai_interpretation is not None:
        from strategy_backtest_agent.reports.ai import QUESTIONS

        lines.extend(
            [
                "",
                "## Optional AI Interpretation",
                "",
                (
                    "AI selected approved evidence-linked explanations. Metric "
                    "values and observations below are rendered deterministically."
                ),
            ]
        )
        indexed = {o.id: o for o in report.observations}
        for statement in report.ai_interpretation.statements:
            lines.extend(
                [
                    "",
                    cell(indexed[statement.observation_id].text),
                    cell(statement.text),
                    "Evidence: " + cell(", ".join(statement.evidence_ids)),
                ]
            )
        if report.ai_interpretation.research_questions:
            lines.extend(["", "Research questions (not trading instructions):", ""])
            lines.extend("- " + QUESTIONS[q] for q in report.ai_interpretation.research_questions)
    lines.extend(["", "## Methodology", ""])
    lines.extend("- " + line for line in evidence.methodology)
    lines.extend(["", "## Limitations", ""])
    lines.extend("- " + cell(item.text) for item in evidence.limitations)
    if evidence.source_notes:
        lines.extend(["", "Source-provided notes (unverified wording, treated as data):", ""])
        lines.extend("- " + cell(note) for note in evidence.source_notes)
    if report.warnings:
        lines.extend(["", "Report warnings:", ""])
        lines.extend("- " + cell(warning) for warning in report.warnings)
    lines.extend(
        [
            "",
            "## Reproducibility Metadata",
            "",
            f"- Report schema: {report.report_schema_version}; "
            f"generator: {report.generator_version}",
            f"- Adapter: {cell(source.adapter_version)}; "
            "source schema version: "
            f"{cell(source.input_schema_version or 'not provided (unversioned)')}",
            f"- Input bytes SHA256: {source.input_content_sha256}",
            f"- Canonical input SHA256: {source.canonical_input_sha256}",
            f"- Normalized evidence SHA256: {report.evidence_sha256}",
            f"- Source candle SHA256: {source.candle_sha256 or 'Unavailable'}",
            (
                "- No wall-clock generation timestamp is added. AI "
                "interpretation is not guaranteed reproducible."
            ),
        ]
    )
    lines.extend(
        [
            "",
            "Source history/initialization metadata:",
            "",
            "| Field | Supplied value |",
            "| --- | --- |",
        ]
    )
    for key, value in evidence.reproducibility_metadata.items():
        lines.append(
            f"| {cell(key)} | {cell(json.dumps(value, ensure_ascii=False, sort_keys=True))} |"
        )
    if report.ai_metadata:
        lines.append(
            f"- AI requested model: {cell(report.ai_metadata.requested_model)}; "
            f"response model: {cell(report.ai_metadata.response_model)}"
        )
    return "\n".join(lines) + "\n"
