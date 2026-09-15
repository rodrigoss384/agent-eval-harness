"""Contratos Pydantic expostos pela API."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class EvaluationMethod(StrEnum):
    """Métodos de avaliação disponíveis na fatia representativa."""

    DETERMINISTIC_MATCH = "deterministic_match"
    PROGRAMMATIC_CHECK = "programmatic_check"
    LLM_AS_JUDGE = "llm_as_judge"


class FinalVerdict(StrEnum):
    """Resultado normativo de uma tentativa."""

    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"


class ToolCall(BaseModel):
    """Trace sintético de uma chamada de ferramenta."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class CandidateInput(BaseModel):
    """Resposta fornecida para avaliação offline."""

    output: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    latency_ms: int | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)


class RunRequest(BaseModel):
    """Solicitação de execução para um caso conhecido do dataset."""

    case_id: str
    methods: list[EvaluationMethod] = Field(min_length=1)
    candidate: CandidateInput


class DeterministicRule(BaseModel):
    """Regra auditável aplicada pelo match determinístico."""

    kind: Literal["exact", "regex", "tool_exact", "tool_canonical"]
    expected: str


class ContextChunk(BaseModel):
    """Trecho fechado que pode ser recuperado pelo agente."""

    id: str
    text: str


class DeterministicAssertion(BaseModel):
    """Fato verificável sem julgamento probabilístico."""

    id: str
    description: str
    pattern: str
    critical: bool = True
    weight: float = Field(default=1, gt=0)


class RetrievalSpec(BaseModel):
    """Ground truth da recuperação lexical."""

    top_k: int = Field(default=3, ge=1, le=10)
    expected_context_ids: list[str] = Field(min_length=1)


class ToolSpec(BaseModel):
    """Contrato fechado de uma ferramenta sintética, sem execução externa."""

    name: str
    description: str
    parameters: dict[str, Any]
    canonical_aliases: list[str] = Field(default_factory=list)
    expected_arguments: dict[str, Any] = Field(default_factory=dict)


class MetricLimits(BaseModel):
    """Limites opcionais que tornam métricas programáticas normativas."""

    latency_ms: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)


class DatasetCase(BaseModel):
    """Caso sintético com ground truth explícito."""

    id: str
    category: Literal["factual", "retrieval", "tool_use"]
    input: str
    expected_output: str
    domain: str = "geral"
    difficulty: Literal["basic", "intermediate", "advanced"] = "basic"
    reference_context: list[ContextChunk] = Field(default_factory=list)
    expected_tool: str | None = None
    deterministic_rule: DeterministicRule
    correctness_definition: str
    rubric: list[str]
    threshold: float = Field(ge=0, le=1)
    deterministic_assertions: list[DeterministicAssertion] = Field(default_factory=list)
    forbidden_patterns: list[str] = Field(default_factory=list)
    retrieval: RetrievalSpec | None = None
    tool: ToolSpec | None = None
    metric_limits: MetricLimits = Field(default_factory=MetricLimits)


class EvaluationResult(BaseModel):
    """Resultado completo de um método de avaliação."""

    method: EvaluationMethod
    status: Literal["passed", "failed", "observed", "unavailable", "error"]
    correctness_definition: str
    passed: bool | None = None
    reason: str
    expected: str | None = None
    actual: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    judge_model: str | None = None
    rubric: list[str] = Field(default_factory=list)
    score: float | None = Field(default=None, ge=0, le=1)
    threshold: float | None = Field(default=None, ge=0, le=1)


class RunMetrics(BaseModel):
    """Métricas do candidato sem estimativas monetárias ocultas."""

    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    cost_usd: float | None
    cost_status: Literal["reported", "estimated", "unavailable"]
    cost_source: Literal["provider_response", "pricing_catalog", "none"]
    time_to_first_token_ms: int | None = None
    generation_ms: int | None = None
    judge_ms: int | None = None
    total_latency_ms: int | None = None
    cost_formula: str | None = None
    pricing_version: str | None = None


class RunVerdict(BaseModel):
    """Veredito persistido e renderizado integralmente pela interface."""

    run_id: str
    case_id: str
    created_at: datetime
    run_status: Literal["completed", "partial", "failed"]
    final_verdict: FinalVerdict
    candidate_origin: Literal["supplied_trace", "live_model"]
    agent_input: str
    agent_output: str
    tool_calls: list[ToolCall]
    evaluations: list[EvaluationResult]
    metrics: RunMetrics
    session_id: str | None = None
    trial_index: int | None = Field(default=None, ge=1, le=3)
    agent_provider: str | None = None
    agent_model: str | None = None
    judge_provider: str | None = None
    judge_model: str | None = None
    retrieved_context: list[dict[str, Any]] = Field(default_factory=list)


class SessionRequest(BaseModel):
    """Cria uma execução live de um caso ou suíte fechada."""

    mode: Literal["single", "suite"] = "single"
    dataset_id: str = "builtin-v2"
    case_ids: list[str] = Field(min_length=1, max_length=500)
    methods: list[EvaluationMethod] = Field(
        default_factory=lambda: [
            EvaluationMethod.DETERMINISTIC_MATCH,
            EvaluationMethod.LLM_AS_JUDGE,
            EvaluationMethod.PROGRAMMATIC_CHECK,
        ]
    )
    judge_role: Literal["judge", "judge_alt"] = "judge_alt"
    pricing_profiles: dict[str, Literal["standard", "free", "paid_standard"]] = Field(
        default_factory=dict
    )
    concurrency: int = Field(default=2, ge=1, le=4)
    trials: Literal[3] = 3


class SessionAccepted(BaseModel):
    """Confirma que a sessão foi persistida antes da execução."""

    session_id: str
    status: Literal["queued"] = "queued"
    events_url: str
    calls_planned: int


class DatasetMetadata(BaseModel):
    """Metadados públicos de um dataset fechado ou importado."""

    dataset_id: str
    name: str
    source: Literal["builtin", "imported"]
    data_classification: Literal["synthetic"] = "synthetic"
    case_count: int
    checksum: str
    created_at: datetime


class DatasetDocument(BaseModel):
    """Dataset completo validado antes da persistência."""

    metadata: DatasetMetadata
    cases: list[DatasetCase]


class DatasetImportRequest(BaseModel):
    """Importa JSONL sintético sem receber arquivos fora da API interna."""

    name: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1)
    data_classification: Literal["synthetic"] = "synthetic"


class SessionSummary(BaseModel):
    """Agregação explícita de estabilidade, tempo, tokens e custo."""

    session_id: str
    total_cases: int
    total_runs: int
    stable_passes: int
    stable_fails: int
    unstable: int
    inconclusive: int
    stable_pass_rate: float
    latency_p50_ms: int | None
    latency_p95_ms: int | None
    total_tokens: int
    known_cost_usd: float
    runs_without_cost: int
    judge_scores: list[float]


class EvaluationSession(BaseModel):
    """Snapshot durável do progresso de uma avaliação live."""

    session_id: str
    created_at: datetime
    updated_at: datetime
    status: Literal[
        "queued", "running", "completed", "partial", "failed", "cancelled", "interrupted"
    ]
    request: SessionRequest
    runs: list[RunVerdict] = Field(default_factory=list)
    case_statuses: dict[str, Literal["stable_pass", "stable_fail", "unstable", "inconclusive"]] = (
        Field(default_factory=dict)
    )
    final_verdict: FinalVerdict = FinalVerdict.INCONCLUSIVE
    current_case_id: str | None = None
    current_trial: int | None = None
    error: str | None = None
    event_cursor: int = 0


class BiasAuditRequest(BaseModel):
    """Solicitação de auditoria live sobre um caso fechado."""

    dataset_id: str = "builtin-v2"
    case_id: str = "case_retrieval_advanced_001"
    pricing_profiles: dict[str, Literal["standard", "free", "paid_standard"]] = Field(
        default_factory=dict
    )


class BiasAuditAccepted(BaseModel):
    """Confirma persistência e início assíncrono da auditoria."""

    audit_id: str
    status: Literal["queued"] = "queued"
    events_url: str
    calls_planned: int


class BiasAudit(BaseModel):
    """Resultado auditável de um experimento de viés."""

    audit_id: str
    experiment: Literal["position", "self_preference", "verbosity", "correctness_definition"]
    created_at: datetime
    updated_at: datetime
    status: Literal["queued", "running", "completed", "failed", "cancelled", "interrupted"]
    result: Literal["detected", "not_detected", "inconclusive"] = "inconclusive"
    hypothesis: str
    protocol: str
    calls_planned: int
    measurements: dict[str, Any] = Field(default_factory=dict)
    delta: float | None = None
    limitations: list[str] = Field(default_factory=list)
    error: str | None = None
    event_cursor: int = 0


class HealthResponse(BaseModel):
    """Estado mínimo das dependências locais."""

    status: Literal["ok"] = "ok"
    database: Literal["ready"] = "ready"
    version: str = "1.0.0"


class ModelRoleStatus(BaseModel):
    """Configuração pública de um papel, sem credenciais."""

    role: Literal["agent", "judge", "judge_alt"]
    provider: str | None
    model: str | None
    configured: bool
    base_url: str | None


def utc_now() -> datetime:
    """Produz timestamps timezone-aware para persistência e API."""
    return datetime.now(UTC)
