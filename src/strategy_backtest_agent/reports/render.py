"""Compact deterministic Markdown. JSON evidence and research calculations are unchanged."""

import json
import unicodedata
from collections import OrderedDict
from datetime import datetime
from typing import Any

from strategy_backtest_agent.reports.inputs import LegacyCLISettings
from strategy_backtest_agent.reports.models import EvidenceMetric, EvidenceScope, ResearchReport
from strategy_backtest_agent.rules.formatter import format_rule
from strategy_backtest_agent.rules.models import RuleStrategy


def cell(value: object) -> str:
    text = str(value).replace("\n", " ").replace("\r", " ").replace("\t", " ")
    escaped = []
    for char in text:
        if unicodedata.category(char) in ("Cf", "Cc"):
            continue
        if char in "&<>":
            escaped.append({"&": "&amp;", "<": "&lt;", ">": "&gt;"}[char])
        elif char in "\\`*_{}[]|#!":
            escaped.append("\\" + char)
        else:
            escaped.append(char)
    return "".join(escaped)


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
    if metric.unit == "count":
        return number
    unit = "quote" if metric.unit == "quote_currency" else metric.unit
    return f"{number} {unit}"


def title(value: str) -> str:
    return value.replace("_", " ").capitalize().replace("test ", "Test ")


def scalar(value: Any) -> str:
    if value is None:
        return "Not provided"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def append_values(lines: list[str], values: dict[str, Any], prefix: str = "") -> None:
    """Flatten nested metadata into bounded-width rows, never serialized JSON cells."""
    for key, value in values.items():
        label = prefix + title(key)
        if isinstance(value, dict):
            append_values(lines, value, label + " / ")
        elif isinstance(value, list):
            if not value:
                lines.append(f"| {cell(label)} | None |")
            elif all(not isinstance(v, dict | list) for v in value):
                lines.append(f"| {cell(label)} | {cell(', '.join(map(scalar, value)))} |")
            else:
                for index, item in enumerate(value, 1):
                    if isinstance(item, dict):
                        append_values(lines, item, f"{label} {index} / ")
                    else:
                        lines.append(f"| {cell(label)} {index} | {cell(scalar(item))} |")
        else:
            lines.append(f"| {cell(label)} | {cell(scalar(value))} |")


def utc(value: datetime | None) -> str:
    return value.isoformat(sep=" ").removesuffix("+00:00") if value else "Not provided"


def scope_label(scope: EvidenceScope) -> str:
    if scope.id.startswith("fold."):
        fold = scope.id.split(".")[1].replace("fold-", "Fold ")
        return f"{scope.label} ({fold}, {scope.role.title()})"
    if scope.role == "oos_summary":
        return f"{scope.label} (OOS summary)"
    if scope.role == "stitched_index":
        return "Stitched OOS endpoint " + scope.id.rsplit(".", 1)[-1]
    return f"{scope.label} ({scope.role.replace('_', ' ').title()})"


def metric_tables(
    lines: list[str],
    scopes: list[EvidenceScope],
    metrics: list[EvidenceMetric],
    short: dict[str, str],
) -> None:
    groups = [
        (
            "Returns and benchmark",
            [
                "initial_balance",
                "final_balance",
                "net_pnl",
                "total_return",
                "net_buy_and_hold",
                "excess_return",
                "max_drawdown",
            ],
        ),
        (
            "Trades",
            ["completed_trades", "winning_trades", "losing_trades", "win_rate", "profit_factor"],
        ),
        (
            "Execution costs (quote currency)",
            [
                "fees",
                "modeled_spread_cost",
                "modeled_slippage_cost",
                "benchmark_fees",
                "benchmark_modeled_spread_cost",
                "benchmark_modeled_slippage_cost",
            ],
        ),
    ]
    lookup = {(m.scope, m.name): m for m in metrics}
    shown = {"fee_per_side", "full_spread", "slippage_per_side"}
    for heading, names in groups:
        present = [name for name in names if any((s.id, name) in lookup for s in scopes)]
        if not present:
            continue
        lines.extend(
            [
                "",
                f"#### {heading}",
                "",
                "| Segment | " + " | ".join(title(n) for n in present) + " |",
                "| --- | " + " | ".join("---" for _ in present) + " |",
            ]
        )
        for scope in scopes:
            if not any((scope.id, n) in lookup for n in present):
                continue
            values = [
                format_metric(lookup[scope.id, n]) if (scope.id, n) in lookup else "Not supplied"
                for n in present
            ]
            lines.append(f"| {short[scope.id]} | " + " | ".join(values) + " |")
        shown.update(present)
    remaining = [m for m in metrics if m.scope in {s.id for s in scopes} and m.name not in shown]
    if remaining:
        lines.extend(
            [
                "",
                "#### Aggregate and additional metrics",
                "",
                "| Segment | Metric | Value |",
                "| --- | --- | --- |",
            ]
        )
        for metric in remaining:
            lines.append(
                f"| {short[metric.scope]} | {title(metric.name)} | {format_metric(metric)} |"
            )


def markdown(report: ResearchReport) -> str:
    evidence = report.evidence
    source = evidence.source
    short = {s.id: f"R{i}" for i, s in enumerate(evidence.scopes, 1)}
    readable_labels = {s.id: scope_label(s) for s in evidence.scopes}

    configured = evidence.configuration.get("strategies", [])
    if isinstance(configured, list):
        names = {
            item["id"]: item["name"]
            for item in configured
            if isinstance(item, dict) and "id" in item and "name" in item
        }
        for scope in evidence.scopes:
            if scope.role == "oos_summary":
                readable_labels[scope.id] = str(names.get(scope.label, scope.label)) + " (OOS)"

    def readable(text: str) -> str:
        for identifier, label in readable_labels.items():
            prefix = identifier + ": "
            if text.startswith(prefix):
                sentence = text[len(prefix) :]
                if sentence.startswith("fewer than"):
                    sentence = "there were " + sentence
                return f"For {label}, {sentence}"
        return text

    def references(ids: list[str]) -> str:
        scopes = {m.id: m.scope for m in evidence.metrics}
        return ", ".join(dict.fromkeys(short[scopes[i]] for i in ids))

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
    summary = (priority + [o for o in report.observations if o not in priority])[:6]
    lines.extend("- " + cell(readable(o.text)) for o in summary)
    lines.extend(
        [
            "",
            (
                "All observations describe supplied historical evidence; no future "
                "performance or live position is recommended."
            ),
            "",
            "## Research Configuration",
            "",
            "| Setting | Validated value (schema defaults applied) |",
            "| --- | --- |",
        ]
    )
    # Definitions and execution settings have their own readable sections.
    config = {
        k: v
        for k, v in evidence.configuration.items()
        if k not in ("strategies", "strategy", "base_strategy", "execution", "scenarios")
    }
    append_values(lines, config)
    lines.extend(
        [
            "",
            "## Strategies and Rules",
            "",
            "| Definition | Used by | Entry | Exit |",
            "| --- | --- | --- | --- |",
        ]
    )
    definitions: dict[str, tuple[str, list[str], dict[str, Any]]] = {}
    for scope in evidence.scopes:
        if scope.strategy is None:
            continue
        key = json.dumps(scope.strategy, sort_keys=True)
        if key not in definitions:
            definitions[key] = (f"S{len(definitions) + 1}", [], scope.strategy)
        labels = definitions[key][1]
        if scope.label not in labels:
            labels.append(scope.label)
    for identifier, labels, definition in definitions.values():
        if definition.get("name") == "RSI":
            legacy = LegacyCLISettings.model_validate(definition)
            entry = f"RSI({legacy.rsi_period}) < {legacy.entry_rsi:g}"
            exit_rule = f"RSI({legacy.rsi_period}) > {legacy.exit_rsi:g}"
        else:
            rule = RuleStrategy.model_validate(definition)
            entry, exit_rule = format_rule(rule.entry), format_rule(rule.exit)
        lines.append(
            f"| {identifier} | {cell(', '.join(labels))} | {cell(entry)} | {cell(exit_rule)} |"
        )
    lines.extend(
        [
            "",
            "## Historical Data and Evaluation Period",
            "",
            f"- Source: {cell(source.data_source or 'Unavailable')}",
            f"- Evaluation (UTC): {utc(source.evaluation_start)} to {utc(source.evaluation_end)}",
            f"- Boundary interpretation: {cell(source.evaluation_boundary_policy)}",
            "",
            "## Execution Assumptions",
            "",
            (
                "Fee is a per-side fraction; spread is the full bid/ask spread in bps; "
                "slippage is adverse per side in bps."
            ),
            (
                "OHLC prices are reference proxies. Reported spread/slippage costs are "
                "illustrative adjustments, not measured fills."
            ),
            "Signals execute at the following candle open; forced liquidation "
            "uses the segment's final close.",
            "",
            "| Applies to | Fee per side | Full spread | Slippage per side |",
            "| --- | --- | --- | --- |",
        ]
    )
    executions: dict[tuple[float, float, float], list[str]] = {}
    for scope in evidence.scopes:
        if scope.execution is not None:
            ex = scope.execution
            executions.setdefault((ex.fee_rate, ex.spread_bps, ex.slippage_bps), []).append(
                short[scope.id]
            )
    for (fee, spread, slip), refs in executions.items():
        applies = "All segments" if len(executions) == 1 else ", ".join(refs)
        lines.append(f"| {applies} | {fee:g} fraction | {spread:g} bps | {slip:g} bps |")
    lines.extend(
        [
            "",
            "## Performance Results",
            "",
            (
                "Numbers are rounded for display; JSON evidence retains source "
                "precision, full identifiers, source paths and contexts. All segments, "
                "negative results and undefined metrics are shown. R references "
                "identify rows below; boundaries are UTC and use the source boundary "
                "policy."
            ),
        ]
    )
    grouped: dict[str, list[EvidenceScope]] = OrderedDict()
    for scope in evidence.scopes:
        if scope.id.startswith("fold."):
            group = scope.id.split(".strategy.")[1].rsplit(".", 1)[0]
        elif scope.id.startswith("summary.strategy."):
            group = scope.id.split("summary.strategy.")[1].split(".")[0]
        else:
            group = "Research results"
        grouped.setdefault(group, []).append(scope)
    for group, scopes in grouped.items():
        lines.extend(
            [
                "",
                f"### {cell(scopes[0].label if group != 'Research results' else group)}",
                "",
                "| Reference | Segment | Start UTC | End UTC |",
                "| --- | --- | --- | --- |",
            ]
        )
        for scope in scopes:
            lines.append(
                f"| {short[scope.id]} | {cell(readable_labels[scope.id])} | "
                f"{utc(scope.start)} | {utc(scope.end)} |"
            )
        metric_tables(lines, scopes, evidence.metrics, short)
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
            "supplied, is a fold-endpoint index: not continuous execution with carried positions."
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
                    cell(readable(indexed[statement.observation_id].text)),
                    cell(statement.text),
                    "References: " + references(statement.evidence_ids),
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
    append_values(lines, evidence.reproducibility_metadata)
    if report.ai_metadata:
        lines.append(
            f"- AI requested model: {cell(report.ai_metadata.requested_model)}; "
            f"response model: {cell(report.ai_metadata.response_model)}"
        )
    return "\n".join(lines) + "\n"
