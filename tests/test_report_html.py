"""Evidence agreement, bounded typed input, deterministic HTML and a strict DOM allowlist."""

import hashlib
import json
import math
import socket
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

from strategy_backtest_agent.reports.evidence import build_report
from strategy_backtest_agent.reports.html import CSS, STYLE_HASH, html
from strategy_backtest_agent.reports.inputs import canonical_bytes, digest
from strategy_backtest_agent.reports.models import ResearchReport

FIXTURES = Path(__file__).parent / "fixtures/reports"
KINDS = ("backtest", "comparison", "validation", "sensitivity", "costs", "walk_forward")


class DOM(HTMLParser):
    def __init__(self, content: str) -> None:
        super().__init__(convert_charrefs=True)
        self.nodes: list[tuple[str, dict[str, str | None]]] = []
        self.data: list[str] = []
        self.cells: list[str] = []
        self.current_cell: list[str] | None = None
        self.feed(content)
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.nodes.append((tag, dict(attrs)))
        if tag == "td":
            self.current_cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self.current_cell is not None:
            self.cells.append("".join(self.current_cell))
            self.current_cell = None

    def handle_data(self, data: str) -> None:
        self.data.append(data)
        if self.current_cell is not None:
            self.current_cell.append(data)


def assert_safe(dom: DOM) -> None:
    allowed = {
        "html",
        "head",
        "meta",
        "title",
        "style",
        "body",
        "main",
        "header",
        "div",
        "h1",
        "h2",
        "h3",
        "p",
        "span",
        "section",
        "dl",
        "dt",
        "dd",
        "code",
        "table",
        "caption",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
        "figure",
        "figcaption",
        "svg",
        "desc",
        "line",
        "rect",
        "text",
        "br",
        "ul",
        "li",
        "footer",
    }
    ids = []
    for tag, attrs in dom.nodes:
        assert tag in allowed, tag
        assert not any(k.startswith("on") or k in {"href", "src", "style", "action"} for k in attrs)
        if "id" in attrs:
            ids.append(attrs["id"])
            assert str(attrs["id"]).startswith("chart-")
        if tag in {"rect", "line", "text"}:
            for key in ("x", "y", "x1", "x2", "y1", "y2", "width", "height"):
                if key in attrs:
                    assert math.isfinite(float(str(attrs[key])))
        if tag == "meta" and attrs.get("http-equiv") == "Content-Security-Policy":
            policy = str(attrs["content"])
            assert "script-src 'none'" in policy and "unsafe-" not in policy
            assert f"style-src 'sha256-{STYLE_HASH}'" in policy
    assert len(ids) == len(set(ids))
    assert hashlib.sha256(CSS.encode()).digest() == __import__("base64").b64decode(STYLE_HASH)


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("HTML renderer must not access the network")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "sendto", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)


@pytest.fixture
def report() -> ResearchReport:
    return build_report((FIXTURES / "v0.9.0/comparison.json").read_bytes())


def rehash(report: ResearchReport) -> ResearchReport:
    return report.model_copy(
        update={"evidence_sha256": digest(canonical_bytes(report.evidence.model_dump(mode="json")))}
    )


@pytest.mark.parametrize("version", ["v0.8.0", "v0.9.0"])
@pytest.mark.parametrize("kind", KINDS)
def test_all_modes_legacy_complete_evidence_and_repeatability(version: str, kind: str) -> None:
    report = build_report((FIXTURES / version / f"{kind}.json").read_bytes())
    original = report.model_dump_json()
    rendered = html(report)
    assert rendered == html(report) and rendered.endswith("\n") and "\r" not in rendered
    assert report.model_dump_json() == original
    dom = DOM(rendered)
    assert_safe(dom)
    for metric in report.evidence.metrics:
        assert metric.name + metric.id in dom.cells
        assert (
            str(metric.value) in dom.cells
            if metric.value is not None
            else "N/A (undefined)" in dom.cells
        )
        assert metric.unit in dom.cells
        assert metric.source_path + metric.context in dom.cells
    assert report.evidence_sha256 in "".join(dom.data)
    assert report.evidence.source.input_content_sha256 in "".join(dom.data)
    assert "No retained equity" in "".join(dom.data)
    if kind == "costs":
        assert "Train-only scenario minus declared baseline" in rendered
        assert "Train-only modeled cost components" in rendered
    if kind == "walk_forward":
        assert "No continuous portfolio" in rendered


@pytest.mark.parametrize(
    "attack",
    [
        '<script>alert("x")</script><svg onload="alert(1)">',
        '</style><img src="https://evil.test" onerror="alert(1)">',
        '" autofocus onfocus=alert(1) x="',
        "javascript:alert(1); data:text/html,<script>evil</script>",
        'body{background:url(https://evil.test)} @import "evil";',
        "Long label " * 600,
    ],
)
def test_hostile_strings_are_only_text(report: ResearchReport, attack: str) -> None:
    report.evidence.scopes[0] = report.evidence.scopes[0].model_copy(update={"label": attack})
    report.evidence.source_notes.append(attack)
    report.evidence.configuration["hostile"] = attack
    report = rehash(report)
    rendered = html(report)
    dom = DOM(rendered)
    assert_safe(dom)
    assert attack in "".join(dom.data)
    assert report.evidence.scopes[0].label in dom.cells or attack in "".join(dom.data)


@pytest.mark.parametrize(
    "change",
    [
        "nan",
        "infinity",
        "huge_int",
        "duplicate_scope",
        "duplicate_metric",
        "pair",
        "scope_ref",
        "observation_ref",
        "hash",
        "unit",
        "reversed",
        "source_reversed",
        "oversized",
        "depth",
        "nodes",
        "control",
        "copy_type",
    ],
)
def test_invalid_typed_reports_fail_safely(
    report: ResearchReport, change: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import strategy_backtest_agent.reports.html as module

    if change in ("nan", "infinity", "huge_int"):
        value = {"nan": float("nan"), "infinity": float("inf"), "huge_int": 10**400}[change]
        report.evidence.metrics[0] = report.evidence.metrics[0].model_copy(update={"value": value})
    elif change == "duplicate_scope":
        report.evidence.scopes.append(report.evidence.scopes[0])
    elif change == "duplicate_metric":
        report.evidence.metrics.append(report.evidence.metrics[0])
    elif change == "pair":
        report.evidence.metrics.append(
            report.evidence.metrics[0].model_copy(update={"id": "other"})
        )
    elif change == "scope_ref":
        report.evidence.metrics[0] = report.evidence.metrics[0].model_copy(
            update={"scope": "absent"}
        )
    elif change == "observation_ref":
        report.observations[0].evidence_ids.append("absent")
    elif change == "hash":
        report = report.model_copy(update={"evidence_sha256": "0" * 64})
    elif change == "unit":
        i = next(i for i, m in enumerate(report.evidence.metrics) if m.name == "total_return")
        report.evidence.metrics[i] = report.evidence.metrics[i].model_copy(update={"unit": "pp"})
    elif change == "reversed":
        s = report.evidence.scopes[0]
        report.evidence.scopes[0] = s.model_copy(update={"start": s.end, "end": s.start})
    elif change == "source_reversed":
        source = report.evidence.source
        report = report.model_copy(
            update={
                "evidence": report.evidence.model_copy(
                    update={
                        "source": source.model_copy(
                            update={
                                "evaluation_start": source.evaluation_end,
                                "evaluation_end": source.evaluation_start,
                            }
                        )
                    }
                )
            }
        )
    elif change == "oversized":
        report.evidence.source_notes.append("x" * 8193)
    elif change == "depth":
        value_dict: dict[str, Any] = {}
        for _ in range(35):
            value_dict = {"nested": value_dict}
        report.evidence.configuration["nested"] = value_dict
    elif change == "nodes":
        monkeypatch.setattr(module, "MAX_NODES", 5)
    elif change == "control":
        report.evidence.source_notes.append("unsafe\u202e")
    elif change == "copy_type":
        report = report.model_copy(update={"status": "not-a-status"})
    if change not in ("nan", "infinity", "huge_int", "copy_type", "hash"):
        report = rehash(report)
    with pytest.raises(ValueError):
        html(report)


@pytest.mark.parametrize("value", [0, -12.5, -1e308, 1e308, None])
def test_zero_negative_constant_and_extreme_geometry(
    report: ResearchReport, value: float | None
) -> None:
    for i, metric in enumerate(report.evidence.metrics):
        if metric.name in ("total_return", "net_buy_and_hold", "max_drawdown"):
            report.evidence.metrics[i] = metric.model_copy(update={"value": value})
    rendered = html(rehash(report))
    assert_safe(DOM(rendered))
    if value == 0:
        assert 'class="zero"' in rendered
    elif value is None:
        assert "<rect" not in rendered and "N/A (undefined)" in rendered


def test_chart_rectangles_agree_with_values(report: ResearchReport) -> None:
    for i, metric in enumerate(report.evidence.metrics):
        if metric.name == "total_return":
            report.evidence.metrics[i] = metric.model_copy(update={"value": -20.0})
        elif metric.name == "net_buy_and_hold":
            report.evidence.metrics[i] = metric.model_copy(update={"value": 10.0})
    rects = [attrs for tag, attrs in DOM(html(rehash(report))).nodes if tag == "rect"]
    assert rects[0]["width"] == "160.000" and rects[0]["x"] == "270.000"
    assert rects[1]["width"] == "80.000" and rects[1]["x"] == "430.000"


def test_panel_splitting_and_bounds(
    report: ResearchReport, monkeypatch: pytest.MonkeyPatch
) -> None:
    import strategy_backtest_agent.reports.html as module

    scopes, metrics = [], []
    for i in range(26):
        scope = report.evidence.scopes[0].model_copy(update={"id": f"scope-{i}"})
        scopes.append(scope)
        metrics.append(
            report.evidence.metrics[2].model_copy(
                update={"id": f"metric-{i}", "scope": scope.id, "name": "total_return", "unit": "%"}
            )
        )
    expanded = report.model_copy(
        update={
            "observations": [],
            "evidence": report.evidence.model_copy(update={"scopes": scopes, "metrics": metrics}),
        }
    )
    rendered = html(rehash(expanded))
    assert rendered.count("<svg ") == 2
    assert "R26" in rendered and len([n for n, a in DOM(rendered).nodes if n == "rect"]) == 26
    monkeypatch.setattr(module, "MAX_HTML_BYTES", len(html(report).encode()) - 1)
    with pytest.raises(ValueError, match="64 MiB"):
        html(report)
    monkeypatch.setattr(module, "MAX_INPUT_BYTES", 1)
    with pytest.raises(ValueError, match="input byte limit"):
        html(report)


def test_no_trade_and_null_metrics(native_results: dict[str, dict[str, Any]]) -> None:
    r = build_report(json.dumps(native_results["comparison"]).encode())
    assert any(m.name == "completed_trades" and m.value == 0 for m in r.evidence.metrics)
    assert "N/A (undefined)" in html(r)


def supplied_ai(report: ResearchReport) -> ResearchReport:
    from strategy_backtest_agent.reports.models import (
        AIInterpretation,
        AIMetadata,
        AINumericReference,
        AIStatement,
    )

    observation = report.observations[0]
    metric = next(m for m in report.evidence.metrics if m.id == observation.evidence_ids[0])
    return report.model_copy(
        update={
            "status": "ai_accepted",
            "ai_metadata": AIMetadata(requested_model="offline", response_model="recorded"),
            "ai_interpretation": AIInterpretation(
                statements=[
                    AIStatement(
                        observation_id=observation.id,
                        explanation_code="historical_context",
                        text="Previously supplied <script>evil()</script>",
                        evidence_ids=observation.evidence_ids,
                        numeric_references=[
                            AINumericReference(
                                evidence_id=metric.id, value=metric.value, unit=metric.unit
                            )
                        ],
                    )
                ],
                research_questions=["unseen_history"],
            ),
        }
    )


def test_cached_ai_is_labelled_escaped_and_referenced(report: ResearchReport) -> None:
    cached = supplied_ai(report)
    rendered = html(cached)
    assert "Previously supplied &lt;script&gt;" in rendered
    assert "not generated by HTML rendering" in rendered
    assert_safe(DOM(rendered))
    assert rendered == html(cached)


@pytest.mark.parametrize("change", ["observation", "evidence", "unlinked", "value", "unit"])
def test_cached_ai_bad_references_rejected(report: ResearchReport, change: str) -> None:
    cached = supplied_ai(report)
    assert cached.ai_interpretation is not None
    statement = cached.ai_interpretation.statements[0]
    if change == "observation":
        statement = statement.model_copy(update={"observation_id": "absent"})
    elif change == "evidence":
        statement = statement.model_copy(update={"evidence_ids": ["absent"]})
    else:
        number = statement.numeric_references[0]
        update: dict[str, Any] = (
            {"evidence_id": "absent"}
            if change == "unlinked"
            else ({"value": 987654321} if change == "value" else {"unit": "count"})
        )
        statement = statement.model_copy(
            update={"numeric_references": [number.model_copy(update=update)]}
        )
    cached.ai_interpretation.statements[0] = statement
    with pytest.raises(ValueError):
        html(cached)
