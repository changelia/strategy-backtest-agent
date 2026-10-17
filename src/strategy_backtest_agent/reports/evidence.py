"""Lossless metric extraction and explicitly defined descriptive observations."""

from typing import Any

from strategy_backtest_agent.comparison.models import ComparisonResult
from strategy_backtest_agent.costs.models import CostScenarioReport
from strategy_backtest_agent.reports.inputs import (
    CLIBacktest,
    ResearchInput,
    adapt,
    canonical_bytes,
    digest,
    parse_input,
)
from strategy_backtest_agent.reports.models import (
    EvidenceLimitation,
    EvidenceMetric,
    EvidenceObservation,
    EvidenceScope,
    ResearchEvidence,
    ResearchReport,
    ResearchSource,
    ResearchType,
    Unit,
)
from strategy_backtest_agent.reports.validation import Segment, check_research
from strategy_backtest_agent.rules.history import interval_duration
from strategy_backtest_agent.sensitivity.models import SensitivityReport
from strategy_backtest_agent.validation.models import ValidationReport
from strategy_backtest_agent.walk_forward.models import WalkForwardReport

METRICS: tuple[tuple[str, str, Unit], ...] = (
    ("initial_balance", "initial_balance", "quote_currency"),
    ("final_balance", "final_balance", "quote_currency"),
    ("total_return", "total_return_percent", "%"),
    ("net_buy_and_hold", "buy_and_hold_return_percent", "%"),
    ("max_drawdown", "max_drawdown_percent", "%"),
    ("completed_trades", "total_trades", "count"),
    ("winning_trades", "winning_trades", "count"),
    ("losing_trades", "losing_trades", "count"),
    ("win_rate", "win_rate", "%"),
    ("profit_factor", "profit_factor", "ratio"),
)


def metric(
    scope: str, name: str, value: int | float | None, unit: Unit, path: str, context: str
) -> EvidenceMetric:
    return EvidenceMetric(
        id=f"{scope}.{name}",
        scope=scope,
        name=name,
        value=value,
        unit=unit,
        source_path=path,
        context=context,
    )


def segment_metrics(segment: Segment) -> list[EvidenceMetric]:
    result, scope, path = segment.result, segment.scope.id, segment.path
    context = "Supplied historical segment metric; independent full-cash portfolio."
    rows = [
        metric(scope, name, getattr(result, field), unit, path + "/" + field, context)
        for name, field, unit in METRICS
    ]
    rows.append(
        metric(
            scope,
            "net_pnl",
            result.final_balance - result.initial_balance,
            "quote_currency",
            path + "/final_balance",
            "Derived final_balance minus initial_balance; verified against supplied trade PnL.",
        )
    )
    if segment.excess_path:
        rows.append(
            metric(
                scope,
                "excess_return",
                segment.excess,
                "pp",
                segment.excess_path,
                "Strategy return minus net Buy & Hold return, in percentage points.",
            )
        )
    for field in ("fees", "modeled_spread_cost", "modeled_slippage_cost"):
        rows.append(
            metric(
                scope,
                field,
                getattr(result.costs, field),
                "quote_currency",
                path + "/costs/" + field,
                "Fees charged or illustrative fill adjustments; not observed market costs.",
            )
        )
        if result.benchmark_costs is not None:
            rows.append(
                metric(
                    scope,
                    "benchmark_" + field,
                    getattr(result.benchmark_costs, field),
                    "quote_currency",
                    path + "/benchmark_costs/" + field,
                    "Benchmark attribution under the same declared execution model.",
                )
            )
    assert result.execution is not None
    assumptions: list[tuple[str, float, Unit]] = [
        ("fee_per_side", result.execution.fee_rate, "fraction"),
        ("full_spread", result.execution.spread_bps, "bps"),
        ("slippage_per_side", result.execution.slippage_bps, "bps"),
    ]
    for name, value, unit in assumptions:
        field = {
            "fee_per_side": "fee_rate",
            "full_spread": "spread_bps",
            "slippage_per_side": "slippage_bps",
        }[name]
        rows.append(
            metric(
                scope,
                name,
                value,
                unit,
                path + "/execution/" + field,
                "Declared execution assumption.",
            )
        )
    return rows


def _source(
    data: ResearchInput, raw: dict[str, Any], content: bytes, adapter: str
) -> ResearchSource:
    kind: ResearchType
    if isinstance(data, CLIBacktest):
        kind = "backtest"
        start, end = data.start_time, data.end_time + interval_duration(data.timeframe)
        source, candle_hash = data.data_source, None
        policy = (
            "Actual completed candles: CLI start/end are candle opens; "
            "normalized end = last open + timeframe."
        )
    else:
        kind = (
            "comparison"
            if isinstance(data, ComparisonResult)
            else "validation"
            if isinstance(data, ValidationReport)
            else "sensitivity"
            if isinstance(data, SensitivityReport)
            else "costs"
            if isinstance(data, CostScenarioReport)
            else "walk_forward"
        )
        shared = data.shared_data
        start, end = shared.evaluation_start, shared.evaluation_end
        source, candle_hash = shared.source, shared.candles_sha256
        policy = (
            "Source requested UTC evaluation range; scopes contain actual "
            "half-open completed-candle segments."
        )
    return ResearchSource(
        research_type=kind,
        adapter_version=adapter,
        input_schema_version=None,
        data_source=source,
        evaluation_start=start,
        evaluation_end=end,
        evaluation_boundary_policy=policy,
        input_content_sha256=digest(content),
        canonical_input_sha256=digest(canonical_bytes(raw)),
        candle_sha256=candle_hash,
    )


def observations(evidence: ResearchEvidence) -> list[EvidenceObservation]:
    rows: list[EvidenceObservation] = []

    def add(kind: Any, ids: list[str], text: str) -> None:
        rows.append(
            EvidenceObservation(
                id=f"observation.{len(rows) + 1:04d}", kind=kind, text=text, evidence_ids=ids
            )
        )

    metrics = {m.id: m for m in evidence.metrics}
    for scope in evidence.scopes:
        if scope.role == "oos_summary":
            count = metrics[f"{scope.id}.fold_count"]
            positive = metrics[f"{scope.id}.positive_test_folds"]
            median = metrics[f"{scope.id}.median_test_return_percent"]
            add(
                "oos",
                [positive.id, count.id],
                f"{scope.id}: {positive.value} of {count.value} independent Test folds "
                "had positive historical returns.",
            )
            add(
                "oos",
                [median.id],
                f"{scope.id}: median Test return was "
                + (
                    "positive."
                    if median.value is not None and median.value > 0
                    else "negative."
                    if median.value is not None and median.value < 0
                    else "zero."
                ),
            )
        value = metrics.get(f"{scope.id}.total_return")
        if value is not None:
            direction = (
                "positive"
                if value.value is not None and value.value > 0
                else "negative"
                if value.value is not None and value.value < 0
                else "zero"
            )
            add(
                "historical_return",
                [value.id],
                f"{scope.id}: historical net return was {direction}; "
                "this is descriptive, not predictive evidence.",
            )
        benchmark = metrics.get(f"{scope.id}.excess_return")
        if benchmark is not None and benchmark.value is not None:
            direction = (
                "above" if benchmark.value > 0 else "below" if benchmark.value < 0 else "equal to"
            )
            add(
                "benchmark",
                [benchmark.id],
                f"{scope.id}: historical return was {direction} net Buy & Hold.",
            )
        trades = metrics.get(f"{scope.id}.completed_trades")
        if trades is not None and trades.value is not None and trades.value < 5:
            add(
                "low_trades",
                [trades.id],
                f"{scope.id}: fewer than five completed trades; "
                "limited trade evidence is not proof of stability.",
            )
        drawdown = metrics.get(f"{scope.id}.max_drawdown")
        if drawdown is not None and drawdown.value is not None and drawdown.value < 0:
            add(
                "drawdown",
                [drawdown.id],
                f"{scope.id}: sampled historical equity experienced a drawdown.",
            )
    if evidence.source.research_type == "sensitivity":
        grid = metrics["summary.grid.positive_return_percent"]
        add(
            "grid",
            [grid.id],
            "The declared Train-only grid contained no positive-return variants."
            if grid.value == 0
            else (
                "The declared Train-only grid contained positive historical "
                "returns; no variant is selected or recommended."
            ),
        )
    if evidence.source.research_type == "costs":
        for item in evidence.metrics:
            if item.name == "return_difference" and item.value is not None:
                add(
                    "costs",
                    [item.id],
                    f"{item.scope}: historical net return was "
                    + (
                        "lower than"
                        if item.value < 0
                        else "higher than"
                        if item.value > 0
                        else "equal to"
                    )
                    + " the declared baseline under these execution assumptions.",
                )
    return rows


def build_report(content: bytes) -> ResearchReport:
    raw = parse_input(content)
    data, adapter, prefix = adapt(raw)
    segments = check_research(data, raw, prefix)
    source = _source(data, raw, content, adapter)
    scopes = [s.scope for s in segments]
    values = [m for segment in segments for m in segment_metrics(segment)]
    configuration = (
        data.strategy.model_dump(mode="json")
        if isinstance(data, CLIBacktest)
        else data.configuration.model_dump(mode="json")
    )
    if isinstance(data, CLIBacktest):
        configuration = {
            "symbol": data.symbol,
            "timeframe": data.timeframe,
            "period_days": data.period_days,
            "strategy": data.strategy.model_dump(mode="json"),
            "evaluation_period": data.evaluation_period.model_dump(mode="json")
            if data.evaluation_period
            else None,
        }
    if isinstance(data, ValidationReport):
        for index, row in enumerate(data.results):
            values.append(
                metric(
                    f"strategy.{row.id}.test",
                    "return_gap",
                    row.return_gap_pp,
                    "pp",
                    f"/results/{index}/return_gap_pp",
                    "Test return minus Train return; durations may differ and are not annualized.",
                )
            )
    if isinstance(data, CostScenarioReport):
        for index, cost_row in enumerate(data.results):
            values.append(
                metric(
                    f"scenario.{cost_row.id}.train",
                    "return_difference",
                    cost_row.return_difference_pp,
                    "pp",
                    f"/results/{index}/return_difference_pp",
                    "Scenario return minus declared baseline; Train only.",
                )
            )
    if isinstance(data, SensitivityReport):
        scopes.append(
            EvidenceScope(
                id="summary.grid",
                label="Declared sensitivity grid",
                role="overall",
                start=data.split.train_start,
                end=data.split.train_end,
                strategy=None,
                execution=None,
            )
        )
        for field in type(data.summary).model_fields:
            value = getattr(data.summary, field)
            if isinstance(value, list):
                continue
            unit: Unit = (
                "count"
                if field in ("variant_count", "minimum_observation_trades")
                else "pp"
                if field.endswith("_pp")
                else "%"
            )
            values.append(
                metric(
                    "summary.grid",
                    field,
                    value,
                    unit,
                    "/summary/" + field,
                    "Declared Train-only grid statistic; no independent Test evaluation.",
                )
            )
    if isinstance(data, WalkForwardReport):
        for index, summary in enumerate(data.summaries):
            scope = f"summary.strategy.{summary.strategy_id}.oos"
            scopes.append(
                EvidenceScope(
                    id=scope,
                    label=summary.strategy_id,
                    role="oos_summary",
                    start=data.folds[0].test_start,
                    end=data.folds[-1].test_end,
                    strategy=None,
                    execution=data.configuration.execution_config(),
                )
            )
            for field in type(summary).model_fields:
                if field in ("strategy_id", "stitched_oos_index"):
                    continue
                unit = (
                    "pp"
                    if field.endswith("_pp")
                    else "%"
                    if field.endswith("_percent")
                    else "fraction"
                    if field.endswith("_fraction")
                    else "count"
                )
                values.append(
                    metric(
                        scope,
                        field,
                        getattr(summary, field),
                        unit,
                        f"/summaries/{index}/{field}",
                        (
                            "Test-only independent-fold statistic; median drawdown is not "
                            "continuous-portfolio drawdown."
                        ),
                    )
                )
            if summary.stitched_oos_index is not None:
                for offset, point in enumerate(summary.stitched_oos_index):
                    point_scope = f"{scope}.index.{offset:03d}"
                    scopes.append(
                        EvidenceScope(
                            id=point_scope,
                            label="Independent Test fold-endpoint index",
                            role="stitched_index",
                            start=point.time,
                            end=point.time,
                            strategy=None,
                            execution=None,
                        )
                    )
                    values.append(
                        metric(
                            point_scope,
                            "value",
                            point.value,
                            "index",
                            f"/summaries/{index}/stitched_oos_index/{offset}/value",
                            (
                                "Normalized independent Test returns compounded at fold "
                                "endpoints; no carried positions or intrafold curve."
                            ),
                        )
                    )
    limitations = [
        EvidenceLimitation(
            id="limitation.historical",
            text=(
                "Historical results do not predict returns, establish safety, "
                "statistical significance or robustness."
            ),
            source_path=None,
        ),
        EvidenceLimitation(
            id="limitation.provenance", text=source.provenance_note, source_path=None
        ),
        EvidenceLimitation(
            id="limitation.execution",
            text=(
                "Spread/slippage are modeled assumptions; full fills and "
                "unlimited liquidity are assumed. Drawdown samples opens/closes."
            ),
            source_path=None,
        ),
        EvidenceLimitation(
            id="limitation.validation",
            text=(
                "Consistency checks cannot verify prices, indicators, signal "
                "correctness or drawdown paths without original candles/equity. "
                "No backtest is rerun."
            ),
            source_path=None,
        ),
    ]
    if isinstance(data, ValidationReport | WalkForwardReport):
        limitations.append(
            EvidenceLimitation(
                id="limitation.holdout",
                text=(
                    "Held-out validity depends on freezing rules before inspecting "
                    "the same history; repeated inspection can contaminate Test."
                ),
                source_path=None,
            )
        )
    if isinstance(data, SensitivityReport | CostScenarioReport):
        limitations.append(
            EvidenceLimitation(
                id="limitation.train_only",
                text=(
                    "Train-only research. Test is reserved and not evaluated by this "
                    "workflow; no independent OOS claim is supported."
                ),
                source_path=None,
            )
        )
    if isinstance(data, WalkForwardReport):
        limitations.append(
            EvidenceLimitation(
                id="limitation.stitch",
                text=(
                    "Stitched OOS is a fold-endpoint index of fresh-capital Test "
                    "portfolios, not continuous execution with carried positions."
                ),
                source_path=None,
            )
        )
    warnings = []
    if source.candle_sha256 is None:
        warnings.append(
            "Input has no candle SHA256; candle provenance is unavailable, not inferred."
        )
    method = [
        (
            "Only the supplied single research result is analyzed; no "
            "market-data fetch or backtest execution."
        ),
        (
            "Numbers are copied from validated results; derived net PnL is "
            "final minus initial balance."
        ),
        (
            "Benchmark is net first evaluation open to final close under the "
            "same execution assumptions."
        ),
        (
            "Undefined metrics remain null; no pooled win rate/profit factor "
            "or continuous OOS drawdown is invented."
        ),
    ]
    if isinstance(data, SensitivityReport | CostScenarioReport):
        method.append("Train only; no Test results are present.")
    if isinstance(data, ValidationReport | WalkForwardReport):
        method.append(
            "Each Train and Test segment starts with fresh capital; no "
            "signals/positions cross segment ends."
        )
    notes = getattr(data, "methodology_warnings", [])
    evidence = ResearchEvidence(
        source=source,
        configuration=configuration,
        reproducibility_metadata={
            **data.shared_data.model_dump(mode="json", exclude_unset=True),
            # Preserve absent legacy fields rather than presenting Pydantic
            # defaults as provenance supplied by the original research file.
            **(
                {
                    "indicator_initializations": [
                        anchor.model_dump(mode="json", exclude_unset=True)
                        for anchor in data.shared_data.indicator_initializations
                    ]
                }
                if "indicator_initializations" in data.shared_data.model_fields_set
                else {}
            ),
        }
        if not isinstance(data, CLIBacktest)
        else {
            "indicator_configuration": [
                s.model_dump(mode="json") for s in data.indicator_configuration
            ]
            if data.indicator_configuration is not None
            else None,
            "indicator_initializations": [
                s.model_dump(mode="json") for s in data.indicator_initializations
            ]
            if data.indicator_initializations is not None
            else None,
            "evaluation_period": data.evaluation_period.model_dump(mode="json")
            if data.evaluation_period is not None
            else None,
        },
        scopes=scopes,
        metrics=values,
        limitations=limitations,
        methodology=method,
        source_notes=notes,
    )
    ids = [m.id for m in values]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate normalized evidence IDs")
    return ResearchReport(
        evidence=evidence,
        evidence_sha256=digest(canonical_bytes(evidence.model_dump(mode="json"))),
        observations=observations(evidence),
        warnings=warnings,
    )
