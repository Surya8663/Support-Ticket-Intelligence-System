from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ErrorResponse(BaseModel):
    error: str
    detail: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["connected", "missing"]
    groq_configured: bool
    row_count: int
    reference_now: str | None = None
    auth_required: bool = False
    sql_timeout_seconds: float | None = None


class NumericSummary(BaseModel):
    count: int
    mean: float | None = None
    median: float | None = None
    min: float | None = None
    max: float | None = None


class AnomalyCounts(BaseModel):
    resolution_outlier: int = 0
    sla_breach: int = 0


class StatsResponse(BaseModel):
    row_count: int
    reference_now: str | None
    by_status: dict[str, int]
    by_priority: dict[str, int]
    by_category: dict[str, int]
    by_agent: dict[str, int]
    resolution_time_hrs: NumericSummary
    customer_rating: NumericSummary
    anomaly_counts: AnomalyCounts


class AnomalyOut(BaseModel):
    ticket_id: str
    anomaly_type: Literal["resolution_outlier", "sla_breach"]
    metric_name: str
    metric_value: float | None = None
    threshold: float | None = None
    reason: str
    created_at: str
    category: str
    priority: str
    status: str


class AnomaliesResponse(BaseModel):
    count: int
    method: Literal["iqr", "zscore"]
    reference_now: str | None
    anomalies: list[AnomalyOut] = Field(default_factory=list)


class TicketOut(BaseModel):
    ticket_id: str
    created_at: str
    category: str
    priority: str
    status: str
    response_time_hrs: float | None = None
    resolution_time_hrs: float | None = None
    agent_id: str
    customer_rating: float | None = None
    issue_summary: str


class TicketListResponse(BaseModel):
    count: int
    total: int
    tickets: list[TicketOut] = Field(default_factory=list)


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 3:
            raise ValueError("Question is too short.")
        return cleaned


class QueryTimings(BaseModel):
    sql_ms: float
    llm_ms: float
    text_to_sql_ms: float = 0.0
    summary_ms: float = 0.0
    total_ms: float


class QueryResponse(BaseModel):
    question: str
    answer: str
    sql: str
    explanation: str
    row_count: int
    rows: list[dict] = Field(default_factory=list)
    truncated: bool = False
    timings: QueryTimings | None = None


class MetricsResponse(BaseModel):
    uptime_seconds: float
    requests_total: int
    errors_total: int
    query_total: int
    query_failures: int
    sql_timeouts: int
    sql_executions: int = 0
    llm_calls: int
    llm_failures: int
    avg_request_ms: float
    avg_llm_ms: float
    avg_sql_ms: float
