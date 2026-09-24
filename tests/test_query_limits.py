import time

from fastapi.testclient import TestClient

from app.ingestion.loader import QueryTimeoutError
from app.main import app


def test_result_set_is_capped():
    with TestClient(app) as client:
        service = app.state.service
        rows, count, elapsed_ms = service._execute_select("SELECT * FROM tickets")
        assert count == 500
        assert len(rows) == service.settings.query_result_row_cap
        assert elapsed_ms < 1000


def test_sql_timeout_cancels_expensive_query():
    with TestClient(app) as client:
        service = app.state.service
        original = service.settings.sql_timeout_seconds
        service.settings.sql_timeout_seconds = 0.01
        service.settings.sql_progress_check_every = 100
        try:
            started = time.perf_counter()
            try:
                service._execute_select(
                    """
                    SELECT COUNT(*) AS n
                    FROM tickets a
                    JOIN tickets b ON a.ticket_id IS NOT NULL
                    JOIN tickets c ON b.ticket_id IS NOT NULL
                    """
                )
            except QueryTimeoutError:
                elapsed = time.perf_counter() - started
                assert elapsed < 2
            else:
                raise AssertionError("Expected QueryTimeoutError")
        finally:
            service.settings.sql_timeout_seconds = original
            service.settings.sql_progress_check_every = 10_000
        assert client.get("/metrics").json()["sql_timeouts"] >= 1


def test_metrics_and_request_id_headers():
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.headers.get("x-request-id")
        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        body = metrics.json()
        assert body["requests_total"] >= 1
        assert "uptime_seconds" in body
