"""Snapshots duráveis do protocolo pareado e do orçamento."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.models import DatasetCase, EvaluationMethod, EvaluationResult, ToolCall, utc_now


class BenchmarkSample(BaseModel):
    id: str
    case: DatasetCase
    output: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    expected_passed: bool
    label_reason: str


class BenchmarkRequest(BaseModel):
    case_ids: list[str] | None = Field(default=None, min_length=1, max_length=24)
    confirm_paid: Literal[True]
    max_calls: int = Field(default=300, ge=1, le=300)
    max_cost_usd: float = Field(default=2, gt=0, le=2, allow_inf_nan=False)


class BenchmarkCall(BaseModel):
    sample_id: str
    trial_index: int
    method: EvaluationMethod
    status: Literal["reserved", "completed", "error", "interrupted"] = "reserved"
    reserved_usd: float
    accounted_usd: float
    accounting: Literal["reservation", "reported", "estimated"] = "reservation"
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    result: EvaluationResult | None = None


class BenchmarkTrial(BaseModel):
    sample_id: str
    trial_index: int
    evaluations: list[EvaluationResult] = Field(default_factory=list)


class Benchmark(BaseModel):
    benchmark_id: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    status: Literal[
        "queued",
        "running",
        "completed",
        "partial",
        "failed",
        "cancelled",
        "interrupted",
        "budget_exhausted",
    ] = "queued"
    request: BenchmarkRequest
    protocol_version: str = "paired-judges-v1"
    dataset_version: str = "paired-candidates-v1"
    dataset_checksum: str
    samples: list[BenchmarkSample]
    calls_planned: int
    calls: list[BenchmarkCall] = Field(default_factory=list)
    runs: list[BenchmarkTrial] = Field(default_factory=list)
    accounted_usd: float = 0
    error: str | None = None
    recorded: bool = False
    configuration: dict[str, Any] = Field(default_factory=dict)


class BenchmarkAccepted(BaseModel):
    benchmark_id: str
    status: str
    calls_planned: int
    events_url: str
