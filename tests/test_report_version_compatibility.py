"""Actual tagged-engine JSON compatibility; no provider or OpenAI access."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from strategy_backtest_agent.reports.cli import main
from strategy_backtest_agent.reports.evidence import build_report
from strategy_backtest_agent.reports.render import markdown

FIXTURES = Path(__file__).parent / "fixtures" / "reports"
VERSIONS = ("v0.8.0", "v0.9.0")
KINDS = ("backtest", "comparison", "validation", "sensitivity", "costs", "walk_forward")


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("kind", KINDS)
def test_tagged_research_outputs_offline_deterministic(
    version: str, kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("report must not call OpenAI or execute research")

    monkeypatch.setattr("strategy_backtest_agent.ai.parser.create_client", forbidden)
    monkeypatch.setattr("strategy_backtest_agent.backtester.run_backtest", forbidden)
    source = (FIXTURES / version / f"{kind}.json").read_bytes()
    first, second = build_report(source), build_report(source)
    assert first.model_dump_json() == second.model_dump_json()
    assert markdown(first) == markdown(second)
    assert first.evidence.source.research_type == kind
    assert first.status == "deterministic"
    if kind in ("comparison", "validation") and version == "v0.8.0":
        assert "indicator_initializations" not in first.evidence.reproducibility_metadata
    if kind == "walk_forward":
        anchors = first.evidence.reproducibility_metadata["indicator_initializations"]
        assert isinstance(anchors, list) and isinstance(anchors[0], dict)
        assert anchors[0]["prior_candle_count"] == 15
        assert ("seed_policy" in anchors[0]) == (version == "v0.9.0")
        assert ("input_fields" in anchors[0]) == (version == "v0.9.0")


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("format_name", ["markdown", "json"])
def test_tagged_walk_forward_cli_output(
    version: str, format_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    source = FIXTURES / version / "walk_forward.json"
    output = tmp_path / f"report.{format_name}"
    main(["--input", str(source), "--format", format_name, "--output", str(output)])
    report = build_report(source.read_bytes())
    expected = report.model_dump_json() + "\n" if format_name == "json" else markdown(report)
    assert output.read_text() == expected
    if format_name == "json":
        assert json.loads(output.read_text())["status"] == "deterministic"


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize(
    "mutation",
    ["count", "history_start", "warmup", "indicator", "input_fields", "seed_policy", "partial"],
)
def test_tagged_walk_forward_invalid_metadata_still_rejected(version: str, mutation: str) -> None:
    source = json.loads((FIXTURES / version / "walk_forward.json").read_bytes())
    shared = source["shared_data"]
    anchor = shared["indicator_initializations"][0]
    if mutation == "count":
        anchor["prior_candle_count"] = 14
    elif mutation == "history_start":
        anchor["history_start"] = "2024-01-01T00:00:00Z"
    elif mutation == "warmup":
        shared["required_warmup_candles"] = 14
    elif mutation == "indicator":
        anchor["indicator"]["period"] = 13
    elif mutation == "partial":
        anchor.pop("seed_policy", None)
        anchor["input_fields"] = ["close"]
    else:
        # Explicitly contradictory additive fields may never be treated as absent.
        anchor["input_fields"] = ["close"]
        anchor["seed_policy"] = (
            "legacy: RSI SMA/Wilder; SMA rolling; EMA first-close; configured history anchor"
        )
        anchor[mutation] = ["high", "low"] if mutation == "input_fields" else "wrong seed"
    with pytest.raises(ValueError):
        build_report(json.dumps(source).encode())


def test_actual_legacy_boundaries_from_reported_failure() -> None:
    source = json.loads((FIXTURES / "v0.8.0" / "walk_forward.json").read_bytes())
    anchor = source["shared_data"]["indicator_initializations"][0]
    assert anchor == {
        "indicator": {"type": "indicator", "name": "rsi", "period": 14},
        "prior_candle_count": 15,
        "history_start": "2023-12-31T09:00:00Z",
    }
    assert source["shared_data"]["warmup_policy"] == (
        "indicator-local seeds before first evaluation open; causal continuation"
    )
    report = build_report(json.dumps(source).encode())
    assert report.evidence.source.evaluation_start is not None
    assert report.evidence.source.evaluation_start.isoformat() == "2024-01-01T00:00:00+00:00"
    corrupted = copy.deepcopy(source)
    corrupted["shared_data"].pop("indicator_initializations")
    with pytest.raises(ValueError):
        build_report(json.dumps(corrupted).encode())


@pytest.mark.parametrize("index", range(3))
@pytest.mark.parametrize("missing", ["details", "profiles"])
def test_advanced_initialization_metadata_remains_required(index: int, missing: str) -> None:
    from test_advanced_research import SPECS, history, rule_for, settings
    from test_comparison_engine import named

    from strategy_backtest_agent.comparison.engine import run_comparison
    from strategy_backtest_agent.comparison.models import ComparisonConfig
    from strategy_backtest_agent.rules.evaluator import warmup_count

    rule = rule_for(SPECS[index])
    config = ComparisonConfig.model_validate(
        {**settings(rule), "strategies": [named("a", rule), named("b", rule)]}
    )
    source = run_comparison(history(warmup_count(rule)), config).model_dump(mode="json")
    if missing == "profiles":
        source["shared_data"].pop("indicator_initializations")
    else:
        anchor = source["shared_data"]["indicator_initializations"][0]
        anchor.pop("input_fields")
        anchor.pop("seed_policy")
    with pytest.raises(ValueError, match="initialization"):
        build_report(json.dumps(source).encode())
