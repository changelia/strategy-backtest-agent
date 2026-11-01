"""Opt-in synthetic HTML fixtures for browser inspection; no application network."""

import argparse
import json
import sys
from pathlib import Path

from strategy_backtest_agent import BacktestClient
from strategy_backtest_agent.reports.evidence import build_report
from strategy_backtest_agent.reports.inputs import canonical_bytes, digest


def generate(work: Path) -> None:
    checkout = Path(__file__).resolve().parents[1]
    work = work.resolve()
    if work.is_relative_to(checkout):
        raise ValueError("Browser fixtures must stay outside the checkout")
    work.mkdir(parents=True, exist_ok=True)
    if list(work.iterdir()):
        raise ValueError("Use a fresh browser-fixture directory")

    def deny(event: str, args: object) -> None:
        if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
            raise RuntimeError("Browser fixture generation denies application network")

    sys.addaudithook(deny)
    client = BacktestClient(api_key="")
    root = checkout / "tests/fixtures/reports/v0.9.0"
    for kind in ("backtest", "comparison", "validation", "sensitivity", "costs", "walk_forward"):
        client.report(root / f"{kind}.json", format="html", output=work / f"{kind}.html")
    report = build_report((root / "comparison.json").read_bytes())
    report.evidence.source_notes.append(
        "Synthetic typed-report edge fixture; native accounting is not asserted."
    )
    attack = 'Long <script>alert(1)</script> label with "quotes" and CSS url(https://evil.test) '
    report.evidence.scopes[0] = report.evidence.scopes[0].model_copy(update={"label": attack * 30})
    for i, metric in enumerate(report.evidence.metrics):
        if metric.name in ("total_return", "net_buy_and_hold", "max_drawdown"):
            report.evidence.metrics[i] = metric.model_copy(update={"value": -12.0})
        elif metric.name in ("profit_factor", "win_rate"):
            report.evidence.metrics[i] = metric.model_copy(update={"value": None})
        elif metric.name == "completed_trades":
            report.evidence.metrics[i] = metric.model_copy(update={"value": 0})
    report = report.model_copy(
        update={"evidence_sha256": digest(canonical_bytes(report.evidence.model_dump(mode="json")))}
    )
    client.report(report, format="html", output=work / "edge.html")
    scopes, metrics = [], []
    for i in range(26):
        scope = report.evidence.scopes[1].model_copy(update={"id": f"scope-{i}"})
        scopes.append(scope)
        metric = next(m for m in report.evidence.metrics if m.name == "total_return")
        metrics.append(metric.model_copy(update={"id": f"metric-{i}", "scope": scope.id}))
    expanded = report.model_copy(
        update={
            "observations": [],
            "evidence": report.evidence.model_copy(update={"scopes": scopes, "metrics": metrics}),
        }
    )
    expanded = expanded.model_copy(
        update={
            "evidence_sha256": digest(canonical_bytes(expanded.evidence.model_dump(mode="json")))
        }
    )
    client.report(expanded, format="html", output=work / "panels.html")
    (work / "fixtures.json").write_text(
        json.dumps({"synthetic": True, "application_network_attempts": 0})
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    generate(parser.parse_args().work)
