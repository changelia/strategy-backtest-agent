"""Stable Python client over the validated historical research engines."""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import logging
import os
import sys
import threading
from collections.abc import Callable, Coroutine, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, TypeVar, cast

from dotenv import dotenv_values
from pydantic import BaseModel, ValidationError

from strategy_backtest_agent.ai.models import AIStrategyConfig
from strategy_backtest_agent.ai.parser import DEFAULT_MODEL
from strategy_backtest_agent.comparison.engine import (
    fetch_and_compare,
    normalized_strategies,
    run_comparison,
)
from strategy_backtest_agent.comparison.models import ComparisonConfig, ComparisonResult
from strategy_backtest_agent.costs.engine import fetch_and_run_costs, run_cost_scenarios
from strategy_backtest_agent.costs.formatter import format_cost_scenarios
from strategy_backtest_agent.costs.models import CostScenarioConfig, CostScenarioReport
from strategy_backtest_agent.demo import demo_candles
from strategy_backtest_agent.market_data import (
    BinanceMarketData,
    MarketDataError,
    MarketDataProvider,
)
from strategy_backtest_agent.models import BacktestConfig, Candle, Model
from strategy_backtest_agent.reports.ai import interpret
from strategy_backtest_agent.reports.cli import write_new
from strategy_backtest_agent.reports.evidence import build_report
from strategy_backtest_agent.reports.inputs import MAX_INPUT_BYTES, CLIBacktest, read_input
from strategy_backtest_agent.reports.models import ResearchReport
from strategy_backtest_agent.rules.evaluator import warmup_count
from strategy_backtest_agent.rules.history import interval_duration
from strategy_backtest_agent.rules.models import RuleStrategy
from strategy_backtest_agent.sensitivity.engine import fetch_and_analyze, run_sensitivity
from strategy_backtest_agent.sensitivity.formatter import format_sensitivity
from strategy_backtest_agent.sensitivity.grid import expand_grid
from strategy_backtest_agent.sensitivity.models import SensitivityConfig, SensitivityReport
from strategy_backtest_agent.services import backtest_json, execute_backtest
from strategy_backtest_agent.validation.engine import fetch_and_validate, run_validation
from strategy_backtest_agent.validation.formatter import format_validation
from strategy_backtest_agent.validation.models import ValidationConfig, ValidationReport
from strategy_backtest_agent.walk_forward.engine import fetch_and_walk_forward, run_walk_forward
from strategy_backtest_agent.walk_forward.formatter import format_walk_forward
from strategy_backtest_agent.walk_forward.models import WalkForwardConfig, WalkForwardReport

ReportFormat = Literal["markdown", "json"]
Workflow = Literal["backtest", "compare", "validate", "sensitivity", "walk-forward"]
ResearchValue = (
    CLIBacktest
    | ComparisonResult
    | ValidationReport
    | SensitivityReport
    | CostScenarioReport
    | WalkForwardReport
    | ResearchReport
)
ConfigValue = BaseModel | Mapping[str, Any] | str | Path
ConfigT = TypeVar("ConfigT", bound=BaseModel)
ResultT = TypeVar("ResultT")
_DOTENV_LOG_LOCK = threading.Lock()


class BacktestClientError(RuntimeError):
    """Sanitized error raised by a public client operation."""


class DoctorDiagnostics(Model):
    python_version: str
    python_compatible: bool
    installed_package_version: str | None
    installed_metadata_available: bool
    source_checkout_version: str | None
    offline_ready: bool
    api_key_present: bool
    api_key_source: Literal["client", "environment", "dotenv", "none"]
    model_configured: bool
    model_source: Literal["client", "environment", "dotenv", "default"]
    config_workflow: str | None
    config_valid: bool | None
    warnings: list[str]


class ClientResult:
    """Typed result wrapper with a deterministic summary and direct report support."""

    __slots__ = ("data", "_source_bytes", "_client", "_research_type")

    def __init__(
        self, data: ResearchValue, source_bytes: bytes, client: BacktestClient, research_type: str
    ) -> None:
        self.data = data
        self._source_bytes = source_bytes
        self._client = client
        self._research_type = research_type

    @property
    def research_type(self) -> str:
        return self._research_type

    def __getattr__(self, name: str) -> Any:
        return getattr(self.data, name)

    def __repr__(self) -> str:
        return (
            f"ClientResult(research_type={self._research_type!r}, data={type(self.data).__name__})"
        )

    def summary(self) -> str:
        from strategy_backtest_agent.comparison.formatter import format_comparison
        from strategy_backtest_agent.reports.render import markdown

        if isinstance(self.data, CLIBacktest):
            value = self.data
            return (
                f"Backtest: {value.symbol} {value.timeframe}, {value.period_days} days; "
                f"return {value.total_return_percent:+.2f}%; "
                f"final balance {value.final_balance:.2f}; trades {value.total_trades}."
            )
        if isinstance(self.data, ComparisonResult):
            return format_comparison(self.data)
        if isinstance(self.data, ValidationReport):
            return format_validation(self.data)
        if isinstance(self.data, SensitivityReport):
            return format_sensitivity(self.data)
        if isinstance(self.data, CostScenarioReport):
            return format_cost_scenarios(self.data)
        if isinstance(self.data, WalkForwardReport):
            return format_walk_forward(self.data)
        return markdown(self.data)

    def model_dump(self, *, mode: str = "python") -> dict[str, Any]:
        return self.data.model_dump(mode=mode)

    def model_dump_json(self) -> str:
        return self.data.model_dump_json()

    def to_json(self) -> str:
        """Return the complete CLI-compatible input accepted by report generation."""
        return self._source_bytes.decode("utf-8")

    def save_report(
        self, path: str | Path, *, format: ReportFormat = "markdown", ai: bool = False
    ) -> str:
        return self._client.report(self, format=format, output=path, ai=ai)


class BacktestClient:
    """Run research with isolated credentials and no import- or construction-time network I/O.

    Environment variables are captured at construction. An explicitly selected dotenv
    file is read without changing process environment; environment values take precedence.
    """

    __slots__ = ("_api_key", "_model", "_key_source", "_model_source", "_provider")

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        dotenv_path: str | Path | None = None,
        market_data_provider: MarketDataProvider | None = None,
    ) -> None:
        dotenv: Mapping[str, str | None] = {}
        if dotenv_path is not None:
            logger = logging.getLogger("dotenv.main")
            with _DOTENV_LOG_LOCK:
                previous = logger.handlers[:], logger.propagate, logger.level
                try:
                    logger.handlers = [logging.NullHandler()]
                    logger.propagate = False
                    logger.setLevel(logging.CRITICAL)
                    dotenv = dotenv_values(
                        dotenv_path=Path(dotenv_path), interpolate=True, verbose=False
                    )
                except (OSError, UnicodeError, ValueError):
                    raise BacktestClientError(
                        "Could not read the explicitly selected dotenv file"
                    ) from None
                finally:
                    logger.handlers, logger.propagate, logger.level = previous
        if api_key is not None:
            self._api_key, self._key_source = api_key, "client"
        elif "OPENAI_API_KEY" in os.environ:
            self._api_key, self._key_source = os.environ["OPENAI_API_KEY"], "environment"
        elif dotenv.get("OPENAI_API_KEY") is not None:
            self._api_key, self._key_source = str(dotenv["OPENAI_API_KEY"]), "dotenv"
        else:
            self._api_key, self._key_source = "", "none"
        if model is not None:
            self._model, self._model_source = model, "client"
        elif "OPENAI_MODEL" in os.environ:
            self._model, self._model_source = os.environ["OPENAI_MODEL"], "environment"
        elif dotenv.get("OPENAI_MODEL") is not None:
            self._model, self._model_source = str(dotenv["OPENAI_MODEL"]), "dotenv"
        else:
            self._model, self._model_source = DEFAULT_MODEL, "default"
        self._provider = market_data_provider

    def __repr__(self) -> str:
        state = "configured" if self._api_key.strip() else "absent"
        return f"BacktestClient(api_key={state}, model_source={self._model_source!r})"

    @staticmethod
    def _sync(
        call: Callable[..., Coroutine[Any, Any, ResultT]], *args: Any, **kwargs: Any
    ) -> ResultT:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(call(*args, **kwargs))
        raise BacktestClientError("Use the corresponding async client method inside an event loop")

    @staticmethod
    def _load(model: type[ConfigT], config: ConfigValue) -> ConfigT:
        try:
            if isinstance(config, model):
                return model.model_validate(config.model_dump(warnings=False))
            if isinstance(config, BaseModel):
                return model.model_validate(config.model_dump(warnings=False))
            if isinstance(config, Mapping):
                return model.model_validate(config)
            contents = read_input(Path(config))
            if len(contents) > MAX_INPUT_BYTES:
                raise ValueError("configuration exceeds input limit")
            return model.model_validate_json(contents)
        except (ValidationError, OSError, ValueError, TypeError, RecursionError):
            raise BacktestClientError(f"Invalid {model.__name__} configuration") from None

    @staticmethod
    def _one_source(request: str | None, config: ConfigValue | None) -> None:
        if request is not None and config is not None:
            raise BacktestClientError(
                "Provide either natural-language request or config=, not both"
            )
        if request is None and config is None:
            raise BacktestClientError("Provide a natural-language request or explicit config=")
        if request is not None and not isinstance(request, str):
            raise BacktestClientError("Positional research input must be natural-language text")

    async def aparse(self, text: str, *, workflow: Workflow = "backtest") -> BaseModel:
        """Await structured AI parsing without executing a research workflow."""
        from strategy_backtest_agent.ai import parser

        functions = {
            "backtest": parser.parse_strategy,
            "compare": parser.parse_comparison,
            "validate": parser.parse_validation,
            "sensitivity": parser.parse_sensitivity,
            "walk-forward": parser.parse_walk_forward,
        }
        function = functions.get(workflow)
        if function is None:
            raise BacktestClientError("No natural-language parser exists for this workflow")
        try:
            return cast(
                BaseModel,
                await asyncio.to_thread(function, text, api_key=self._api_key, model=self._model),
            )
        except (ValueError, ValidationError, MarketDataError):
            raise
        except Exception:
            raise BacktestClientError("AI parsing failed; details were withheld") from None

    def parse(self, text: str, *, workflow: Workflow = "backtest") -> BaseModel:
        """Parse and validate a request without fetching data or executing research."""
        return self._sync(self.aparse, text, workflow=workflow)

    @staticmethod
    def _bytes(value: BaseModel) -> bytes:
        return (value.model_dump_json() + "\n").encode("utf-8")

    def _wrap(self, value: BaseModel, source: bytes, kind: str) -> ClientResult:
        return ClientResult(cast(ResearchValue, value), source, self, kind)

    @staticmethod
    def _demo_history(config: BaseModel, strategies: Sequence[RuleStrategy]) -> list[Candle]:
        fields = config.model_dump()
        timeframe = str(fields["timeframe"])
        days = int(fields["period_days"])
        duration = interval_duration(timeframe)
        end = datetime(2024, 7, 1, tzinfo=UTC)
        configured_end = getattr(config, "evaluation_end", None)
        if configured_end is not None and configured_end != end:
            raise BacktestClientError("demo data ends at 2024-07-01T00:00:00Z")
        required = max((warmup_count(strategy) for strategy in strategies), default=0)
        count = days * 86400 // int(duration.total_seconds())
        extra_days = (required * int(duration.total_seconds()) + 86399) // 86400
        generated = demo_candles(timeframe, days + extra_days)
        candles = generated[-(count + required) :]
        if len(candles) != count + required:
            raise BacktestClientError("Synthetic demo data could not satisfy indicator warm-up")
        return candles

    async def arun(
        self,
        request: str | None = None,
        *,
        config: ConfigValue | None = None,
        demo: bool = False,
        days: int | None = None,
        evaluation_end: datetime | None = None,
    ) -> ClientResult:
        """Async single-strategy backtest for use in an existing event loop."""
        self._one_source(request, config)
        ai_context: dict[str, object] | None = None
        if request is not None:
            parsed = await self.aparse(request)
            assert isinstance(parsed, AIStrategyConfig)
            typed: BaseModel = parsed
            run_days = parsed.period_days if days is None else days
            if run_days != parsed.period_days:
                raise BacktestClientError("days conflicts with parsed period_days")
            ai_context = {"input": request, "parsed_strategy": parsed.model_dump(mode="json")}
        else:
            assert config is not None
            try:
                typed = self._load(AIStrategyConfig, config)
                assert isinstance(typed, AIStrategyConfig)
                run_days = typed.period_days if days is None else days
                if run_days != typed.period_days:
                    raise BacktestClientError("days conflicts with config period_days")
            except BacktestClientError as first_error:
                try:
                    typed = self._load(BacktestConfig, config)
                except BacktestClientError:
                    raise first_error from None
                run_days = 180 if days is None else days
        if isinstance(typed, AIStrategyConfig):
            backtest_config = typed.to_backtest_config()
            strategy = typed.strategy if isinstance(typed.strategy, RuleStrategy) else None
        else:
            assert isinstance(typed, BacktestConfig)
            backtest_config, strategy = typed, None
        execution = await execute_backtest(
            backtest_config,
            run_days,
            demo=demo,
            provider=self._provider or BinanceMarketData(),
            strategy=strategy,
            evaluation_end=evaluation_end,
        )
        if ai_context is None:
            source = backtest_json(execution)
            result = CLIBacktest.model_validate_json(source)
        else:
            from strategy_backtest_agent.services import backtest_payload

            result = CLIBacktest.model_validate(backtest_payload(execution))
            source = (
                json.dumps(
                    {**ai_context, "backtest_result": backtest_payload(execution)},
                    allow_nan=False,
                )
                + "\n"
            ).encode("utf-8")
        return self._wrap(result, source, "backtest")

    def run(
        self,
        request: str | None = None,
        *,
        config: ConfigValue | None = None,
        demo: bool = False,
        days: int | None = None,
        evaluation_end: datetime | None = None,
    ) -> ClientResult:
        """Synchronously run one strategy; use arun within an existing event loop."""
        return self._sync(
            self.arun,
            request,
            config=config,
            demo=demo,
            days=days,
            evaluation_end=evaluation_end,
        )

    async def _aresearch(
        self,
        workflow: Literal["compare", "validate", "sensitivity", "costs", "walk-forward"],
        request: str | None,
        config: ConfigValue | None,
        demo: bool,
    ) -> ClientResult:
        self._one_source(request, config)
        if workflow == "costs":
            if request is not None:
                raise BacktestClientError("Cost scenarios currently require CostScenarioConfig")
            assert config is not None
            cost_config = self._load(CostScenarioConfig, config)
            typed: BaseModel = cost_config
            strategies = [cost_config.strategy]
            engine: Any = run_cost_scenarios
            fetch: Any = fetch_and_run_costs
        else:
            if request is not None:
                typed = await self.aparse(request, workflow=workflow)
            else:
                assert config is not None
                models: dict[str, type[BaseModel]] = {
                    "compare": ComparisonConfig,
                    "validate": ValidationConfig,
                    "sensitivity": SensitivityConfig,
                    "walk-forward": WalkForwardConfig,
                }
                typed = self._load(models[workflow], config)
            if workflow == "compare":
                assert isinstance(typed, ComparisonConfig)
                strategies = normalized_strategies(typed)
                engine, fetch = run_comparison, fetch_and_compare
            elif workflow == "validate":
                assert isinstance(typed, ValidationConfig)
                strategies = normalized_strategies(typed)
                engine, fetch = run_validation, fetch_and_validate
            elif workflow == "sensitivity":
                assert isinstance(typed, SensitivityConfig)
                _, variants = expand_grid(typed.base_strategy, typed.parameters)
                strategies = [variant.strategy for variant in variants]
                engine, fetch = run_sensitivity, fetch_and_analyze
            else:
                assert isinstance(typed, WalkForwardConfig)
                strategies = normalized_strategies(typed)
                engine, fetch = run_walk_forward, fetch_and_walk_forward
        if demo:
            value = engine(
                self._demo_history(typed, strategies), typed, data_source="synthetic_demo"
            )
        else:
            value = await fetch(self._provider or BinanceMarketData(), typed, data_source="binance")
        return self._wrap(value, self._bytes(value), workflow)

    async def acompare(
        self, request: str | None = None, *, config: ConfigValue | None = None, demo: bool = False
    ) -> ClientResult:
        return await self._aresearch("compare", request, config, demo)

    def compare(
        self, request: str | None = None, *, config: ConfigValue | None = None, demo: bool = False
    ) -> ClientResult:
        return self._sync(self.acompare, request, config=config, demo=demo)

    async def avalidate(
        self, request: str | None = None, *, config: ConfigValue | None = None, demo: bool = False
    ) -> ClientResult:
        return await self._aresearch("validate", request, config, demo)

    def validate(
        self, request: str | None = None, *, config: ConfigValue | None = None, demo: bool = False
    ) -> ClientResult:
        return self._sync(self.avalidate, request, config=config, demo=demo)

    async def asensitivity(
        self, request: str | None = None, *, config: ConfigValue | None = None, demo: bool = False
    ) -> ClientResult:
        return await self._aresearch("sensitivity", request, config, demo)

    def sensitivity(
        self, request: str | None = None, *, config: ConfigValue | None = None, demo: bool = False
    ) -> ClientResult:
        return self._sync(self.asensitivity, request, config=config, demo=demo)

    async def acosts(self, *, config: ConfigValue, demo: bool = False) -> ClientResult:
        return await self._aresearch("costs", None, config, demo)

    def costs(self, *, config: ConfigValue, demo: bool = False) -> ClientResult:
        return self._sync(self.acosts, config=config, demo=demo)

    async def awalk_forward(
        self, request: str | None = None, *, config: ConfigValue | None = None, demo: bool = False
    ) -> ClientResult:
        return await self._aresearch("walk-forward", request, config, demo)

    def walk_forward(
        self, request: str | None = None, *, config: ConfigValue | None = None, demo: bool = False
    ) -> ClientResult:
        return self._sync(self.awalk_forward, request, config=config, demo=demo)

    def template(
        self,
        workflow: Literal["backtest", "compare", "validate", "walk-forward"],
        *,
        output: str | Path | None = None,
    ) -> Model:
        """Return an existing validated template, optionally saved without overwriting."""
        from strategy_backtest_agent.init_cli import template

        try:
            value = template(workflow)
            if output is not None:
                write_new(Path(output), value.model_dump_json(indent=2) + "\n")
            return value
        except (ValueError, OSError, ValidationError):
            raise BacktestClientError("Could not create or save the requested template") from None

    def doctor(
        self, *, workflow: str | None = None, config: ConfigValue | None = None
    ) -> DoctorDiagnostics:
        """Return structured offline diagnostics without printing or modifying files."""
        if (workflow is None) != (config is None):
            raise BacktestClientError("Specify both workflow= and config= to validate a config")
        installed_ok = True
        try:
            installed_version: str | None = importlib.metadata.version("strategy-backtest-agent")
        except importlib.metadata.PackageNotFoundError:
            installed_version, installed_ok = None, False
        from strategy_backtest_agent.doctor import source_metadata

        source_version, _ = source_metadata()
        valid: bool | None = None
        warnings: list[str] = []
        if config is not None and workflow is not None:
            models: dict[str, type[BaseModel]] = {
                "backtest": BacktestConfig,
                "compare": ComparisonConfig,
                "validate": ValidationConfig,
                "sensitivity": SensitivityConfig,
                "costs": CostScenarioConfig,
                "walk-forward": WalkForwardConfig,
            }
            model_type = models.get(workflow)
            if model_type is None:
                raise BacktestClientError("Unknown research workflow for config validation")
            try:
                self._load(model_type, config)
                valid = True
            except BacktestClientError:
                valid = False
                warnings.append("The explicitly supplied configuration is invalid.")
        try:
            demo_candles("1h", 1)
            offline = True
        except (ValueError, OSError, ImportError):
            offline = False
            warnings.append("Synthetic offline data check failed.")
        if not self._api_key.strip():
            warnings.append("Optional AI is unavailable without a key; offline workflows work.")
        if not installed_ok:
            warnings.append("Installed package metadata is unavailable.")
        return DoctorDiagnostics(
            python_version=".".join(map(str, sys.version_info[:3])),
            python_compatible=(3, 12) <= sys.version_info[:2] < (4, 0),
            installed_package_version=installed_version,
            installed_metadata_available=installed_ok,
            source_checkout_version=source_version,
            offline_ready=offline,
            api_key_present=bool(self._api_key.strip()),
            api_key_source=self._key_source,  # type: ignore[arg-type]
            model_configured=bool(self._model.strip()),
            model_source=self._model_source,  # type: ignore[arg-type]
            config_workflow=workflow,
            config_valid=valid,
            warnings=warnings,
        )

    def report(
        self,
        source: ClientResult | BaseModel | ResearchReport | Mapping[str, Any] | str | Path,
        *,
        format: ReportFormat = "markdown",
        output: str | Path | None = None,
        ai: bool = False,
    ) -> str:
        """Render an existing typed result, mapping, report, or JSON file; never reruns."""
        if ai:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                pass
            else:
                raise BacktestClientError(
                    "Use areport(..., ai=True) for AI interpretation inside an event loop"
                )
        try:
            if isinstance(source, ClientResult):
                content = source._source_bytes
                report = build_report(content)
            elif isinstance(source, ResearchReport):
                report = source
            elif isinstance(source, BaseModel):
                report = build_report(self._bytes(source))
            elif isinstance(source, Mapping):
                content = (json.dumps(source, allow_nan=False) + "\n").encode("utf-8")
                report = build_report(content)
            else:
                report = build_report(read_input(Path(source)))
            if ai:
                report = interpret(report, api_key=self._api_key, model=self._model)
            if format == "json":
                rendered = report.model_dump_json() + "\n"
            elif format == "markdown":
                from strategy_backtest_agent.reports.render import markdown

                rendered = markdown(report)
            else:
                raise BacktestClientError("format must be 'markdown' or 'json'")
            if output is not None:
                try:
                    write_new(Path(output), rendered)
                except (OSError, ValueError):
                    raise BacktestClientError(
                        "Could not safely create report output; choose a new file path"
                    ) from None
            return rendered
        except BacktestClientError:
            raise
        except (ValidationError, ValueError, OSError, TypeError, RecursionError):
            raise BacktestClientError(
                "Could not validate or render the supplied research result"
            ) from None

    async def areport(
        self,
        source: ClientResult | BaseModel | ResearchReport | Mapping[str, Any] | str | Path,
        *,
        format: ReportFormat = "markdown",
        output: str | Path | None = None,
        ai: bool = False,
    ) -> str:
        """Await report rendering and optional constrained interpretation."""
        return await asyncio.to_thread(self.report, source, format=format, output=output, ai=ai)
