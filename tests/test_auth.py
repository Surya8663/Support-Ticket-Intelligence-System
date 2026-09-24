from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


def test_api_is_open_when_token_unset():
    settings = get_settings()
    original = settings.api_token
    settings.api_token = ""
    try:
        with TestClient(app) as client:
            assert client.get("/stats").status_code == 200
    finally:
        settings.api_token = original


def test_bearer_token_is_required_when_configured():
    settings = get_settings()
    original = settings.api_token
    settings.api_token = "assessment-secret"
    try:
        with TestClient(app) as client:
            denied = client.get("/stats")
            assert denied.status_code == 401
            assert denied.json()["error"] == "unauthorized"
            allowed = client.get("/stats", headers={"Authorization": "Bearer assessment-secret"})
            assert allowed.status_code == 200
            assert client.get("/health").status_code == 200
            preflight = client.options("/stats")
            assert preflight.status_code != 401
    finally:
        settings.api_token = original
