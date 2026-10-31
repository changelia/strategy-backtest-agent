"""Offline evidence-only HTML. No source execution, assets, scripts or schema changes."""

from __future__ import annotations

import base64
import hashlib
import math
import unicodedata
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from html import escape
from typing import Any

from pydantic import BaseModel

from strategy_backtest_agent.reports.inputs import (
    MAX_DEPTH,
    MAX_INPUT_BYTES,
    MAX_NODES,
    MAX_STRING,
    canonical_bytes,
    digest,
)
from strategy_backtest_agent.reports.models import EvidenceMetric, EvidenceScope, ResearchReport

RENDERER_VERSION = "visual-html/1"
MAX_HTML_BYTES = 64 * 1024 * 1024
PANEL_GROUPS = 25
CSS = """*{box-sizing:border-box}html{color:#172b3a;background:#eef2f4;
font:16px/1.55 system-ui,sans-serif}body{margin:0}main{max-width:1120px;margin:auto;
padding:40px 28px}header{border-top:5px solid #087e83;padding:24px 0 28px}
h1{font-size:clamp(1.8rem,4vw,2.8rem);line-height:1.15;margin:12px 0}h2{font-size:1.5rem;
margin-top:0}h3{font-size:1.15rem}p{max-width:85ch}.eyebrow{color:#08666b;
font-size:.8rem;font-weight:700;letter-spacing:.12em;text-transform:uppercase}
section{background:white;border:1px solid #d5dfe4;border-radius:10px;padding:24px;
margin:24px 0;min-width:0}.notice{border-left:4px solid #a76017;padding:12px 18px;
background:#fff6e6}.muted{color:#435969}.badge{display:inline-block;padding:3px 10px;
border:1px solid #8aa6af;border-radius:20px;font-size:.85rem}table{border-collapse:collapse;
width:100%;font-size:.875rem;table-layout:fixed}th,td{text-align:left;vertical-align:top;
padding:10px 12px;border-bottom:1px solid #dce4e8;overflow-wrap:anywhere}
th{color:#334e5f;background:#f0f5f7}caption{text-align:left;padding:12px 0;font-weight:600}
code{font-size:.85em;overflow-wrap:anywhere}dl{display:grid;grid-template-columns:180px 1fr;
gap:8px 16px}dt{font-weight:600}dd{margin:0;overflow-wrap:anywhere}svg{display:block;
width:100%;height:auto;min-width:0}svg text{font:12px system-ui,sans-serif;fill:#172b3a}
.axis{stroke:#738a98;stroke-width:1}.strategy{fill:#087e83}.benchmark{fill:#586aaf}
.drawdown{fill:#a54d25}.cost{fill:#7b548d}.zero{stroke:#172b3a;stroke-width:2}
figure{margin:20px 0}figcaption{font-weight:600}details{margin:16px 0}summary{cursor:pointer;
font-weight:600}.metrics th:nth-child(1){width:26%}.metrics th:nth-child(2){width:18%}
.metrics th:nth-child(3){width:12%}.metrics th:nth-child(4){width:44%}
footer{padding:24px 0;color:#435969;font-size:.85rem}li{overflow-wrap:anywhere}
@media(max-width:600px){main{padding:20px 12px}section{padding:16px 12px}th,td{padding:8px 5px;
font-size:.78rem}.chart-scroll{overflow-x:auto}svg{min-width:760px}dl{grid-template-columns:1fr;gap:4px}dd{margin-bottom:12px}}
@media print{html{background:white;font-size:10pt}main{max-width:none;padding:0}
section{border:0;border-top:1px solid #a6b8c2;border-radius:0;padding:16px 0}
figure,tr{break-inside:avoid}h2,h3,caption{break-after:avoid}thead{display:table-header-group}
details{display:block}summary{display:none}header{padding-top:12px}}
"""
STYLE_HASH = base64.b64encode(hashlib.sha256(CSS.encode()).digest()).decode()
CSP = (
    "default-src 'none'; script-src 'none'; connect-src 'none'; object-src 'none'; "
    "base-uri 'none'; form-action 'none'; style-src 'sha256-" + STYLE_HASH + "'"
)
TITLES = {
    "backtest": "Single strategy backtest",
    "comparison": "Strategy comparison",
    "validation": "Chronological Train / Test validation",
    "sensitivity": "Parameter sensitivity · Train only",
    "costs": "Execution-cost scenarios · Train only",
    "walk_forward": "Walk-Forward · independent portfolios",
}
CHART_UNITS = {
    "total_return": "%",
    "net_buy_and_hold": "%",
    "max_drawdown": "%",
    "return_difference": "pp",
    "fees": "quote_currency",
    "modeled_spread_cost": "quote_currency",
    "modeled_slippage_cost": "quote_currency",
}


def _bounded(value: Any, depth: int = 0, count: list[int] | None = None) -> None:
    count = [0] if count is None else count
    count[0] += 1
    if count[0] > MAX_NODES or depth > MAX_DEPTH:
        raise ValueError("HTML report exceeds node/depth limits")
    if isinstance(value, str):
        if len(value) > MAX_STRING or any(
            unicodedata.category(c) in {"Cf", "Cs"}
            or (ord(c) < 32 and c not in "\n\r\t")
            or ord(c) == 127
            for c in value
        ):
            raise ValueError("HTML report has oversized text or unsupported controls")
    elif isinstance(value, int | float):
        try:
            finite = math.isfinite(value)
        except OverflowError:
            finite = False
        if not finite:
            raise ValueError("HTML report numbers must be finite")
    elif isinstance(value, BaseModel):
        _bounded(vars(value), depth, count)
    elif isinstance(value, dict):
        for key, child in value.items():
            _bounded(key, depth + 1, count)
            _bounded(child, depth + 1, count)
    elif isinstance(value, list):
        for child in value:
            _bounded(child, depth + 1, count)


def validate_report(report: ResearchReport) -> ResearchReport:
    """Revalidate even model_copy/model_construct inputs; never assert native accounting."""
    _bounded(report)
    raw = report.model_dump(mode="python", warnings="error")
    checked = ResearchReport.model_validate(raw, strict=True)
    if len(canonical_bytes(checked.model_dump(mode="json"))) > MAX_INPUT_BYTES:
        raise ValueError("HTML report exceeds the normalized input byte limit")
    evidence = checked.evidence
    if digest(canonical_bytes(evidence.model_dump(mode="json"))) != checked.evidence_sha256:
        raise ValueError("HTML report evidence hash mismatch")

    def unique(values: Iterable[str]) -> set[str]:
        items = list(values)
        if any(not value for value in items) or len(set(items)) != len(items):
            raise ValueError("HTML report has empty/duplicate identifiers")
        return set(items)

    scopes = unique(s.id for s in evidence.scopes)
    metrics = unique(m.id for m in evidence.metrics)
    observation_ids = unique(o.id for o in checked.observations)
    unique(item.id for item in evidence.limitations)
    pairs: set[tuple[str, str]] = set()
    for metric in evidence.metrics:
        pair = (metric.scope, metric.name)
        if metric.scope not in scopes or pair in pairs:
            raise ValueError("HTML report has invalid metric scope/name references")
        pairs.add(pair)
        if metric.name in CHART_UNITS and metric.unit != CHART_UNITS[metric.name]:
            raise ValueError("HTML chart metric has a contradictory unit")
    for scope in evidence.scopes:
        if scope.start is not None and scope.end is not None and scope.start > scope.end:
            raise ValueError("HTML report scope boundaries are reversed")
    source = evidence.source
    if (
        source.evaluation_start is not None
        and source.evaluation_end is not None
        and source.evaluation_start > source.evaluation_end
    ):
        raise ValueError("HTML report source boundaries are reversed")
    for observation in checked.observations:
        if any(ref not in metrics for ref in observation.evidence_ids):
            raise ValueError("HTML report has unknown observation evidence references")
    if checked.ai_interpretation is not None:
        by_id = {m.id: m for m in evidence.metrics}
        for statement in checked.ai_interpretation.statements:
            if statement.observation_id not in observation_ids or any(
                ref not in metrics for ref in statement.evidence_ids
            ):
                raise ValueError("HTML report has unknown AI references")
            for number in statement.numeric_references:
                if number.evidence_id not in statement.evidence_ids:
                    raise ValueError("HTML report has unlinked AI numeric references")
                metric = by_id[number.evidence_id]
                if number.value != metric.value or number.unit != metric.unit:
                    raise ValueError("HTML report AI numeric reference contradicts evidence")
    return checked


def text(value: object) -> str:
    return escape(str(value), quote=True)


def utc(value: datetime | None) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z") if value else "Not supplied"


def value_text(value: object) -> str:
    if value is None:
        return "N/A (undefined)"
    return str(value)


class Document:
    def __init__(self) -> None:
        self.parts: list[str] = []
        self.size = 0

    def add(self, value: str) -> None:
        self.size += len(value.encode("utf-8"))
        if self.size > MAX_HTML_BYTES:
            raise ValueError("HTML output exceeds 64 MiB")
        self.parts.append(value)


def fields(value: Any, prefix: str = "") -> Iterable[tuple[str, str]]:
    """Flatten explanatory configuration into escaped table cells, not markup/JSON."""
    if isinstance(value, dict) and value:
        for key, child in value.items():
            yield from fields(child, f"{prefix}.{key}" if prefix else str(key))
    elif isinstance(value, list) and value:
        for index, child in enumerate(value):
            yield from fields(child, f"{prefix}[{index}]")
    else:
        yield prefix, value_text(value)


def field_table(doc: Document, title: str, value: Any) -> None:
    doc.add(
        f"<table><caption>{text(title)}</caption><thead><tr><th>Field</th>"
        "<th>Supplied value</th></tr></thead><tbody>\n"
    )
    for key, child in fields(value):
        doc.add(f"<tr><td>{text(key)}</td><td>{text(child)}</td></tr>\n")
    doc.add("</tbody></table>\n")


def paragraphs(doc: Document, title: str, items: Iterable[str]) -> None:
    doc.add(f"<h3>{text(title)}</h3><ul>\n")
    found = False
    for item in items:
        found = True
        doc.add(f"<li>{text(item)}</li>\n")
    if not found:
        doc.add("<li>None supplied.</li>\n")
    doc.add("</ul>\n")


def charts(
    doc: Document,
    scopes: list[tuple[int, EvidenceScope]],
    by_scope: dict[str, list[EvidenceMetric]],
    names: tuple[str, ...],
    title: str,
    unit: str,
    panel_id: int,
) -> int:
    groups = [
        (number, scope)
        for number, scope in scopes
        if any(m.name in names for m in by_scope[scope.id])
    ]
    if not groups:
        return panel_id
    values = [
        m.value
        for _, s in groups
        for m in by_scope[s.id]
        if m.name in names and m.value is not None
    ]
    # Normalize before multiplying so extreme but finite input cannot overflow SVG geometry.
    scale = max((abs(v) for v in values), default=0) or 1
    for offset in range(0, len(groups), PANEL_GROUPS):
        chunk = groups[offset : offset + PANEL_GROUPS]
        panel_id += 1
        rows = [
            (number, m)
            for number, s in chunk
            for name in names
            for m in by_scope[s.id]
            if m.name == name
        ]
        height = 50 + len(rows) * 28
        doc.add(
            f"<figure><figcaption>{text(title)} · panel {panel_id}</figcaption>"
            '<div class="chart-scroll">'
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 {height}" '
            f'role="img" aria-labelledby="chart-{panel_id}">'
            f'<title id="chart-{panel_id}">{text(title)} ({text(unit)}). '
            "R numbers refer to the complete evidence tables below.</title>"
            "<desc>Zero is the vertical center line. Left is negative, right positive. "
            "Values are supplied scalar metrics, not a time series.</desc>"
            f'<line class="axis" x1="430" x2="430" y1="20" y2="{height - 10}"/>'
            '<text x="430" y="14" text-anchor="middle">0</text>'
        )
        for index, (number, metric) in enumerate(rows):
            y = 42 + index * 28
            label = {
                "total_return": "Strategy net",
                "net_buy_and_hold": "Net Buy & Hold",
                "max_drawdown": "Max drawdown (scalar)",
                "return_difference": "Baseline difference",
                "fees": "Fees",
                "modeled_spread_cost": "Modeled spread",
                "modeled_slippage_cost": "Modeled slippage",
            }[metric.name]
            doc.add(f'<text x="8" y="{y}">R{number} · {text(label)}</text>')
            if metric.value is not None:
                width = abs(metric.value / scale) * 160
                x = 430 - width if metric.value < 0 else 430
                css = (
                    "benchmark"
                    if metric.name == "net_buy_and_hold"
                    else "drawdown"
                    if metric.name == "max_drawdown"
                    else "cost"
                    if metric.unit == "quote_currency"
                    else "strategy"
                )
                doc.add(
                    f'<rect class="{css}" x="{x:.3f}" y="{y - 12}" '
                    f'width="{width:.3f}" height="14">'
                    f"<title>{text(metric.id)}: {text(value_text(metric.value))} "
                    f"{text(unit)}</title></rect>"
                )
                if metric.value == 0:
                    doc.add(f'<line class="zero" x1="430" x2="430" y1="{y - 12}" y2="{y + 2}"/>')
            displayed = "N/A (undefined)" if metric.value is None else f"{metric.value:.4g} {unit}"
            doc.add(f'<text x="610" y="{y}">{text(displayed)}</text>')
        doc.add(
            '</svg></div><p class="muted">Linear magnitude scale shared across these panels; '
            f"maximum magnitude {text(scale)} {text(unit)}. Null values have no mark. "
            "Exact values, labels, units and source paths are in the evidence "
            "tables.</p></figure>\n"
        )
    return panel_id


def html(report: ResearchReport) -> str:
    """Render a bounded, revalidated report; return one deterministic UTF-8 document."""
    report = validate_report(report)
    evidence = report.evidence
    source = evidence.source
    doc = Document()
    doc.add(
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n'
        f'<meta http-equiv="Content-Security-Policy" content="{text(CSP)}">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<meta name="generator" content="{RENDERER_VERSION}">\n'
        "<title>Historical Strategy Research Report</title>\n"
        f"<style>{CSS}</style></head><body><main>\n<header>"
        '<div class="eyebrow">Strategy Backtest · Historical research</div>'
        f"<h1>{text(TITLES[source.research_type])}</h1>"
        f'<span class="badge">{text(report.status)}</span>'
        "<p>Standalone evidence report · offline · no scripts</p></header>\n"
        '<p class="notice">Historical results do not predict future returns. '
        "These charts show recorded scalar metrics, not equity or drawdown curves.</p>\n"
    )
    doc.add("<section><h2>Source and provenance</h2><dl>")
    for key, value in source.model_dump(mode="python").items():
        display = utc(value) if isinstance(value, datetime) else value_text(value)
        doc.add(f"<dt>{text(key)}</dt><dd>{text(display)}</dd>")
    doc.add(
        f"<dt>Evidence SHA256</dt><dd><code>{text(report.evidence_sha256)}</code></dd>"
        f"<dt>Report schema / generator</dt><dd>{text(report.report_schema_version)} / "
        f"{text(report.generator_version)}</dd><dt>HTML renderer</dt><dd>{RENDERER_VERSION}</dd>"
        "</dl><p>Requested/source boundaries follow the policy above; actual UTC "
        "half-open segment boundaries appear in each evidence scope below. Missing "
        "metadata is not inferred. Typed normalized evidence is structurally checked; "
        "native accounting and original prices cannot be verified without native "
        "data.</p></section>\n"
    )
    doc.add("<section><h2>Chart capabilities</h2>")
    field_table(
        doc,
        "Available and deferred visuals",
        {
            "Available": (
                "Scalar net strategy/benchmark returns and maximum drawdown; complete "
                "numeric tables."
            ),
            "Costs": (
                "Train-only scenario differences (pp) and modeled cost components "
                "(quote currency), when supplied."
            ),
            "Unavailable curves": (
                "No retained equity, drawdown or benchmark time series. No "
                "reconstruction from trades or scalars."
            ),
            "Deferred": (
                "Heatmaps, fold timelines, stitched-index plots and native grid "
                "layouts are not rendered."
            ),
            "Independent portfolios": (
                "Train/Test/fold scopes reset capital and positions. Endpoint indices "
                "are not continuous portfolios."
            ),
            "Missing values": (
                "N/A means undefined or not supplied; it is not zero. No ranking or "
                "optimization is performed."
            ),
        },
    )
    doc.add("</section>\n<section><h2>Configuration and reproducibility</h2>")
    field_table(doc, "Supplied configuration", evidence.configuration)
    field_table(doc, "Reproducibility metadata", evidence.reproducibility_metadata)
    doc.add(
        "</section>\n<section><h2>Scalar comparisons</h2>"
        "<p>Each R number identifies an independent scope below. Percent (%) and "
        "percentage-point differences (pp) use separate panels. Costs are illustrative "
        "fill attributions, not measured market spreads or extra charges to subtract "
        "from already net performance.</p>"
    )
    by_scope: dict[str, list[EvidenceMetric]] = defaultdict(list)
    for metric in evidence.metrics:
        by_scope[metric.scope].append(metric)
    scopes = list(enumerate(evidence.scopes, 1))
    panel = charts(
        doc,
        scopes,
        by_scope,
        ("total_return", "net_buy_and_hold"),
        "Strategy versus net benchmark return",
        "%",
        0,
    )
    panel = charts(
        doc, scopes, by_scope, ("max_drawdown",), "Maximum drawdown · scalar", "%", panel
    )
    cost_scopes = [(n, s) for n, s in scopes if s.role == "scenario_train"]
    panel = charts(
        doc,
        cost_scopes,
        by_scope,
        ("return_difference",),
        "Train-only scenario minus declared baseline",
        "pp",
        panel,
    )
    charts(
        doc,
        cost_scopes,
        by_scope,
        ("fees", "modeled_spread_cost", "modeled_slippage_cost"),
        "Train-only modeled cost components",
        "quote_currency",
        panel,
    )
    if not any(m.name in CHART_UNITS for m in evidence.metrics):
        doc.add("<p>No supported chart metrics supplied. Complete tables remain below.</p>")
    doc.add("</section>\n")
    for number, scope in scopes:
        doc.add(
            f"<section><h2>R{number} · {text(scope.label)}</h2>"
            f"<p><code>{text(scope.id)}</code> · {text(scope.role)}</p>"
            f"<p>Actual scope UTC: {text(utc(scope.start))} → {text(utc(scope.end))} "
            "(half-open segment; index points have equal boundaries).</p>"
        )
        if scope.role in ("variant_train", "scenario_train"):
            doc.add(
                '<p class="notice">Train only. Test is reserved and not evaluated. '
                "Inspect trade counts; zero or few trades do not establish stability.</p>"
            )
        if scope.role in ("oos_summary", "stitched_index"):
            doc.add(
                '<p class="notice">Independent Test-fold statistics / endpoint data. '
                "No continuous portfolio, intrafold path or pooled drawdown is implied.</p>"
            )
        if scope.strategy is not None or scope.execution is not None:
            field_table(
                doc,
                "Scope strategy and execution assumptions",
                {
                    "strategy": scope.strategy,
                    "execution": scope.execution.model_dump()
                    if scope.execution is not None
                    else None,
                },
            )
        doc.add(
            '<table class="metrics"><caption>Complete numeric evidence · '
            f"R{number}</caption><thead><tr><th>Metric / ID</th><th>Exact value</th>"
            "<th>Unit</th><th>Source path / context</th></tr></thead><tbody>\n"
        )
        for metric in by_scope[scope.id]:
            doc.add(
                f"<tr><td>{text(metric.name)}<br><code>{text(metric.id)}</code></td>"
                f"<td>{text(value_text(metric.value))}</td><td>{text(metric.unit)}</td>"
                f"<td><code>{text(metric.source_path)}</code><br>{text(metric.context)}</td></tr>\n"
            )
        doc.add("</tbody></table></section>\n")
    doc.add("<section><h2>Methodology and limitations</h2>")
    paragraphs(doc, "Methodology", evidence.methodology)
    paragraphs(doc, "Limitations", (f"{item.id}: {item.text}" for item in evidence.limitations))
    paragraphs(doc, "Warnings", report.warnings)
    paragraphs(doc, "Source notes · unverified supplied content", evidence.source_notes)
    paragraphs(
        doc,
        "Evidence observations",
        (f"{o.id}: {o.text} [{', '.join(o.evidence_ids)}]" for o in report.observations),
    )
    if report.ai_interpretation is not None:
        doc.add("<h3>Previously supplied AI interpretation · not generated by HTML rendering</h3>")
        field_table(
            doc,
            "Supplied AI metadata",
            report.ai_metadata.model_dump() if report.ai_metadata else {},
        )
        for statement in report.ai_interpretation.statements:
            doc.add(
                f"<p>{text(statement.text)}<br>Evidence: "
                f"{text(', '.join(statement.evidence_ids))}</p>"
            )
        paragraphs(
            doc, "Supplied AI research-question codes", report.ai_interpretation.research_questions
        )
    doc.add(
        "</section><footer>Historical Strategy Research Report · visual-html/1 · "
        "One self-contained document. No external assets or requests.</footer>\n"
        "</main></body></html>\n"
    )
    return "".join(doc.parts)
