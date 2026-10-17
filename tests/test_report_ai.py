"""Mocked SDK interpretations and adversarial grounding/fallback checks."""

import copy
import json
from typing import Any

import httpx2
import pytest
from test_ai_parser import install_transport, response_payload
from test_reports import encode

from strategy_backtest_agent.reports.ai import EXPLANATIONS, interpret
from strategy_backtest_agent.reports.evidence import build_report
from strategy_backtest_agent.reports.models import ResearchReport
from strategy_backtest_agent.reports.render import markdown


def output(report: ResearchReport) -> dict[str, Any]:
    observation = report.observations[0]
    metric = next(m for m in report.evidence.metrics if m.id == observation.evidence_ids[0])
    return {
        "statements": [
            {
                "observation_id": observation.id,
                "explanation_code": "historical_context",
                "text": EXPLANATIONS["historical_context"],
                "evidence_ids": observation.evidence_ids,
                "numeric_references": [
                    {"evidence_id": metric.id, "value": metric.value, "unit": metric.unit}
                ],
            }
        ],
        "research_questions": ["unseen_history"],
    }


def test_actual_sdk_success_receives_only_bounded_evidence(
    native_results: dict[str, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    report = build_report(encode(native_results["backtest"]))
    payload = output(report)
    calls = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        body = json.loads(request.content)
        assert body["store"] is False and "tools" not in body
        assert body["text"]["format"]["strict"] is True
        evidence = json.loads(body["input"])
        assert set(evidence) == {
            "observations",
            "metrics",
            "approved_explanations",
            "research_questions",
        }
        assert len(evidence["observations"]) <= 8
        assert "trades" not in evidence and "configuration" not in evidence
        return httpx2.Response(200, json=response_payload(payload))

    install_transport(monkeypatch, handler)
    interpreted = interpret(report)
    assert len(calls) == 1 and interpreted.status == "ai_accepted"
    assert interpreted.evidence == report.evidence
    assert interpreted.evidence_sha256 == report.evidence_sha256
    assert interpreted.observations == report.observations
    assert (
        interpreted.ai_metadata is not None
        and interpreted.ai_metadata.response_model == "test-model"
    )
    assert "## Optional AI Interpretation" in markdown(interpreted)


@pytest.mark.parametrize(
    "kind",
    [
        "unknown_evidence",
        "unknown_observation",
        "fabricated_number",
        "wrong_unit",
        "free_number",
        "forecast",
        "advice",
        "guarantee",
        "unrelated_evidence",
        "wrong_kind",
        "duplicate",
        "invalid_schema",
        "extra_field",
        "empty",
    ],
)
def test_untrusted_claims_rejected_without_corrupting_deterministic_report(
    kind: str, native_results: dict[str, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    report = build_report(encode(native_results["backtest"]))
    payload = output(report)
    statement = payload["statements"][0]
    if kind == "unknown_evidence":
        statement["evidence_ids"] = ["unknown.id"]
    elif kind == "unknown_observation":
        statement["observation_id"] = "unknown.observation"
    elif kind == "fabricated_number":
        statement["numeric_references"][0]["value"] = 123456789
    elif kind == "wrong_unit":
        statement["numeric_references"][0]["unit"] = "pp"
    elif kind == "free_number":
        statement["text"] = "The return was 900 percent."
    elif kind == "forecast":
        statement["text"] = "The strategy will outperform in the future."
    elif kind == "advice":
        statement["text"] = "Buy BTCUSDT and allocate your capital now."
    elif kind == "guarantee":
        statement["text"] = "A high win rate guarantees profitability."
    elif kind == "unrelated_evidence":
        statement["evidence_ids"] = [report.evidence.metrics[0].id]
    elif kind == "wrong_kind":
        statement["explanation_code"] = "grid_context"
        statement["text"] = EXPLANATIONS["grid_context"]
    elif kind == "duplicate":
        payload["statements"].append(copy.deepcopy(statement))
    elif kind == "invalid_schema":
        statement["explanation_code"] = "invented_code"
    elif kind == "extra_field":
        statement["predicted_return"] = 100
    elif kind == "empty":
        payload["statements"] = []
    install_transport(monkeypatch, lambda _: httpx2.Response(200, json=response_payload(payload)))
    interpreted = interpret(report)
    assert interpreted.status == "ai_rejected" and interpreted.ai_interpretation is None
    assert (
        interpreted.evidence == report.evidence and interpreted.observations == report.observations
    )
    rendered = markdown(interpreted)
    assert "## Performance Results" in rendered
    assert "## Optional AI Interpretation" not in rendered
    assert "900 percent" not in rendered and "will outperform" not in rendered


def test_missing_key_preserves_report(
    native_results: dict[str, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    report = build_report(encode(native_results["backtest"]))
    result = interpret(report)
    assert result.status == "ai_unavailable" and result.evidence == report.evidence
    assert "Deterministic report generated" in result.warnings[-1]


@pytest.mark.parametrize("failure", ["timeout", "rate_limit", "bad_json", "incomplete"])
def test_provider_failures_sanitized(
    failure: str, native_results: dict[str, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    report = build_report(encode(native_results["backtest"]))

    def handler(request: httpx2.Request) -> httpx2.Response:
        if failure == "timeout":
            raise httpx2.ReadTimeout("sensitive-provider-debug", request=request)
        if failure == "rate_limit":
            return httpx2.Response(
                429,
                json={
                    "error": {
                        "message": "sensitive-provider-debug",
                        "type": "rate_limit",
                        "code": "rate_limit",
                    }
                },
            )
        if failure == "bad_json":
            response: Any = response_payload(output(report))
            response["output"][0]["content"][0]["text"] = "{ invalid json"
            return httpx2.Response(200, json=response)
        return httpx2.Response(200, json=response_payload(output(report), status="incomplete"))

    install_transport(monkeypatch, handler)
    result = interpret(report)
    assert result.status == (
        "ai_unavailable" if failure in ("timeout", "rate_limit") else "ai_rejected"
    )
    assert result.evidence == report.evidence
    assert "sensitive-provider-debug" not in result.model_dump_json()
