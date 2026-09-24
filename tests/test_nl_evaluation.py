import json

from fastapi.testclient import TestClient

from app.main import app
from app.nlquery.eval_cases import GOLDEN_CASES
from app.nlquery.sql_guard import validate_sql
from app.nlquery.text_to_sql import generate_sql


def _scalar(rows: list[dict], column: str):
    return rows[0][column] if rows else None


def test_golden_sql_semantics_and_results():
    with TestClient(app) as client:
        service = app.state.service
        for case in GOLDEN_CASES:
            sql = validate_sql(case.sql)
            rows, count, _ms = service._execute_select(sql)
            if case.expected_count is not None:
                assert count == case.expected_count, f"{case.question}: count {count}"
            if case.expected_scalar is not None:
                value = _scalar(rows, case.scalar_column or "value")
                if case.scalar_round is not None:
                    value = round(float(value), case.scalar_round)
                assert value == case.expected_scalar, f"{case.question}: {value}"
        health = client.get("/health")
        assert health.status_code == 200


def test_nulls_are_domain_meaningful_not_zero():
    with TestClient(app) as client:
        service = app.state.service
        null_resolution, _, _ = service._execute_select(
            "SELECT COUNT(*) AS value FROM tickets WHERE resolution_time_hrs IS NULL"
        )
        null_rating, _, _ = service._execute_select(
            "SELECT COUNT(*) AS value FROM tickets WHERE customer_rating IS NULL"
        )
        unresolved, _, _ = service._execute_select(
            "SELECT COUNT(*) AS value FROM tickets WHERE status IN ('Open', 'Escalated')"
        )
        assert null_resolution[0]["value"] == 173
        assert null_rating[0]["value"] == 173
        assert unresolved[0]["value"] == 173
        assert client.get("/stats").json()["by_status"]["Resolved"] == 327


def test_text_to_sql_uses_golden_sql_when_model_cooperates():
    class ScriptedClient:
        def complete_json(self, system: str, user: str) -> str:
            question = user.split("Question:", 1)[-1].strip().split("\n", 1)[0]
            for case in GOLDEN_CASES:
                if case.question == question:
                    return json.dumps({"sql": case.sql, "explanation": case.intent})
            raise AssertionError(f"No golden SQL for {question}")

    with TestClient(app) as client:
        service = app.state.service
        plan = generate_sql(
            GOLDEN_CASES[0].question,
            service.schema,
            ScriptedClient(),
            max_joins=service.settings.sql_max_joins,
        )
        assert "status = 'Open'" in plan.sql
        assert "Escalated" not in plan.sql
        assert client.get("/metrics").status_code == 200
