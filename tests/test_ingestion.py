from pathlib import Path

import pandas as pd
import pytest

from app.config import Settings
from app.ingestion.loader import ingest_tickets
from app.ingestion.schema import MissingColumnsError


def test_ingest_loads_expected_columns(tmp_path: Path):
    csv_path = tmp_path / "tickets.csv"
    db_path = tmp_path / "tickets.db"
    pd.DataFrame(
        [
            {
                "ticket_id": "TKT-001",
                "created_at": "2024-03-01 10:00",
                "category": "Billing",
                "priority": "High",
                "status": "Resolved",
                "response_time_hrs": 1.0,
                "resolution_time_hrs": 2.0,
                "agent_id": "AGT-01",
                "customer_rating": 4,
                "issue_summary": "Invoice error",
            }
        ]
    ).to_csv(csv_path, index=False)

    schema = ingest_tickets(Settings(csv_path=csv_path, db_path=db_path))
    assert schema.row_count == 1
    assert schema.reference_now == "2024-03-01 10:00:00"
    assert [col.name for col in schema.columns][0] == "ticket_id"


def test_ingest_fails_on_missing_columns(tmp_path: Path):
    csv_path = tmp_path / "bad.csv"
    db_path = tmp_path / "tickets.db"
    pd.DataFrame([{"ticket_id": "TKT-001"}]).to_csv(csv_path, index=False)
    with pytest.raises(MissingColumnsError):
        ingest_tickets(Settings(csv_path=csv_path, db_path=db_path))
