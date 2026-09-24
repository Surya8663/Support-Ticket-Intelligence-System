from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import pandas as pd

from app.anomalies.detector import detect_anomalies, load_anomalies, persist_anomalies
from app.config import Settings
from app.ingestion.loader import connect, ingest_tickets
from app.ingestion.schema import SchemaInfo
from app.llm.groq_client import GroqClient
from app.models.schemas import (
    AnomaliesResponse,
    AnomalyCounts,
    AnomalyOut,
    HealthResponse,
    NumericSummary,
    QueryResponse,
    StatsResponse,
    TicketListResponse,
    TicketOut,
)
from app.nlquery.summarizer import summarize_rows
from app.nlquery.text_to_sql import generate_sql

logger = logging.getLogger(__name__)


class TicketService:
    """Shared orchestration used by the API. UI must not import internals; it calls HTTP."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.schema: SchemaInfo | None = None
        self.anomaly_count: int = 0

    def startup(self) -> SchemaInfo:
        self.schema = ingest_tickets(self.settings)
        with self._connect(readonly=False) as conn:
            tickets = pd.read_sql_query("SELECT * FROM tickets", conn)
            records = detect_anomalies(
                tickets,
                self.settings,
                self.schema.reference_now,
                method="iqr",
            )
            persist_anomalies(conn, records)
            self.anomaly_count = len(records)
        logger.info("Startup complete: %s tickets, %s anomalies", self.schema.row_count, self.anomaly_count)
        return self.schema

    def health(self) -> HealthResponse:
        db_ok = False
        if Path(self.settings.db_path).exists() and self.schema is not None:
            try:
                with self._connect(readonly=True) as conn:
                    conn.execute("SELECT 1 FROM tickets LIMIT 1")
                db_ok = True
            except sqlite3.Error as exc:
                logger.warning("Health check could not read SQLite: %s", exc)
        return HealthResponse(
            status="ok" if db_ok else "degraded",
            database="connected" if db_ok else "missing",
            groq_configured=bool(self.settings.groq_api_key),
            row_count=self.schema.row_count if self.schema else 0,
            reference_now=self.schema.reference_now if self.schema else None,
        )

    def stats(self) -> StatsResponse:
        with self._connect() as conn:
            tickets = pd.read_sql_query("SELECT * FROM tickets", conn)
            stored = load_anomalies(conn)

        resolved = tickets[tickets["status"] == "Resolved"]
        anomaly_counts = AnomalyCounts(
            resolution_outlier=sum(1 for a in stored if a.anomaly_type == "resolution_outlier"),
            sla_breach=sum(1 for a in stored if a.anomaly_type == "sla_breach"),
        )
        return StatsResponse(
            row_count=int(len(tickets)),
            reference_now=self.schema.reference_now if self.schema else None,
            by_status=_value_counts(tickets, "status"),
            by_priority=_value_counts(tickets, "priority"),
            by_category=_value_counts(tickets, "category"),
            by_agent=_value_counts(tickets, "agent_id"),
            resolution_time_hrs=_numeric_summary(resolved["resolution_time_hrs"]),
            customer_rating=_numeric_summary(resolved["customer_rating"]),
            anomaly_counts=anomaly_counts,
        )

    def anomalies(
        self,
        method: str = "iqr",
        anomaly_type: str = "all",
        iqr_multiplier: float | None = None,
        zscore_threshold: float | None = None,
        sla_breach_hours: float | None = None,
    ) -> AnomaliesResponse:
        defaults = (
            method == "iqr"
            and iqr_multiplier is None
            and zscore_threshold is None
            and sla_breach_hours is None
        )
        with self._connect() as conn:
            if defaults:
                records = load_anomalies(conn)
            else:
                tickets = pd.read_sql_query("SELECT * FROM tickets", conn)
                records = detect_anomalies(
                    tickets,
                    self.settings,
                    self.schema.reference_now if self.schema else None,
                    method=method,
                    iqr_multiplier=iqr_multiplier,
                    zscore_threshold=zscore_threshold,
                    sla_breach_hours=sla_breach_hours,
                )

        if anomaly_type != "all":
            records = [r for r in records if r.anomaly_type == anomaly_type]

        return AnomaliesResponse(
            count=len(records),
            method=method,  # type: ignore[arg-type]
            reference_now=self.schema.reference_now if self.schema else None,
            anomalies=[AnomalyOut(**r.__dict__) for r in records],
        )

    def list_tickets(
        self,
        status: str | None = None,
        priority: str | None = None,
        category: str | None = None,
        agent_id: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> TicketListResponse:
        with self._connect(readonly=True) as conn:
            tickets = pd.read_sql_query("SELECT * FROM tickets", conn)
        if status:
            tickets = tickets[tickets["status"] == status]
        if priority:
            tickets = tickets[tickets["priority"] == priority]
        if category:
            tickets = tickets[tickets["category"] == category]
        if agent_id:
            tickets = tickets[tickets["agent_id"] == agent_id]
        if search:
            needle = search.lower()
            tickets = tickets[
                tickets["ticket_id"].str.lower().str.contains(needle, na=False)
                | tickets["issue_summary"].str.lower().str.contains(needle, na=False)
                | tickets["agent_id"].str.lower().str.contains(needle, na=False)
            ]
        tickets = tickets.sort_values("created_at", ascending=False)
        total = int(len(tickets))
        page = tickets.iloc[offset : offset + limit]
        return TicketListResponse(
            count=int(len(page)),
            total=total,
            tickets=[_ticket_out(row) for row in page.to_dict(orient="records")],
        )

    def get_ticket(self, ticket_id: str) -> TicketOut | None:
        with self._connect(readonly=True) as conn:
            row = conn.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
        if row is None:
            return None
        return _ticket_out(dict(row))

    def query(self, question: str) -> QueryResponse:
        if self.schema is None:
            raise RuntimeError("Service has not been started.")
        client = GroqClient(self.settings)
        plan = generate_sql(question, self.schema, client)
        logger.info("Generated SQL for query: %s", plan.sql)
        rows, row_count = self._execute_select(plan.sql)
        answer = summarize_rows(question, plan.sql, row_count, rows, client)
        return QueryResponse(
            question=question,
            answer=answer,
            sql=plan.sql,
            explanation=plan.explanation,
            row_count=row_count,
            rows=rows,
        )

    def _execute_select(self, sql: str) -> tuple[list[dict], int]:
        cap = self.settings.query_result_row_cap
        with self._connect(readonly=True) as conn:
            cursor = conn.execute(sql)
            columns = [col[0] for col in cursor.description] if cursor.description else []
            fetched = cursor.fetchall()
        row_count = len(fetched)
        rows = [_stringify_row(columns, row) for row in fetched[:cap]]
        return rows, row_count

    def _connect(self, readonly: bool = True) -> sqlite3.Connection:
        return connect(self.settings.db_path, readonly=readonly)


def _ticket_out(row: dict) -> TicketOut:
    return TicketOut(
        ticket_id=str(row["ticket_id"]),
        created_at=str(row["created_at"]),
        category=str(row["category"]),
        priority=str(row["priority"]),
        status=str(row["status"]),
        response_time_hrs=_optional_float(row.get("response_time_hrs")),
        resolution_time_hrs=_optional_float(row.get("resolution_time_hrs")),
        agent_id=str(row["agent_id"]),
        customer_rating=_optional_float(row.get("customer_rating")),
        issue_summary=str(row.get("issue_summary") or ""),
    )


def _optional_float(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return float(value)


def _value_counts(df: pd.DataFrame, column: str) -> dict[str, int]:
    return {str(k): int(v) for k, v in df[column].value_counts().items()}


def _stringify_row(columns: list[str], row: sqlite3.Row | tuple) -> dict:
    values = list(row)
    return {col: _json_safe(value) for col, value in zip(columns, values)}


def _json_safe(value):
    if value is None:
        return None
    if isinstance(value, (int, float, str, bool)):
        return value
    return str(value)


def _numeric_summary(series: pd.Series) -> NumericSummary:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return NumericSummary(count=0)
    return NumericSummary(
        count=int(clean.count()),
        mean=round(float(clean.mean()), 3),
        median=round(float(clean.median()), 3),
        min=round(float(clean.min()), 3),
        max=round(float(clean.max()), 3),
    )
