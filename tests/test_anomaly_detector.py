import pandas as pd

from app.anomalies.detector import detect_anomalies
from app.config import Settings


def _tickets() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticket_id": "T1",
                "created_at": "2024-03-01 10:00:00",
                "category": "Billing",
                "priority": "Low",
                "status": "Resolved",
                "resolution_time_hrs": 4.0,
            },
            {
                "ticket_id": "T2",
                "created_at": "2024-03-01 10:00:00",
                "category": "Billing",
                "priority": "Low",
                "status": "Resolved",
                "resolution_time_hrs": 5.0,
            },
            {
                "ticket_id": "T3",
                "created_at": "2024-03-01 10:00:00",
                "category": "Billing",
                "priority": "Low",
                "status": "Resolved",
                "resolution_time_hrs": 6.0,
            },
            {
                "ticket_id": "T4",
                "created_at": "2024-03-01 10:00:00",
                "category": "Billing",
                "priority": "Low",
                "status": "Resolved",
                "resolution_time_hrs": 5.5,
            },
            {
                "ticket_id": "T5",
                "created_at": "2024-03-01 10:00:00",
                "category": "Billing",
                "priority": "Low",
                "status": "Resolved",
                "resolution_time_hrs": 80.0,
            },
            {
                "ticket_id": "T6",
                "created_at": "2024-03-01 10:00:00",
                "category": "Technical",
                "priority": "Critical",
                "status": "Open",
                "resolution_time_hrs": None,
            },
            {
                "ticket_id": "T7",
                "created_at": "2024-03-30 17:00:00",
                "category": "Technical",
                "priority": "High",
                "status": "Open",
                "resolution_time_hrs": None,
            },
        ]
    )


def test_iqr_flags_extreme_resolution_time():
    settings = Settings(iqr_multiplier=1.5, sla_breach_hours=24)
    records = detect_anomalies(_tickets(), settings, "2024-03-30 18:06:00", method="iqr")
    outliers = [r for r in records if r.anomaly_type == "resolution_outlier"]
    assert {r.ticket_id for r in outliers} == {"T5"}


def test_sla_flags_old_high_priority_only():
    settings = Settings(iqr_multiplier=1.5, sla_breach_hours=24)
    records = detect_anomalies(_tickets(), settings, "2024-03-30 18:06:00", method="iqr")
    breaches = [r for r in records if r.anomaly_type == "sla_breach"]
    assert {r.ticket_id for r in breaches} == {"T6"}
