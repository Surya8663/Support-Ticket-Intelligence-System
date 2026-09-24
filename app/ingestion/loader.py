from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path

import pandas as pd

from app.config import Settings
from app.ingestion.schema import (
    COLUMN_NOTES,
    EXPECTED_CATEGORIES,
    EXPECTED_PRIORITIES,
    EXPECTED_STATUSES,
    NULLABLE_COLUMNS,
    REQUIRED_COLUMNS,
    ColumnInfo,
    MissingColumnsError,
    SchemaInfo,
)

logger = logging.getLogger(__name__)

TICKETS_TABLE = "tickets"

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status)",
    "CREATE INDEX IF NOT EXISTS idx_tickets_priority ON tickets(priority)",
    "CREATE INDEX IF NOT EXISTS idx_tickets_category ON tickets(category)",
    "CREATE INDEX IF NOT EXISTS idx_tickets_agent ON tickets(agent_id)",
    "CREATE INDEX IF NOT EXISTS idx_tickets_created ON tickets(created_at)",
)


def ingest_tickets(settings: Settings) -> SchemaInfo:
    """Load the CSV into SQLite. Idempotent: the tickets table is replaced each run."""
    csv_path = Path(settings.csv_path)
    db_path = Path(settings.db_path)

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found at {csv_path.resolve()}")

    df = pd.read_csv(csv_path)
    _validate_columns(df)
    df, warnings = _coerce_and_validate(df)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(f"DROP TABLE IF EXISTS {TICKETS_TABLE}")
        df.to_sql(TICKETS_TABLE, conn, index=False, if_exists="replace")
        for stmt in _INDEXES:
            conn.execute(stmt)
        conn.commit()
        schema = introspect_schema(conn, warnings=warnings)
    finally:
        conn.close()

    logger.info(
        "Ingested %s rows into %s (reference_now=%s)",
        schema.row_count,
        db_path,
        schema.reference_now,
    )
    for warning in schema.warnings:
        logger.warning(warning)
    return schema


def introspect_schema(
    conn: sqlite3.Connection,
    table: str = TICKETS_TABLE,
    warnings: list[str] | None = None,
) -> SchemaInfo:
    """Read column names/types from SQLite so prompts are never hardcoded to one CSV."""
    pragma = conn.execute(f"PRAGMA table_info({table})").fetchall()
    if not pragma:
        raise RuntimeError(f"Table {table} is missing after ingest")

    row_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    reference_now = conn.execute(f"SELECT MAX(created_at) FROM {table}").fetchone()[0]

    columns = [
        ColumnInfo(
            name=row[1],
            sql_type=row[2] or "TEXT",
            nullable=row[1] in NULLABLE_COLUMNS or not row[3],
            note=COLUMN_NOTES.get(row[1], ""),
        )
        for row in pragma
    ]
    return SchemaInfo(
        table_name=table,
        columns=columns,
        row_count=int(row_count),
        reference_now=str(reference_now) if reference_now is not None else None,
        warnings=warnings or [],
    )


class QueryTimeoutError(RuntimeError):
    """Raised when a generated query exceeds the configured VM budget."""


def connect(
    db_path: Path,
    readonly: bool = False,
    timeout_seconds: float | None = None,
    progress_every: int = 10_000,
) -> sqlite3.Connection:
    path = Path(db_path)
    if readonly:
        uri = f"{path.resolve().as_uri()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
    else:
        conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    if timeout_seconds and timeout_seconds > 0:
        started = time.monotonic()

        def _watchdog() -> int:
            if time.monotonic() - started > timeout_seconds:
                return 1
            return 0

        conn.set_progress_handler(_watchdog, progress_every)
    return conn


def _validate_columns(df: pd.DataFrame) -> None:
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise MissingColumnsError(
            f"CSV is missing required columns: {missing}. Found: {list(df.columns)}"
        )


def _coerce_and_validate(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    warnings: list[str] = []
    out = df.copy()

    parsed_dates = pd.to_datetime(out["created_at"], errors="coerce")
    bad_dates = int(parsed_dates.isna().sum())
    if bad_dates:
        warnings.append(f"{bad_dates} rows have unparseable created_at values and were kept as null.")
    out["created_at"] = parsed_dates.dt.strftime("%Y-%m-%d %H:%M:%S")
    # Preserve original nulls from failed parses as None for SQLite.
    out.loc[parsed_dates.isna(), "created_at"] = None

    for col in ("response_time_hrs", "resolution_time_hrs", "customer_rating"):
        out[col] = pd.to_numeric(out[col], errors="coerce")

    warnings.extend(_categorical_warnings(out["category"], "category", EXPECTED_CATEGORIES))
    warnings.extend(_categorical_warnings(out["priority"], "priority", EXPECTED_PRIORITIES))
    warnings.extend(_categorical_warnings(out["status"], "status", EXPECTED_STATUSES))
    return out, warnings


def _categorical_warnings(series: pd.Series, name: str, expected: frozenset[str]) -> list[str]:
    unexpected = sorted({str(v) for v in series.dropna().unique()} - expected)
    if unexpected:
        return [f"Unexpected {name} values (logged, not rejected): {unexpected}"]
    return []
