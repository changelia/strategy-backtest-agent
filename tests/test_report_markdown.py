"""Readable Markdown snapshots, complete metrics and adversarial metadata."""

import hashlib
import json
from pathlib import Path

import pytest

from strategy_backtest_agent.reports.evidence import build_report
from strategy_backtest_agent.reports.render import cell, format_metric, markdown, utc
from strategy_backtest_agent.rules.formatter import format_rule
from strategy_backtest_agent.rules.models import RuleStrategy

FIXTURES = Path(__file__).parent / "fixtures" / "reports"
KINDS = ("backtest", "comparison", "validation", "sensitivity", "costs", "walk_forward")


@pytest.mark.parametrize("kind", KINDS)
def test_readable_markdown_snapshot_and_complete_evidence(kind: str) -> None:
    source = (FIXTURES / "v0.9.0" / f"{kind}.json").read_bytes()
    report = build_report(source)
    original_json = report.model_dump_json()
    text = markdown(report)
    assert text == (FIXTURES / "markdown" / f"{kind}.md").read_text()
    assert text == markdown(report)
    assert report.model_dump_json() == original_json
    assert hashlib.sha256(original_json.encode()).hexdigest() == JSON_HASHES[kind]
    assert "&#58;" not in text and "&#95;" not in text and "&#34;" not in text
    assert '"conditions"' not in text and '"strategy"' not in text
    summary = text.split("## Executive Summary\n", 1)[1].split("\n## ", 1)[0]
    assert "Evidence:" not in summary
    assert not any(s.id in summary for s in report.evidence.scopes)
    for index, scope in enumerate(report.evidence.scopes, 1):
        assert f"| R{index} |" in text
        assert utc(scope.start) in text and utc(scope.end) in text
    for metric in report.evidence.metrics:
        if metric.name not in ("fee_per_side", "full_spread", "slippage_per_side"):
            assert format_metric(metric) in text, metric.id
    for limitation in report.evidence.limitations:
        assert cell(limitation.text) in text
    for note in report.evidence.source_notes:
        assert cell(note) in text
    strategies = text.split("## Strategies and Rules\n", 1)[1].split("\n## ", 1)[0]
    definitions = {
        json.dumps(s.strategy, sort_keys=True)
        for s in report.evidence.scopes
        if s.strategy is not None
    }
    assert len([line for line in strategies.splitlines() if line.startswith("| S")]) == len(
        definitions
    )
    for definition in definitions:
        rule = RuleStrategy.model_validate_json(definition)
        assert cell(format_rule(rule.entry)) in strategies
        assert cell(format_rule(rule.exit)) in strategies


@pytest.mark.parametrize(
    "name",
    [
        '[owned](javascript:alert(1)) | <script>alert("x")</script>',
        "**bold** _emphasis_ `code` ``` # Forged ![img](https://evil.test)",
        'RSI_14: "30/70" \\ | <img src=x onerror=alert(1)>',
        "normal\u202e# hidden\u2066name",
    ],
)
def test_strategy_names_cannot_inject_structure(name: str) -> None:
    raw = json.loads((FIXTURES / "v0.9.0" / "comparison.json").read_bytes())
    raw["configuration"]["strategies"][0]["name"] = name
    raw["results"][0]["name"] = name
    original = markdown(build_report((FIXTURES / "v0.9.0" / "comparison.json").read_bytes()))
    rendered = markdown(build_report(json.dumps(raw).encode()))
    assert [line for line in rendered.splitlines() if line.startswith("#")] == [
        line for line in original.splitlines() if line.startswith("#")
    ]
    assert cell(name) in rendered
    assert "<script>" not in rendered and "<img " not in rendered
    assert "[owned](" not in rendered and "![img](" not in rendered
    assert "```" not in rendered and "\u202e" not in rendered


def test_normal_punctuation_is_readable_and_controls_are_removed() -> None:
    assert cell('RSI_14: "30/70" (UTC); fee=0.001') == 'RSI\\_14: "30/70" (UTC); fee=0.001'
    assert cell("safe\n# forged\t<script>\u202e") == "safe \\# forged &lt;script&gt;"


def test_walk_forward_preserves_all_train_test_rows_and_negative_metrics() -> None:
    report = build_report((FIXTURES / "v0.9.0" / "walk_forward.json").read_bytes())
    text = markdown(report)
    for i, scope in enumerate(report.evidence.scopes, 1):
        if scope.role not in ("train", "test"):
            continue
        returns = [line for line in text.splitlines() if line.startswith(f"| R{i} |")]
        assert len(returns) == 4  # boundary, returns, trades, execution costs
        for metric in report.evidence.metrics:
            if metric.scope == scope.id and metric.name in (
                "total_return",
                "net_buy_and_hold",
                "excess_return",
                "max_drawdown",
            ):
                assert format_metric(metric) in returns[1]
    assert "N/A (undefined)" in text
    assert "not continuous execution with carried positions" in text


JSON_HASHES: dict[str, str] = {
    "backtest": "4d8c29e8c1d37c67f7133c3faeaa44d5f7a96c879116e1b4013e9943136f6f28",
    "comparison": "7b62d4a01f969b38bf759642d3a85aaad1b430aa132c70df8a03cb79eae5e1fa",
    "costs": "c17815b9e6d061383aa47468022ceeb8fa1c8583ca76f0d2b98128286d4ba3e4",
    "sensitivity": "91f899a4491c8919cee18151c867096b47910dabd5e7256862a7a7458f933532",
    "validation": "19fe35613c794c62355a6bdb8adb7a9718c5740c9892469907f60f629ec02a08",
    "walk_forward": "933a197cbb07bf29c494d684b433b10a110307321fb9ce67b0e51e16a1334f66",
}


@pytest.mark.parametrize("index", range(3))
def test_advanced_and_nested_rules_use_existing_readable_formatter(index: int) -> None:
    from test_advanced_research import SPECS, history, rule_for, settings
    from test_comparison_engine import named

    from strategy_backtest_agent.comparison.engine import run_comparison
    from strategy_backtest_agent.comparison.models import ComparisonConfig
    from strategy_backtest_agent.rules.evaluator import warmup_count

    original = rule_for(SPECS[index])
    rule = RuleStrategy.model_validate(
        {
            "entry": {"type": "and", "conditions": [original.entry, original.exit]},
            "exit": original.exit,
        }
    )
    config = ComparisonConfig.model_validate(
        {**settings(rule), "strategies": [named("a", rule), named("b", rule)]}
    )
    source = run_comparison(history(warmup_count(rule)), config).model_dump_json().encode()
    rendered = markdown(build_report(source))
    assert cell(format_rule(rule.entry)) in rendered
    strategies = rendered.split("## Strategies and Rules\n", 1)[1].split("\n## ", 1)[0]
    assert strategies.count("| S1 |") == 1 and "| S2 |" not in strategies
    assert " AND " in strategies and '"conditions"' not in rendered
