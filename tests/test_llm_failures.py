import json

import pytest

from app.llm.groq_client import GroqNotConfiguredError, GroqRequestError
from app.nlquery.text_to_sql import QueryTranslationError, generate_sql
from app.nlquery.summarizer import summarize_rows


class _BoomClient:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error

    def complete_json(self, system: str, user: str) -> str:
        if self.error:
            raise self.error
        return self.payload


def test_invalid_json_is_unprocessable(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        service = app.state.service
        with pytest.raises(QueryTranslationError, match="valid JSON"):
            generate_sql("How many tickets are open?", service.schema, _BoomClient(payload="not-json"))


def test_missing_sql_field_is_unprocessable():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        service = app.state.service
        with pytest.raises(QueryTranslationError, match="sql field"):
            generate_sql(
                "How many tickets are open?",
                service.schema,
                _BoomClient(payload=json.dumps({"explanation": "no sql"})),
            )


def test_malformed_sql_is_not_executed():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        service = app.state.service
        with pytest.raises(QueryTranslationError):
            generate_sql(
                "Delete everything",
                service.schema,
                _BoomClient(payload=json.dumps({"sql": "DELETE FROM tickets", "explanation": "bad"})),
            )


def test_summarizer_falls_back_when_llm_fails():
    answer = summarize_rows(
        "How many?",
        "SELECT 1",
        3,
        [{"n": 3}],
        _BoomClient(error=GroqRequestError("timeout")),
    )
    assert "3" in answer


def test_missing_key_error_type():
    from app.config import Settings
    from app.llm.groq_client import GroqClient

    with pytest.raises(GroqNotConfiguredError):
        GroqClient(Settings(groq_api_key=""))
