from __future__ import annotations

import logging
import sqlite3
from dataclasses import asdict, dataclass

import pandas as pd

from app.config import Settings

logger = logging.getLogger(__name__)

ANOMALIES_TABLE = "anomalies"
RESOLUTION_OUTLIER = "resolution_outlier"
SLA_BREACH = "sla_breach"

ANOMALIES_DDL = f"""
CREATE TABLE IF NOT EXISTS {ANOMALIES_TABLE} (
    ticket_id TEXT NOT NULL,
    anomaly_type TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL,
    threshold REAL,
    reason TEXT NOT NULL,
    created_at TEXT,
    category TEXT,
    priority TEXT,
    status TEXT
)
"""


@dataclass
class AnomalyRecord:
    ticket_id: str
    anomaly_type: str
    metric_name: str
    metric_value: float | None
    threshold: float | None
    reason: str
    created_at: str
    category: str
    priority: str
    status: str


def detect_anomalies(
    tickets: pd.DataFrame,
    settings: Settings,
    reference_now: str | pd.Timestamp | None,
    method: str = "iqr",
    iqr_multiplier: float | None = None,
    zscore_threshold: float | None = None,
    sla_breach_hours: float | None = None,
) -> list[AnomalyRecord]:
    """Deterministic anomaly detection. The LLM is not consulted."""
    if tickets.empty:
        return []

    df = tickets.copy()
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    now = pd.to_datetime(reference_now) if reference_now is not None else df["created_at"].max()

    k = settings.iqr_multiplier if iqr_multiplier is None else iqr_multiplier
    z_thresh = settings.zscore_threshold if zscore_threshold is None else zscore_threshold
    sla_hours = settings.sla_breach_hours if sla_breach_hours is None else sla_breach_hours

    outliers = (
        _resolution_iqr(df, k)
        if method == "iqr"
        else _resolution_zscore(df, z_thresh)
    )
    breaches = _sla_breaches(df, now, sla_hours)
    return outliers + breaches


def persist_anomalies(conn: sqlite3.Connection, records: list[AnomalyRecord]) -> None:
    conn.execute(f"DROP TABLE IF EXISTS {ANOMALIES_TABLE}")
    conn.execute(ANOMALIES_DDL)
    if records:
        conn.executemany(
            f"""
            INSERT INTO {ANOMALIES_TABLE} (
                ticket_id, anomaly_type, metric_name, metric_value, threshold,
                reason, created_at, category, priority, status
            ) VALUES (
                :ticket_id, :anomaly_type, :metric_name, :metric_value, :threshold,
                :reason, :created_at, :category, :priority, :status
            )
            """,
            [asdict(r) for r in records],
        )
    conn.commit()
    logger.info("Persisted %s anomaly rows", len(records))


def load_anomalies(conn: sqlite3.Connection) -> list[AnomalyRecord]:
    rows = conn.execute(f"SELECT * FROM {ANOMALIES_TABLE}").fetchall()
    return [
        AnomalyRecord(
            ticket_id=row["ticket_id"],
            anomaly_type=row["anomaly_type"],
            metric_name=row["metric_name"],
            metric_value=row["metric_value"],
            threshold=row["threshold"],
            reason=row["reason"],
            created_at=row["created_at"],
            category=row["category"],
            priority=row["priority"],
            status=row["status"],
        )
        for row in rows
    ]


def _resolution_iqr(df: pd.DataFrame, k: float) -> list[AnomalyRecord]:
    resolved = df[df["status"] == "Resolved"].dropna(subset=["resolution_time_hrs"])
    if resolved.empty:
        return []

    records: list[AnomalyRecord] = []
    for category, group in resolved.groupby("category", dropna=False):
        bounds = _iqr_bounds(group["resolution_time_hrs"], k)
        if bounds is None:
            continue
        lower, upper, q1, q3, iqr = bounds
        flagged = group[group["resolution_time_hrs"] > upper]
        for row in flagged.itertuples(index=False):
            value = float(row.resolution_time_hrs)
            records.append(
                _outlier_record(
                    row,
                    value=value,
                    threshold=upper,
                    reason=(
                        f"Resolution time {value:.1f}h is above the IQR upper fence "
                        f"{upper:.1f}h for {category} tickets "
                        f"(Q1={q1:.1f}, Q3={q3:.1f}, IQR={iqr:.1f}, k={k})."
                    ),
                )
            )
    return records


def _resolution_zscore(df: pd.DataFrame, threshold: float) -> list[AnomalyRecord]:
    resolved = df[df["status"] == "Resolved"].dropna(subset=["resolution_time_hrs"])
    if resolved.empty:
        return []

    records: list[AnomalyRecord] = []
    for category, group in resolved.groupby("category", dropna=False):
        values = group["resolution_time_hrs"]
        std = float(values.std(ddof=0))
        if std == 0 or pd.isna(std):
            continue
        mean = float(values.mean())
        z = (values - mean) / std
        flagged = group[z.abs() > threshold]
        for row in flagged.itertuples(index=False):
            value = float(row.resolution_time_hrs)
            score = abs((value - mean) / std)
            records.append(
                _outlier_record(
                    row,
                    value=value,
                    threshold=threshold,
                    reason=(
                        f"Resolution time {value:.1f}h has |z|={score:.2f} "
                        f"(threshold {threshold}) within {category} tickets "
                        f"(mean={mean:.1f}h)."
                    ),
                )
            )
    return records


def _sla_breaches(
    df: pd.DataFrame,
    reference_now: pd.Timestamp,
    sla_hours: float,
) -> list[AnomalyRecord]:
    openish = df[df["status"] != "Resolved"].copy()
    high_priority = openish[openish["priority"].isin(["High", "Critical"])]
    if high_priority.empty:
        return []

    age_hours = (reference_now - high_priority["created_at"]).dt.total_seconds() / 3600.0
    flagged = high_priority[age_hours > sla_hours]
    records: list[AnomalyRecord] = []
    for row, age in zip(flagged.itertuples(index=False), age_hours.loc[flagged.index]):
        records.append(
            AnomalyRecord(
                ticket_id=str(row.ticket_id),
                anomaly_type=SLA_BREACH,
                metric_name="hours_open",
                metric_value=round(float(age), 2),
                threshold=float(sla_hours),
                reason=(
                    f"Unresolved {row.priority} ticket has been open {float(age):.1f}h, "
                    f"exceeding the {sla_hours:.0f}h SLA "
                    f"(status={row.status}, reference_now={reference_now})."
                ),
                created_at=_fmt_ts(row.created_at),
                category=str(row.category),
                priority=str(row.priority),
                status=str(row.status),
            )
        )
    return records


def _iqr_bounds(series: pd.Series, k: float) -> tuple[float, float, float, float, float] | None:
    if len(series) < 4:
        return None
    q1 = float(series.quantile(0.25))
    q3 = float(series.quantile(0.75))
    iqr = q3 - q1
    if iqr == 0:
        return None
    return q1 - k * iqr, q3 + k * iqr, q1, q3, iqr


def _outlier_record(row, value: float, threshold: float, reason: str) -> AnomalyRecord:
    return AnomalyRecord(
        ticket_id=str(row.ticket_id),
        anomaly_type=RESOLUTION_OUTLIER,
        metric_name="resolution_time_hrs",
        metric_value=round(value, 2),
        threshold=round(float(threshold), 2),
        reason=reason,
        created_at=_fmt_ts(row.created_at),
        category=str(row.category),
        priority=str(row.priority),
        status=str(row.status),
    )


def _fmt_ts(value) -> str:
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return ""
    return ts.strftime("%Y-%m-%d %H:%M:%S")
