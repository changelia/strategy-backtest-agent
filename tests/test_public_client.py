"""Public Python client contract and parity tests."""

import asyncio
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import httpx2
import pytest
from openai import OpenAI

from strategy_backtest_agent import (
    ATRIndicator,
    BacktestClient,
    BacktestClientError,
    BacktestConfig,
    Comparison,
    ComparisonConfig,
    CostScenarioConfig,
    Group,
    MACDIndicator,
    NamedStrategy,
    ParameterSpec,
    RuleStrategy,
    SensitivityConfig,
    StrategyParseError,
    ValidationConfig,
    Value,
    WalkForwardConfig,
)
from strategy_backtest_agent.cli import main as cli_main
from strategy_backtest_agent.comparison.models import ComparisonResult
from strategy_backtest_agent.costs.models import CostScenarioReport
from strategy_backtest_agent.init_cli import template
from strategy_backtest_agent.models import Candle
from strategy_backtest_agent.reports.inputs import CLIBacktest
from strategy_backtest_agent.sensitivity.models import SensitivityReport
from strategy_backtest_agent.validation.models import ValidationReport
from strategy_backtest_agent.walk_forward.models import WalkForwardReport


def comparison_config() -> ComparisonConfig:
    config = template("compare").model_dump(mode="json")
    config["period_days"] = 3
    return ComparisonConfig.model_validate_json(json.dumps(config))


def sensitivity_config() -> SensitivityConfig:
    rule = comparison_config().strategies[0].to_rules()
    return SensitivityConfig.model_validate_json(
        json.dumps(
            {
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "period_days": 3,
                "initial_balance": 10000,
                "fee": 0.001,
                "evaluation_end": "2024-07-01T00:00:00Z",
                "base_strategy": rule.model_dump(mode="json"),
                "parameters": [
                    ParameterSpec(path="entry.right.value", values=[25, 30]).model_dump()
                ],
            }
        )
    )


def costs_config() -> CostScenarioConfig:
    rule = comparison_config().strategies[0].to_rules()
    return CostScenarioConfig.model_validate_json(
        json.dumps(
            {
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "period_days": 3,
                "initial_balance": 10000,
                "fee": 0.001,
                "evaluation_end": "2024-07-01T00:00:00Z",
                "strategy": rule.model_dump(mode="json"),
                "scenarios": [
                    {"id": "baseline", "name": "Baseline"},
                    {"id": "modeled", "name": "Modeled costs", "spread_bps": 10, "slippage_bps": 5},
                ],
            }
        )
    )


def test_root_imports_templates_and_config_input_forms(tmp_path: Path) -> None:
    client = BacktestClient()
    config = client.template("backtest")
    assert isinstance(config, BacktestConfig)
    mapping_result = client.run(config=config.model_dump(mode="json"), days=3, demo=True)
    path = tmp_path / "config.json"
    path.write_text(config.model_dump_json(), encoding="utf-8")
    path_result = client.run(config=path, days=3, demo=True)
    model_result = client.run(config=config, days=3, demo=True)
    assert mapping_result.model_dump() == path_result.model_dump() == model_result.model_dump()
    assert mapping_result.research_type == "backtest"
    assert "Backtest:" in mapping_result.summary()


@pytest.mark.parametrize(
    ("prompt", "config", "message"),
    [
        ("strategy-backtest.json", None, "OPENAI_API_KEY is missing"),
        ("buy BTC", BacktestConfig(), "either"),
        (None, None, "Provide"),
    ],
)
def test_input_is_explicit_and_conflicts_are_rejected(
    prompt: str | None, config: Any, message: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    error_type = StrategyParseError if prompt == "strategy-backtest.json" else BacktestClientError
    with pytest.raises(error_type, match=message):
        BacktestClient().run(prompt, config=config, demo=True)


def test_all_six_modes_return_typed_results_and_preserve_mode_data() -> None:
    client = BacktestClient()
    comparison = client.compare(config=comparison_config(), demo=True)
    validation_values = template("validate").model_dump(mode="json")
    validation_values["period_days"] = 3
    validation_cfg = ValidationConfig.model_validate_json(json.dumps(validation_values))
    validation = client.validate(config=validation_cfg, demo=True)
    sensitivity = client.sensitivity(config=sensitivity_config(), demo=True)
    costs = client.costs(config=costs_config(), demo=True)
    wf_template = client.template("walk-forward").model_dump(mode="json")
    wf_template["period_days"] = 30
    wf_template["windows"].update(train_days=15, test_days=5, step_days=5, max_folds=3)
    walk_forward = client.walk_forward(
        config=WalkForwardConfig.model_validate_json(json.dumps(wf_template)), demo=True
    )
    single = client.run(config=client.template("backtest"), days=3, demo=True)
    assert isinstance(comparison.data, ComparisonResult)
    assert isinstance(validation.data, ValidationReport)
    assert isinstance(sensitivity.data, SensitivityReport)
    assert isinstance(costs.data, CostScenarioReport)
    assert isinstance(walk_forward.data, WalkForwardReport)
    assert all(
        result.data is not None
        for result in (single, comparison, validation, sensitivity, costs, walk_forward)
    )
    assert len(comparison.data.results) == 2
    assert validation.data.results[0].train.result.initial_balance == 10000
    assert len(sensitivity.data.variants) == 2
    assert len(costs.data.results) == 2
    assert len(walk_forward.data.results) >= 2
    assert "fold" in walk_forward.summary().lower()


def test_public_client_runs_advanced_typed_rule_strategies() -> None:
    base = comparison_config().model_dump(mode="json")
    base["strategies"][0]["strategy"] = {
        "type": "rules",
        "entry": {
            "type": "and",
            "conditions": [
                {
                    "type": "comparison",
                    "left": {
                        "type": "indicator",
                        "name": "macd",
                        "fast_period": 2,
                        "slow_period": 4,
                        "signal_period": 3,
                        "component": "macd",
                    },
                    "operator": ">",
                    "right": {
                        "type": "indicator",
                        "name": "macd",
                        "fast_period": 2,
                        "slow_period": 4,
                        "signal_period": 3,
                        "component": "signal",
                    },
                },
                {
                    "type": "comparison",
                    "left": {"type": "indicator", "name": "atr", "period": 3},
                    "operator": ">",
                    "right": {"type": "value", "value": 0},
                },
            ],
        },
        "exit": {
            "type": "comparison",
            "left": {
                "type": "indicator",
                "name": "macd",
                "fast_period": 2,
                "slow_period": 4,
                "signal_period": 3,
                "component": "macd",
            },
            "operator": "<",
            "right": {
                "type": "indicator",
                "name": "macd",
                "fast_period": 2,
                "slow_period": 4,
                "signal_period": 3,
                "component": "signal",
            },
        },
    }
    config = ComparisonConfig.model_validate_json(json.dumps(base))
    result = BacktestClient().compare(config=config, demo=True)
    assert isinstance(result.data, ComparisonResult)
    assert {item.name for item in result.data.shared_data.indicators} == {"macd", "atr", "rsi"}
    assert result.data.shared_data.indicator_initializations
    assert result.data.results[0].strategy.entry.type == "and"
    # The public constructors can also be imported without internal module paths.
    assert Comparison.model_fields and Group.model_fields
    assert MACDIndicator.model_fields and ATRIndicator.model_fields
    assert NamedStrategy.model_fields and Value.model_fields


def test_demo_uses_synthetic_history_and_api_is_quiet(
    monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    class NeverFetch:
        async def fetch_candles(self, *_: Any) -> list[Candle]:
            raise AssertionError("demo must never fetch market data")

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = BacktestClient(market_data_provider=NeverFetch()).compare(
        config=comparison_config(), demo=True
    )
    assert isinstance(result.data, ComparisonResult)
    assert result.data.shared_data.source == "synthetic_demo"
    assert capsys.readouterr() == ("", "")


def test_direct_report_generation_is_deterministic_and_safe(tmp_path: Path) -> None:
    client = BacktestClient()
    result = client.run(config=client.template("backtest"), days=3, demo=True)
    json_report = client.report(result, format="json")
    markdown_report = result.save_report(tmp_path / "report.md")
    assert json.loads(json_report)["evidence_sha256"]
    assert markdown_report.startswith("# Historical Strategy Research Report")
    assert (tmp_path / "report.md").read_text() == markdown_report
    assert client.report(result, format="json") == json_report
    with pytest.raises(BacktestClientError, match="safely create"):
        result.save_report(tmp_path / "report.md")
    assert client.report(result, format="markdown") == client.report(result, format="markdown")


def test_fixed_demo_api_matches_existing_cli_and_report_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: Any
) -> None:
    config = BacktestConfig()
    client = BacktestClient()
    api_result = client.run(config=config, days=3, demo=True)
    config_path = tmp_path / "backtest.json"
    config_path.write_text(config.model_dump_json(), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        ["strategy-backtest", "--config", str(config_path), "--days", "3", "--demo", "--json"],
    )
    cli_main()
    cli_bytes = capsys.readouterr().out.encode()
    assert json.loads(api_result.to_json()) == json.loads(cli_bytes)
    api_report = json.loads(client.report(api_result, format="json"))
    cli_path = tmp_path / "cli.json"
    cli_path.write_bytes(cli_bytes)
    cli_report = json.loads(client.report(cli_path, format="json"))
    assert api_report["evidence_sha256"] == cli_report["evidence_sha256"]
    assert api_report["evidence"] == cli_report["evidence"]


@pytest.mark.parametrize(
    "workflow", ["compare", "validate", "sensitivity", "costs", "walk-forward"]
)
def test_shared_research_modes_match_cli_results_and_evidence(
    workflow: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: Any
) -> None:
    client = BacktestClient()
    if workflow == "compare":
        config: Any = comparison_config()
        result = client.compare(config=config, demo=True)
    elif workflow == "validate":
        values = template("validate").model_dump(mode="json")
        values["period_days"] = 3
        config = ValidationConfig.model_validate_json(json.dumps(values))
        result = client.validate(config=config, demo=True)
    elif workflow == "sensitivity":
        config = sensitivity_config()
        result = client.sensitivity(config=config, demo=True)
        from strategy_backtest_agent.sensitivity import cli as sensitivity_cli
        from strategy_backtest_agent.sensitivity.engine import run_sensitivity
        from strategy_backtest_agent.sensitivity.grid import expand_grid

        _, variants = expand_grid(config.base_strategy, config.parameters)

        async def offline_sensitivity(_: Any, loaded: Any, *, data_source: str) -> Any:
            candles = client._demo_history(loaded, [variant.strategy for variant in variants])
            return run_sensitivity(candles, loaded, data_source="synthetic_demo")

        monkeypatch.setattr(sensitivity_cli, "fetch_and_analyze", offline_sensitivity)
    elif workflow == "costs":
        config = costs_config()
        result = client.costs(config=config, demo=True)
        from strategy_backtest_agent.costs import cli as costs_cli
        from strategy_backtest_agent.costs.engine import run_cost_scenarios

        async def offline_costs(_: Any, loaded: Any, *, data_source: str) -> Any:
            candles = client._demo_history(loaded, [loaded.strategy])
            return run_cost_scenarios(candles, loaded, data_source="synthetic_demo")

        monkeypatch.setattr(costs_cli, "fetch_and_run_costs", offline_costs)
    else:
        values = template("walk-forward").model_dump(mode="json")
        values["period_days"] = 30
        values["windows"].update(train_days=15, test_days=5, step_days=5, max_folds=3)
        config = WalkForwardConfig.model_validate_json(json.dumps(values))
        result = client.walk_forward(config=config, demo=True)
    config_path = tmp_path / f"{workflow}.json"
    config_path.write_text(config.model_dump_json(), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "strategy-backtest",
            workflow,
            "--config",
            str(config_path),
            *(["--demo"] if workflow in {"compare", "validate", "walk-forward"} else []),
            "--json",
        ],
    )
    cli_main()
    cli_bytes = capsys.readouterr().out.encode()
    assert json.loads(result.to_json()) == json.loads(cli_bytes)
    cli_path = tmp_path / f"{workflow}-cli.json"
    cli_path.write_bytes(cli_bytes)
    python_evidence = json.loads(client.report(result, format="json"))
    cli_evidence = json.loads(client.report(cli_path, format="json"))
    assert python_evidence["evidence_sha256"] == cli_evidence["evidence_sha256"]
    assert python_evidence["evidence"] == cli_evidence["evidence"]


def test_template_and_doctor_are_structured_and_do_not_write(tmp_path: Path, capsys: Any) -> None:
    client = BacktestClient()
    destination = tmp_path / "template.json"
    value = client.template("compare", output=destination)
    assert isinstance(value, ComparisonConfig)
    original = destination.read_bytes()
    with pytest.raises(BacktestClientError):
        client.template("compare", output=destination)
    diagnostics = client.doctor()
    assert diagnostics.offline_ready
    assert diagnostics.config_valid is None
    assert destination.read_bytes() == original
    assert capsys.readouterr() == ("", "")


def test_invalid_client_inputs_and_diagnostics_never_echo_secrets() -> None:
    marker = "SYNTHETIC_SECRET_MARKER_4281"
    client = BacktestClient(api_key=marker)
    for operation in (
        lambda: client.run(config={"api_key": marker}, demo=True),
        lambda: client.report({"api_key": marker}),
    ):
        with pytest.raises(BacktestClientError) as error:
            operation()
        assert marker not in str(error.value)
    diagnostics = client.doctor()
    assert marker not in repr(client)
    assert marker not in diagnostics.model_dump_json()


def test_explicit_dotenv_and_environment_precedence_without_environment_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("OPENAI_API_KEY=dotenv-secret-marker\nOPENAI_MODEL=gpt-dotenv\n")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    client = BacktestClient(dotenv_path=dotenv)
    assert client._api_key == "dotenv-secret-marker"
    assert client._model == "gpt-dotenv"
    assert "OPENAI_API_KEY" not in os.environ
    assert "dotenv-secret-marker" not in repr(client)
    monkeypatch.setenv("OPENAI_API_KEY", "shell-secret-marker")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-shell")
    shell_client = BacktestClient(dotenv_path=dotenv)
    assert shell_client._api_key == "shell-secret-marker"
    assert shell_client._model == "gpt-shell"
    explicit = BacktestClient(
        api_key="client-secret-marker", model="gpt-client", dotenv_path=dotenv
    )
    assert explicit._api_key == "client-secret-marker"
    assert explicit._model == "gpt-client"
    empty = BacktestClient(api_key="", model="")
    assert not empty.doctor().api_key_present
    assert not empty.doctor().model_configured
    assert "secret-marker" not in repr(explicit)


def test_environment_default_and_explicit_ai_settings_are_isolated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from strategy_backtest_agent.ai import parser

    monkeypatch.setenv("OPENAI_API_KEY", "environment-key-marker")
    monkeypatch.setenv("OPENAI_MODEL", "environment-model")
    shell = BacktestClient()
    assert shell._api_key == "environment-key-marker"
    assert shell._model == "environment-model"
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.delenv("OPENAI_MODEL")
    default = BacktestClient()
    assert default._api_key == ""
    assert default._model == parser.DEFAULT_MODEL

    barrier = threading.Barrier(2)
    observed: list[tuple[str | None, str | None]] = []

    def mocked_parse(_text: str, *, api_key: str | None = None, model: str | None = None) -> Any:
        barrier.wait(timeout=2)
        time.sleep(0.01)
        observed.append((api_key, model))
        return template("backtest")

    monkeypatch.setattr(parser, "parse_strategy", mocked_parse)
    first = BacktestClient(api_key="first-key-marker", model="model-one")
    second = BacktestClient(api_key="second-key-marker", model="model-two")

    async def call_both() -> list[Any]:
        return list(
            await asyncio.gather(
                first.aparse("Backtest BTCUSDT"), second.aparse("Backtest BTCUSDT")
            )
        )

    asyncio.run(call_both())
    assert set(observed) == {
        ("first-key-marker", "model-one"),
        ("second-key-marker", "model-two"),
    }
    assert "first-key-marker" not in repr(first) and "second-key-marker" not in repr(second)


def test_report_ai_uses_client_credentials_without_environment_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import strategy_backtest_agent.client as client_module

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    seen: list[tuple[str | None, str | None]] = []

    def fake_interpret(report: Any, *, api_key: str | None, model: str | None) -> Any:
        seen.append((api_key, model))
        return report

    monkeypatch.setattr(client_module, "interpret", fake_interpret)
    client = BacktestClient(api_key="report-key-marker", model="report-model")
    result = client.run(config=client.template("backtest"), days=3, demo=True)
    client.report(result, format="json", ai=True)
    assert seen == [("report-key-marker", "report-model")]
    assert "report-key-marker" not in repr(result)


def test_mocked_ai_parse_then_demo_rule_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from test_ai_parser import extraction, response_payload

    from strategy_backtest_agent.ai import parser

    rule = {
        "type": "rules",
        "entry": {
            "type": "comparison",
            "left": {"type": "indicator", "name": "rsi", "period": 14},
            "operator": "<",
            "right": {"type": "value", "value": 30},
        },
        "exit": {
            "type": "comparison",
            "left": {"type": "indicator", "name": "rsi", "period": 14},
            "operator": ">",
            "right": {"type": "value", "value": 70},
        },
    }
    calls: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        body = json.loads(request.content)
        assert body["model"] == "client-model"
        assert request.headers["authorization"] == "Bearer client-ai-key-marker"
        return httpx2.Response(
            200,
            json=response_payload({"configuration": extraction(strategy=rule), "rejection": None}),
        )

    def mock_client(api_key: str | None = None) -> OpenAI:
        return OpenAI(
            api_key=api_key or "fallback-test-only",
            http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
            max_retries=0,
        )

    monkeypatch.setattr(parser, "create_client", mock_client)
    client = BacktestClient(api_key="client-ai-key-marker", model="client-model")
    parsed = client.parse("Backtest BTCUSDT with RSI rules")
    assert len(calls) == 1
    result = client.run(config=parsed, demo=True)
    assert isinstance(result.data, CLIBacktest)
    assert result.data.data_source == "synthetic_demo"
    assert isinstance(result.data.strategy, RuleStrategy)


def test_mocked_ai_interpretation_uses_client_and_keeps_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from test_ai_parser import response_payload
    from test_report_ai import output

    from strategy_backtest_agent.ai import parser

    requests: list[httpx2.Request] = []
    client = BacktestClient(api_key="client-report-key", model="client-report-model")
    result = client.run(config=client.template("backtest"), days=3, demo=True)
    source_report = client.report(result, format="json")
    source_evidence = json.loads(source_report)["evidence"]

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        body = json.loads(request.content)
        assert body["model"] == "client-report-model"
        assert request.headers["authorization"] == "Bearer client-report-key"
        return httpx2.Response(
            200, json=response_payload(output(build_report(result.to_json().encode())))
        )

    def mock_client(api_key: str | None = None) -> OpenAI:
        return OpenAI(
            api_key=api_key or "fallback-test-only",
            http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
            max_retries=0,
        )

    from strategy_backtest_agent.reports.evidence import build_report

    monkeypatch.setattr(parser, "create_client", mock_client)
    interpreted = json.loads(client.report(result, format="json", ai=True))
    assert len(requests) == 1
    assert interpreted["status"] == "ai_accepted"
    assert interpreted["evidence"] == source_evidence


def test_ai_report_sync_call_rejects_active_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    client = BacktestClient(api_key="synthetic-key")
    result = client.run(config=client.template("backtest"), days=3, demo=True)

    async def exercise() -> None:
        with pytest.raises(BacktestClientError, match="areport"):
            client.report(result, ai=True)

    asyncio.run(exercise())


def test_async_usage_inside_running_loop_and_sync_guard() -> None:
    client = BacktestClient()

    async def exercise() -> None:
        result = await client.arun(config=client.template("backtest"), days=3, demo=True)
        assert result.research_type == "backtest"
        with pytest.raises(BacktestClientError, match="async client method"):
            client.run(config=client.template("backtest"), days=3, demo=True)

    asyncio.run(exercise())


def test_root_exports_rule_types_and_walk_forward_configuration() -> None:
    assert RuleStrategy.model_fields
    assert WalkForwardConfig.model_fields
