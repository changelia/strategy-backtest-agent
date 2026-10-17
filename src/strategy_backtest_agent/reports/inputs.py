"""Bounded untrusted JSON parsing and explicit unversioned-v0.9 schema adapters."""

import hashlib
import json
import math
import os
import stat
from pathlib import Path
from typing import Any, Literal

from pydantic import AwareDatetime, Field, JsonValue

from strategy_backtest_agent.ai.models import AIStrategyConfig
from strategy_backtest_agent.comparison.models import ComparisonResult
from strategy_backtest_agent.costs.models import CostScenarioReport
from strategy_backtest_agent.models import BacktestResult, RSIStrategy, StrictModel
from strategy_backtest_agent.rules.models import (
    IndicatorInitialization,
    RuleStrategy,
    TechnicalIndicator,
)
from strategy_backtest_agent.sensitivity.models import SensitivityReport
from strategy_backtest_agent.validation.models import ValidationReport
from strategy_backtest_agent.walk_forward.models import WalkForwardReport

MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_NODES = 250000
MAX_DEPTH = 32
MAX_STRING = 8192


class LegacyCLISettings(StrictModel):
    name: Literal["RSI"]
    rsi_period: int = Field(ge=1)
    entry_rsi: float = Field(ge=0, le=100)
    exit_rsi: float = Field(ge=0, le=100)
    fee: float = Field(ge=0, lt=1)


class EvaluationPeriod(StrictModel):
    requested_start: AwareDatetime
    requested_end: AwareDatetime
    warmup_candles: int = Field(ge=0)
    required_warmup_candles: int = Field(ge=0)
    ema_policy: str


class CLIBacktest(BacktestResult):
    symbol: str = Field(pattern=r"^[A-Z0-9]{5,20}$")
    timeframe: str
    period_days: int = Field(gt=0)
    data_source: str
    candle_count: int = Field(gt=0)
    start_time: AwareDatetime
    end_time: AwareDatetime
    strategy: LegacyCLISettings | RuleStrategy
    trading_fee: float | None = None
    indicator_configuration: list[TechnicalIndicator] | None = None
    indicator_initializations: list[IndicatorInitialization] | None = None
    evaluation_period: EvaluationPeriod | None = None


class AIBacktest(StrictModel):
    input: str
    parsed_strategy: AIStrategyConfig
    backtest_result: CLIBacktest


ResearchInput = (
    CLIBacktest
    | ComparisonResult
    | ValidationReport
    | SensitivityReport
    | CostScenarioReport
    | WalkForwardReport
)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object keys are unsupported")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ValueError("JSON numbers must be finite")


def parse_input(content: bytes) -> dict[str, Any]:
    if not content or len(content) > MAX_INPUT_BYTES:
        raise ValueError("input must be nonempty and at most 16 MiB")
    try:
        value = json.loads(
            content.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant
        )
    except (UnicodeError, RecursionError, json.JSONDecodeError) as exc:
        raise ValueError("invalid UTF-8 JSON or excessive nesting") from exc
    count = 0

    def visit(item: Any, depth: int) -> None:
        nonlocal count
        count += 1
        if count > MAX_NODES or depth > MAX_DEPTH:
            raise ValueError("research JSON exceeds node/depth limits")
        if isinstance(item, str) and (
            len(item) > MAX_STRING or any(ord(c) < 32 and c not in "\n\r\t" for c in item)
        ):
            raise ValueError("research JSON has oversized text or control characters")
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("JSON numbers must be finite")
        if isinstance(item, dict):
            for key, child in item.items():
                visit(key, depth + 1)
                visit(child, depth + 1)
        elif isinstance(item, list):
            for child in item:
                visit(child, depth + 1)

    visit(value, 0)
    if not isinstance(value, dict):
        raise ValueError("input must be one research JSON object, not a multi-file array")
    return value


def read_input(path: Path) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("research input must be a regular JSON file")
        return stream.read(MAX_INPUT_BYTES + 1)


def adapt(raw: dict[str, Any]) -> tuple[ResearchInput, str, str]:
    """Adapter names version our reader; sources themselves have no schema version."""
    signatures = [
        ("walk_forward", "folds"),
        ("sensitivity", "variants"),
        ("costs", "baseline_id"),
        ("comparison", "ranking"),
        ("validation", "return_gap_pp"),
    ]
    kinds = [kind for kind, key in signatures if key in raw]
    if "split" in raw and not kinds:
        kinds.append("validation")
    if "backtest_result" in raw or "start_time" in raw:
        kinds.append("backtest")
    if len(kinds) != 1:
        raise ValueError("unsupported or ambiguous research schema; use one v0.9 CLI --json result")
    kind = kinds[0]
    encoded = canonical_bytes(raw)
    if kind == "backtest":
        if "backtest_result" in raw:
            wrapped = AIBacktest.model_validate_json(encoded, strict=True)
            result = wrapped.backtest_result
            parsed = wrapped.parsed_strategy
            if (
                parsed.symbol != result.symbol
                or parsed.timeframe != result.timeframe
                or parsed.period_days != result.period_days
                or parsed.initial_balance != result.initial_balance
                or parsed.execution_config() != result.execution
            ):
                raise ValueError("AI parsed configuration contradicts its backtest result")
            if isinstance(result.strategy, RuleStrategy) and parsed.strategy != result.strategy:
                raise ValueError("AI strategy contradicts the reported rule strategy")
            if isinstance(result.strategy, LegacyCLISettings):
                if not isinstance(parsed.strategy, RSIStrategy) or (
                    parsed.strategy.period,
                    parsed.strategy.entry_below,
                    parsed.strategy.exit_above,
                ) != (
                    result.strategy.rsi_period,
                    result.strategy.entry_rsi,
                    result.strategy.exit_rsi,
                ):
                    raise ValueError("AI legacy configuration contradicts reported RSI settings")
            return result, "sba-v0.9-ai-backtest/1", "/backtest_result"
        return CLIBacktest.model_validate_json(encoded, strict=True), "sba-v0.9-backtest/1", ""
    models: dict[
        str,
        type[ComparisonResult]
        | type[ValidationReport]
        | type[SensitivityReport]
        | type[CostScenarioReport]
        | type[WalkForwardReport],
    ] = {
        "comparison": ComparisonResult,
        "validation": ValidationReport,
        "sensitivity": SensitivityReport,
        "costs": CostScenarioReport,
        "walk_forward": WalkForwardReport,
    }
    model = models[kind]
    if not set(model.model_fields) <= raw.keys():
        raise ValueError("missing required v0.9 report fields; use complete CLI --json output")
    shared = raw.get("shared_data")
    from strategy_backtest_agent.comparison.models import SharedData

    if not isinstance(shared, dict) or not set(SharedData.model_fields) <= shared.keys():
        raise ValueError("missing required v0.9 shared-data provenance fields")
    return model.model_validate_json(encoded, strict=True), f"sba-v0.9-{kind}/1", ""


def json_object(value: dict[str, Any]) -> dict[str, JsonValue]:
    # Internal typed models have already excluded unsupported non-JSON objects.
    return value
