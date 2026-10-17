"""Versioned, strict normalized evidence and output contracts."""

from datetime import UTC, datetime
from typing import Final, Literal

from pydantic import AwareDatetime, Field, JsonValue, field_validator

from strategy_backtest_agent.models import ExecutionConfig, StrictModel

ResearchType = Literal[
    "backtest", "comparison", "validation", "sensitivity", "costs", "walk_forward"
]
Unit = Literal["%", "pp", "bps", "quote_currency", "count", "fraction", "ratio", "index"]
REPORT_VERSION: Final = "1.0"
GENERATOR_VERSION: Final = "research-reports/1"


class ResearchSource(StrictModel):
    research_type: ResearchType
    adapter_version: str
    input_schema_version: str | None
    data_source: str | None
    evaluation_start: AwareDatetime | None
    evaluation_end: AwareDatetime | None
    evaluation_boundary_policy: str
    input_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candle_sha256: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    provenance_note: str = (
        "Structural and consistency validation does not authenticate data or results. "
        "A supplied candle hash is source metadata, not proof of truthful research."
    )

    @field_validator("evaluation_start", "evaluation_end")
    @classmethod
    def utc_boundaries(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(UTC) if value is not None else None


class EvidenceMetric(StrictModel):
    id: str
    scope: str
    name: str
    value: int | float | None
    unit: Unit
    source_path: str
    context: str


class EvidenceScope(StrictModel):
    id: str
    label: str
    role: Literal[
        "overall",
        "strategy",
        "train",
        "test",
        "variant_train",
        "scenario_train",
        "oos_summary",
        "stitched_index",
    ]
    start: AwareDatetime | None
    end: AwareDatetime | None
    strategy: dict[str, JsonValue] | None
    execution: ExecutionConfig | None

    @field_validator("start", "end")
    @classmethod
    def utc_boundaries(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(UTC) if value is not None else None


class EvidenceObservation(StrictModel):
    id: str
    kind: Literal[
        "historical_return", "benchmark", "drawdown", "low_trades", "oos", "grid", "costs"
    ]
    text: str
    evidence_ids: list[str]


class EvidenceLimitation(StrictModel):
    id: str
    text: str
    source_path: str | None


class ResearchEvidence(StrictModel):
    source: ResearchSource
    configuration: dict[str, JsonValue]
    reproducibility_metadata: dict[str, JsonValue]
    scopes: list[EvidenceScope]
    metrics: list[EvidenceMetric]
    limitations: list[EvidenceLimitation]
    methodology: list[str]
    source_notes: list[str]


class AINumericReference(StrictModel):
    evidence_id: str
    value: int | float | None
    unit: Unit


ExplanationCode = Literal[
    "historical_context",
    "benchmark_context",
    "cost_context",
    "oos_context",
    "grid_context",
    "limited_trades",
]


class AIStatement(StrictModel):
    observation_id: str
    explanation_code: ExplanationCode
    text: str = Field(max_length=500)
    evidence_ids: list[str] = Field(min_length=1, max_length=1000)
    numeric_references: list[AINumericReference] = Field(max_length=1000)


class AIInterpretation(StrictModel):
    statements: list[AIStatement] = Field(min_length=1, max_length=8)
    research_questions: list[
        Literal["unseen_history", "cost_assumptions", "predeclared_protocol"]
    ] = Field(max_length=3)


class AIMetadata(StrictModel):
    requested_model: str
    response_model: str | None


class ResearchReport(StrictModel):
    report_schema_version: Literal["1.0"] = REPORT_VERSION
    generator_version: Literal["research-reports/1"] = GENERATOR_VERSION
    status: Literal["deterministic", "ai_accepted", "ai_unavailable", "ai_rejected"] = (
        "deterministic"
    )
    evidence: ResearchEvidence
    evidence_sha256: str
    observations: list[EvidenceObservation]
    ai_interpretation: AIInterpretation | None = None
    ai_metadata: AIMetadata | None = None
    warnings: list[str] = Field(default_factory=list)
