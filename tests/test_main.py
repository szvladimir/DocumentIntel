from fastapi.testclient import TestClient

from app.main import app
from app.query_intent import DateRange, QueryIntent


def test_ask_db_intent_endpoint_returns_expected_response(monkeypatch):
    intent = QueryIntent(
        intent_type="sum_payments",
        service_category="electricity",
        date_range=DateRange.model_validate({"from": "2025-12-01", "to": "2026-03-01"}),
        amount_field="FinalSum",
        group_by=None,
    )

    monkeypatch.setattr("app.main.generate_query_intent", lambda question, client: intent)
    monkeypatch.setattr(
        "app.main.execute_parameterized_query",
        lambda db_path, sql, params: {"columns": ["total_payment"], "rows": [[123.45]]},
    )
    monkeypatch.setattr("app.db_agent.generate_answer", lambda question, sql, columns, rows, client: "Сумма 123.45")

    client = TestClient(app)
    response = client.post(
        "/ask-db-intent",
        json={"question": "Сколько я заплатил за ток зимой 2026 года?"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["question"] == "Сколько я заплатил за ток зимой 2026 года?"
    assert data["intent"]["service_category"] == "electricity"
    assert data["intent"]["date_range"]["from"] == "2025-12-01"
    assert data["sql"].startswith("SELECT")
    assert data["params"] == ["electricity", "2025-12-01", "2026-03-01"]
    assert data["rows"] == [[123.45]]
    assert data["answer"] == "Сумма 123.45"
