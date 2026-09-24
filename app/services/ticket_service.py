from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path

import pandas as pd

from app.anomalies.detector import detect_anomalies, load_anomalies, persist_anomalies
from app.config import Settings
from app.ingestion.loader import QueryTimeoutError, connect, ingest_tickets
from app.ingestion.schema import SchemaInfo
from app.llm.groq_client import GroqClient
from app.models.schemas import (
    AnomaliesResponse,
    AnomalyCounts,
    AnomalyOut,
    HealthResponse,
    NumericSummary,
    QueryResponse,
    QueryTimings,
    StatsResponse,
    TicketListResponse,
    TicketOut,
)
from app.nlquery.result_limit import bound_select, count_select
from app.nlquery.sql_guard import validate_sql
from app.nlquery.summarizer import summarize_rows
from app.nlquery.text_to_sql import generate_sql
from app.observability import metrics

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
            auth_required=bool(self.settings.api_token),
            sql_timeout_seconds=self.settings.sql_timeout_seconds,
        )

    def stats(self) -> StatsResponse:
        with self._connect() as conn:
            row_count = int(conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0])
            stored = load_anomalies(conn)
            resolution = _numeric_from_sql(
                conn,
                "resolution_time_hrs",
                "status = 'Resolved' AND resolution_time_hrs IS NOT NULL",
            )
            rating = _numeric_from_sql(
                conn,
                "customer_rating",
                "status = 'Resolved' AND customer_rating IS NOT NULL",
            )
            by_status = _group_counts(conn, "status")
            by_priority = _group_counts(conn, "priority")
            by_category = _group_counts(conn, "category")
            by_agent = _group_counts(conn, "agent_id")

        anomaly_counts = AnomalyCounts(
            resolution_outlier=sum(1 for a in stored if a.anomaly_type == "resolution_outlier"),
            sla_breach=sum(1 for a in stored if a.anomaly_type == "sla_breach"),
        )
        return StatsResponse(
            row_count=row_count,
            reference_now=self.schema.reference_now if self.schema else None,
            by_status=by_status,
            by_priority=by_priority,
            by_category=by_category,
            by_agent=by_agent,
            resolution_time_hrs=resolution,
            customer_rating=rating,
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
        clauses = ["1=1"]
        params: list[object] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if priority:
            clauses.append("priority = ?")
            params.append(priority)
        if category:
            clauses.append("category = ?")
            params.append(category)
        if agent_id:
            clauses.append("agent_id = ?")
            params.append(agent_id)
        if search:
            clauses.append(
                "(LOWER(ticket_id) LIKE ? OR LOWER(issue_summary) LIKE ? OR LOWER(agent_id) LIKE ?)"
            )
            needle = f"%{search.lower()}%"
            params.extend([needle, needle, needle])
        where = " AND ".join(clauses)
        with self._connect(readonly=True) as conn:
            total = int(conn.execute(f"SELECT COUNT(*) FROM tickets WHERE {where}", params).fetchone()[0])
            rows = conn.execute(
                f"""
                SELECT * FROM tickets
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()
        return TicketListResponse(
            count=len(rows),
            total=total,
            tickets=[_ticket_out(dict(row)) for row in rows],
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
        started = time.perf_counter()
        client = GroqClient(self.settings)
        plan = generate_sql(
            question,
            self.schema,
            client,
            max_joins=self.settings.sql_max_joins,
        )
        text_to_sql_ms = (time.perf_counter() - started) * 1000
        sql = validate_sql(plan.sql, max_joins=self.settings.sql_max_joins)
        logger.info("Generated SQL for query: %s", sql)
        rows, row_count, sql_ms = self._execute_select(sql)
        summary_started = time.perf_counter()
        answer = summarize_rows(question, sql, row_count, rows, client)
        summary_ms = (time.perf_counter() - summary_started) * 1000
        total_ms = (time.perf_counter() - started) * 1000
        return QueryResponse(
            question=question,
            answer=answer,
            sql=sql,
            explanation=plan.explanation,
            row_count=row_count,
            rows=rows,
            truncated=row_count > len(rows),
            timings=QueryTimings(
                sql_ms=round(sql_ms, 2),
                llm_ms=round(text_to_sql_ms + summary_ms, 2),
                text_to_sql_ms=round(text_to_sql_ms, 2),
                summary_ms=round(summary_ms, 2),
                total_ms=round(total_ms, 2),
            ),
        )

    def _execute_select(self, sql: str) -> tuple[list[dict], int, float]:
        cap = self.settings.query_result_row_cap
        fetch_limit = cap + 1
        bounded_sql = bound_select(sql, fetch_limit)
        started = time.perf_counter()
        try:
            with self._connect(
                readonly=True,
                timeout_seconds=self.settings.sql_timeout_seconds,
            ) as conn:
                cursor = conn.execute(bounded_sql)
                columns = [col[0] for col in cursor.description] if cursor.description else []
                fetched = cursor.fetchmany(fetch_limit)
        except sqlite3.OperationalError as exc:
            timed_out = "interrupt" in str(exc).lower()
            metrics.record_sql((time.perf_counter() - started) * 1000, timed_out=timed_out)
            if timed_out:
                raise QueryTimeoutError(
                    f"Query exceeded {self.settings.sql_timeout_seconds:.1f}s and was cancelled."
                ) from exc
            raise
        elapsed_ms = (time.perf_counter() - started) * 1000
        metrics.record_sql(elapsed_ms, timed_out=False)
        truncated = len(fetched) > cap
        rows = [_stringify_row(columns, row) for row in fetched[:cap]]
        if truncated:
            row_count = self._count_matches(sql)
        else:
            row_count = len(fetched)
        return rows, row_count, elapsed_ms

    def _count_matches(self, sql: str) -> int:
        with self._connect(
            readonly=True,
            timeout_seconds=self.settings.sql_timeout_seconds,
        ) as conn:
            row = conn.execute(count_select(sql)).fetchone()
        return int(row[0]) if row else 0

    def _connect(self, readonly: bool = True, timeout_seconds: float | None = None) -> sqlite3.Connection:
        return connect(
            self.settings.db_path,
            readonly=readonly,
            timeout_seconds=timeout_seconds,
            progress_every=self.settings.sql_progress_check_every,
        )


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


def _group_counts(conn: sqlite3.Connection, column: str) -> dict[str, int]:
    rows = conn.execute(f"SELECT {column}, COUNT(*) AS n FROM tickets GROUP BY {column}").fetchall()
    return {str(row[0]): int(row[1]) for row in rows}


def _numeric_from_sql(conn: sqlite3.Connection, column: str, where: str) -> NumericSummary:
    stats = conn.execute(
        f"SELECT COUNT({column}), AVG({column}), MIN({column}), MAX({column}) FROM tickets WHERE {where}"
    ).fetchone()
    count = int(stats[0] or 0)
    if count == 0:
        return NumericSummary(count=0)
    median_row = conn.execute(
        f"""
        SELECT AVG({column}) FROM (
            SELECT {column} FROM tickets
            WHERE {where}
            ORDER BY {column}
            LIMIT 2 - (SELECT COUNT({column}) FROM tickets WHERE {where}) % 2
            OFFSET (
                SELECT (COUNT({column}) - 1) / 2 FROM tickets WHERE {where}
            )
        )
        """
    ).fetchone()
    return NumericSummary(
        count=count,
        mean=round(float(stats[1]), 3),
        median=round(float(median_row[0]), 3) if median_row and median_row[0] is not None else None,
        min=round(float(stats[2]), 3),
        max=round(float(stats[3]), 3),
    )


def _stringify_row(columns: list[str], row: sqlite3.Row | tuple) -> dict:
    values = list(row)
    return {col: _json_safe(value) for col, value in zip(columns, values)}


def _json_safe(value):
    if value is None:
        return None
    if isinstance(value, (int, float, str, bool)):
        return value
    return str(value)
