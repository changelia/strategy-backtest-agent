"""Offline native-result adapters, grounding, security and report determinism."""

import copy
import hashlib
import json
from typing import Any

import pytest

from strategy_backtest_agent.reports.evidence import build_report
from strategy_backtest_agent.reports.inputs import canonical_bytes
from strategy_backtest_agent.reports.render import markdown

KINDS = ("backtest", "comparison", "validation", "sensitivity", "costs", "walk_forward")


def encode(value: dict[str, Any]) -> bytes:
    return json.dumps(value, allow_nan=False).encode()


@pytest.mark.parametrize("kind", KINDS)
def test_native_adapter_deterministic_and_lossless(
    kind: str, native_results: dict[str, dict[str, Any]]
) -> None:
    content = encode(native_results[kind])
    a, b = build_report(content), build_report(content)
    assert a.model_dump_json() == b.model_dump_json()
    assert markdown(a) == markdown(b)
    assert a.evidence.source.research_type == kind
    assert a.evidence.source.input_schema_version is None
    assert a.evidence.source.input_content_sha256 == hashlib.sha256(content).hexdigest()
    assert (
        a.evidence.source.canonical_input_sha256
        == hashlib.sha256(canonical_bytes(native_results[kind])).hexdigest()
    )
    assert len({m.id for m in a.evidence.metrics}) == len(a.evidence.metrics)
    for metric in a.evidence.metrics:
        if metric.name in ("net_pnl", "fee_per_side", "full_spread", "slippage_per_side"):
            continue
        value: Any = native_results[kind]
        for part in metric.source_path.strip("/").split("/"):
            value = value[int(part)] if isinstance(value, list) else value[part]
        assert metric.value == value
    assert a.status == "deterministic" and a.ai_interpretation is None
    assert "## Limitations" in markdown(a)


def test_undefined_units_benchmarks_and_negative_oos_not_hidden(
    native_results: dict[str, dict[str, Any]],
) -> None:
    comparison = build_report(encode(native_results["comparison"]))
    lookup = {m.id: m for m in comparison.evidence.metrics}
    assert lookup["strategy.never.profit_factor"].value is None
    assert lookup["strategy.never.win_rate"].value is None
    assert lookup["strategy.never.excess_return"].unit == "pp"
    assert lookup["strategy.never.net_buy_and_hold"].unit == "%"
    assert lookup["strategy.always.fees"].unit == "quote_currency"
    assert lookup["strategy.always.full_spread"].unit == "bps"
    assert "N/A (undefined)" in markdown(comparison)
    oos = build_report(encode(native_results["walk_forward"]))
    returns = [
        m.value
        for m in oos.evidence.metrics
        if m.name == "total_return" and m.scope.endswith(".test")
    ]
    assert any(v is not None and v < 0 for v in returns)
    assert len(returns) == 3
    assert "not continuous execution with carried positions" in markdown(oos)
    assert all(m.name != "continuous_drawdown" for m in oos.evidence.metrics)
    assert any("1 of 3" in o.text for o in oos.observations)


@pytest.mark.parametrize("kind", ["sensitivity", "costs"])
def test_train_only_wording_and_observations(
    kind: str, native_results: dict[str, dict[str, Any]]
) -> None:
    report = build_report(encode(native_results[kind]))
    text = markdown(report)
    assert "Train only" in text and "Test is reserved and not evaluated" in text
    assert not any(scope.role == "test" for scope in report.evidence.scopes)
    if kind == "sensitivity":
        assert any("no positive-return variants" in o.text for o in report.observations)
    else:
        assert any("lower than" in o.text for o in report.observations if o.kind == "costs")


@pytest.mark.parametrize(
    "field,value",
    [
        ("final_balance", 12345),
        ("total_return_percent", 999),
        ("win_rate", 90),
        ("profit_factor", 999),
        ("total_trades", 999),
        ("max_drawdown_percent", 10),
    ],
)
def test_contradictory_financial_values_rejected(
    field: str, value: int, native_results: dict[str, dict[str, Any]]
) -> None:
    raw = copy.deepcopy(native_results["comparison"])
    raw["results"][0]["result"][field] = value
    with pytest.raises(ValueError):
        build_report(encode(raw))


@pytest.mark.parametrize(
    "field", ["win_rate", "execution", "costs", "benchmark_policy", "total_return_percent"]
)
def test_missing_required_financial_fields_rejected(
    field: str, native_results: dict[str, dict[str, Any]]
) -> None:
    raw = copy.deepcopy(native_results["comparison"])
    raw["results"][0]["result"].pop(field)
    with pytest.raises(ValueError):
        build_report(encode(raw))


def test_forged_gross_benchmark_cannot_be_called_net(
    native_results: dict[str, dict[str, Any]],
) -> None:
    raw = copy.deepcopy(native_results["backtest"])
    raw["benchmark_policy"] = "gross first open to final close"
    with pytest.raises(ValueError, match="benchmark policy"):
        build_report(encode(raw))


@pytest.mark.parametrize("kind", KINDS)
def test_report_does_not_execute_backtest_or_fetch(
    kind: str, native_results: dict[str, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("report must not execute research")

    for module in [
        "strategy_backtest_agent.backtester",
        "strategy_backtest_agent.comparison.engine",
        "strategy_backtest_agent.validation.engine",
        "strategy_backtest_agent.sensitivity.engine",
        "strategy_backtest_agent.costs.engine",
        "strategy_backtest_agent.walk_forward.engine",
    ]:
        monkeypatch.setattr(module + ".run_backtest", forbidden)
    monkeypatch.setattr(
        "strategy_backtest_agent.market_data.BinanceMarketData.fetch_candles", forbidden
    )
    build_report(encode(native_results[kind]))


def test_canonical_hash_ignores_key_order_but_content_hash_records_bytes(
    native_results: dict[str, dict[str, Any]],
) -> None:
    raw = native_results["comparison"]
    a = build_report(encode(raw))
    b = build_report(json.dumps(raw, sort_keys=True, indent=2).encode())
    assert a.evidence.source.input_content_sha256 != b.evidence.source.input_content_sha256
    assert a.evidence.source.canonical_input_sha256 == b.evidence.source.canonical_input_sha256
    assert a.evidence.metrics == b.evidence.metrics and a.observations == b.observations


def test_ai_wrapped_backtest_and_legacy_cli_compatibility(
    native_results: dict[str, dict[str, Any]],
) -> None:
    from strategy_backtest_agent.ai.models import AIStrategyConfig
    from strategy_backtest_agent.reports.inputs import LegacyCLISettings

    raw = native_results["backtest"]
    parsed = AIStrategyConfig.model_validate(
        {
            "symbol": "BTCUSDT",
            "timeframe": "12h",
            "period_days": 4,
            "initial_balance": 1000,
            "fee": 0.01,
            "execution": raw["execution"],
            "strategy": raw["strategy"],
        }
    )
    wrapped = {
        "input": "Historical request (untrusted source text)",
        "parsed_strategy": parsed.model_dump(mode="json"),
        "backtest_result": raw,
    }
    report = build_report(encode(wrapped))
    assert report.evidence.source.adapter_version == "sba-v0.9-ai-backtest/1"
    assert all(m.source_path.startswith("/backtest_result/") for m in report.evidence.metrics)
    legacy = copy.deepcopy(raw)
    legacy["strategy"] = LegacyCLISettings(
        name="RSI", rsi_period=14, entry_rsi=30, exit_rsi=70, fee=0.01
    ).model_dump()
    legacy.pop("trading_fee")
    legacy.pop("indicator_configuration")
    report = build_report(encode(legacy))
    assert report.evidence.source.candle_sha256 is None
    assert report.warnings


@pytest.mark.parametrize(
    "field", ["median_return_percent", "positive_return_percent", "variant_count"]
)
def test_contradictory_sensitivity_summary_rejected(
    field: str, native_results: dict[str, dict[str, Any]]
) -> None:
    raw = copy.deepcopy(native_results["sensitivity"])
    raw["summary"][field] = 999
    with pytest.raises(ValueError):
        build_report(encode(raw))


def test_cost_baseline_and_validation_gap_rejected_when_inconsistent(
    native_results: dict[str, dict[str, Any]],
) -> None:
    costs = copy.deepcopy(native_results["costs"])
    costs["results"][1]["return_difference_pp"] = 99
    with pytest.raises(ValueError):
        build_report(encode(costs))
    validation = copy.deepcopy(native_results["validation"])
    validation["results"][0]["return_gap_pp"] = 99
    with pytest.raises(ValueError):
        build_report(encode(validation))


def test_high_win_rate_never_described_as_guarantee(
    native_results: dict[str, dict[str, Any]],
) -> None:
    raw = native_results["walk_forward"]
    assert raw["results"][0]["test"]["result"]["win_rate"] == 100
    report = build_report(encode(raw))
    assert not any(
        "guarantee" in o.text or "safe" in o.text or "optimal" in o.text
        for o in report.observations
    )
    assert any("do not predict" in limitation.text for limitation in report.evidence.limitations)


@pytest.mark.parametrize("index", range(3))
@pytest.mark.parametrize(
    "workflow", ["comparison", "validation", "sensitivity", "costs", "rolling", "expanding"]
)
def test_advanced_indicator_research_metadata(index: int, workflow: str) -> None:
    from pydantic import BaseModel
    from test_advanced_research import SPECS, history, rule_for, settings

    from strategy_backtest_agent.comparison.engine import run_comparison
    from strategy_backtest_agent.comparison.models import ComparisonConfig
    from strategy_backtest_agent.costs.engine import run_cost_scenarios
    from strategy_backtest_agent.costs.models import CostScenarioConfig
    from strategy_backtest_agent.rules.evaluator import warmup_count
    from strategy_backtest_agent.sensitivity.engine import run_sensitivity
    from strategy_backtest_agent.sensitivity.models import SensitivityConfig
    from strategy_backtest_agent.validation.engine import run_validation
    from strategy_backtest_agent.validation.models import ValidationConfig
    from strategy_backtest_agent.walk_forward.engine import run_walk_forward
    from strategy_backtest_agent.walk_forward.models import WalkForwardConfig

    result: BaseModel
    spec = SPECS[index]
    rule = rule_for(spec)
    values = settings(rule)
    source = history(warmup_count(rule))
    if workflow == "comparison":
        values["strategies"] = [
            {"id": "first", "name": "first", "strategy": rule},
            {"id": "other", "name": "other", "strategy": rule},
        ]
        result = run_comparison(source, ComparisonConfig.model_validate(values))
    elif workflow == "validation":
        result = run_validation(source, ValidationConfig.model_validate(values))
    elif workflow == "sensitivity":
        values.pop("strategies")
        field = "fast_period" if index == 0 else "period"
        values.update(
            base_strategy=rule,
            parameters=[{"path": f"entry.left.{field}", "values": [getattr(spec, field)]}],
        )
        result = run_sensitivity(source, SensitivityConfig.model_validate(values))
    elif workflow == "costs":
        values.pop("strategies")
        values.pop("execution")
        values.update(
            strategy=rule,
            scenarios=[
                {"id": "base", "name": "base"},
                {"id": "costs", "name": "costs", "spread_bps": 20},
            ],
        )
        result = run_cost_scenarios(source, CostScenarioConfig.model_validate(values))
    else:
        values["windows"] = {"mode": workflow, "train_days": 1, "test_days": 1}
        result = run_walk_forward(source, WalkForwardConfig.model_validate(values))
    report = build_report(result.model_dump_json().encode())
    assert report.evidence.reproducibility_metadata["indicator_initializations"]
    corrupted = result.model_dump(mode="json")
    corrupted["shared_data"]["indicator_initializations"][0]["input_fields"] = ["open"]
    with pytest.raises(ValueError, match="initialization"):
        build_report(encode(corrupted))


def test_committed_example_reproduces_exactly() -> None:
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (root / "examples/report-source.json").read_bytes()
    generated = subprocess.check_output([sys.executable, str(root / "examples/report_fixture.py")])
    assert generated == source
    assert markdown(build_report(source)) == (root / "examples/research-report.md").read_text()
