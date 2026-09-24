from fastapi.testclient import TestClient

from app.main import app


def test_health_stats_and_anomalies():
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        body = health.json()
        assert body["database"] == "connected"
        assert body["row_count"] == 500
        assert body["reference_now"] == "2024-03-30 18:06:00"

        stats = client.get("/stats")
        assert stats.status_code == 200
        payload = stats.json()
        assert payload["by_status"]["Open"] == 111
        assert payload["anomaly_counts"]["sla_breach"] == 80

        anomalies = client.get("/anomalies", params={"anomaly_type": "sla_breach"})
        assert anomalies.status_code == 200
        assert anomalies.json()["count"] == 80

        tickets = client.get("/tickets", params={"status": "Open", "limit": 10})
        assert tickets.status_code == 200
        assert tickets.json()["total"] == 111
        assert len(tickets.json()["tickets"]) == 10

        first_id = tickets.json()["tickets"][0]["ticket_id"]
        detail = client.get(f"/tickets/{first_id}")
        assert detail.status_code == 200
        assert detail.json()["ticket_id"] == first_id

        missing = client.get("/tickets/TKT-99999")
        assert missing.status_code == 404


def test_query_is_structured_or_reports_missing_key():
    with TestClient(app) as client:
        response = client.post("/query", json={"question": "How many tickets are currently open?"})
        if response.status_code == 503:
            assert response.json()["error"] in {"llm_not_configured", "llm_unavailable"}
            return
        assert response.status_code == 200
        body = response.json()
        assert "sql" in body
        assert "answer" in body
        assert "row_count" in body
