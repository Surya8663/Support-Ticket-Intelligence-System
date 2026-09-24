from app.nlquery.prompts import date_windows, sql_system_prompt


def test_relative_windows_are_bound_to_dataset_now():
    windows = date_windows("2024-03-30 18:06:00")
    assert windows["this_month"] == "2024-03"
    assert windows["last_month"] == "2024-02"
    assert windows["week_start"] == "2024-03-23 18:06:00"
    assert windows["last_week_start"] == "2024-03-16 18:06:00"
    assert windows["reference_now"] == "2024-03-30 18:06:00"


def test_prompt_contains_last_week_and_last_month():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        prompt = sql_system_prompt(app.state.service.schema)
        assert "2024-03" in prompt
        assert "2024-02" in prompt
        assert "2024-03-23 18:06:00" in prompt
        assert "2024-03-16 18:06:00" in prompt
        assert client.get("/health").json()["reference_now"] == "2024-03-30 18:06:00"


def test_missing_reference_now_is_empty():
    windows = date_windows(None)
    assert windows["this_month"] == ""
    assert windows["last_month"] == ""
