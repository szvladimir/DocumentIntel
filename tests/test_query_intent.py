import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.query_intent import QueryIntent, extract_json_from_model_response, generate_query_intent
from app.sql_builder import build_payments_query


class StubClient:
    class chat:
        class completions:
            @staticmethod
            def create(*args, **kwargs):
                class Message:
                    content = json.dumps(
                        {
                            "intent_type": "sum_payments",
                            "service_category": "electricity",
                            "date_range": {
                                "from": "2025-12-01",
                                "to": "2026-03-01"
                            },
                            "amount_field": "FinalSum",
                            "group_by": None,
                        }, ensure_ascii=False
                    )

                class Choice:
                    def __init__(self):
                        self.message = Message()

                return type("Response", (), {"choices": [Choice()]})()


def test_extract_json_from_model_response_parses_fenced_json():
    response = "Here is the intent:\n```json\n{\n  \"intent_type\": \"sum_payments\"\n}```"
    assert extract_json_from_model_response(response) == {"intent_type": "sum_payments"}


def test_query_intent_validation_rejects_bad_date():
    with pytest.raises(ValidationError):
        QueryIntent.model_validate(
            {
                "intent_type": "sum_payments",
                "service_category": "electricity",
                "date_range": {"from": "2025-13-01", "to": "2026-03-01"},
                "amount_field": "FinalSum",
                "group_by": None,
            }
        )


def test_generate_query_intent_uses_openai_for_json():
    intent = generate_query_intent("Сколько я заплатил за ток зимой 2026 года?", StubClient())
    assert intent.intent_type == "sum_payments"
    assert intent.service_category == "electricity"
    assert intent.date_range.from_ == "2025-12-01"
    assert intent.date_range.to == "2026-03-01"


def test_generate_query_intent_parses_water_january_2026():
    class WaterStubClient(StubClient):
        class chat:
            class completions:
                @staticmethod
                def create(*args, **kwargs):
                    class Message:
                        content = json.dumps(
                            {
                                "intent_type": "sum_payments",
                                "service_category": "water",
                                "date_range": {
                                    "from": "2026-01-01",
                                    "to": "2026-02-01"
                                },
                                "amount_field": "FinalSum",
                                "group_by": None,
                            }, ensure_ascii=False
                        )

                    class Choice:
                        def __init__(self):
                            self.message = Message()

                    return type("Response", (), {"choices": [Choice()]})()

    intent = generate_query_intent("Сколько было за воду в январе 2026?", WaterStubClient())
    assert intent.intent_type == "sum_payments"
    assert intent.service_category == "water"
    assert intent.date_range.from_ == "2026-01-01"
    assert intent.date_range.to == "2026-02-01"


def test_build_payments_query_uses_join_and_params():
    intent = {
        "intent_type": "sum_payments",
        "service_category": "electricity",
        "date_range": {"from": "2025-12-01", "to": "2026-03-01"},
        "amount_field": "FinalSum",
        "group_by": None,
    }

    sql, params = build_payments_query(intent)
    assert "JOIN providers pr ON p.Recipient = pr.Recipient" in sql
    assert sql.startswith("SELECT SUM(p.FinalSum)")
    assert "?" in sql
    assert params == ["electricity", "2025-12-01", "2026-03-01"]


def test_build_payments_query_list_payments_limit():
    intent = {
        "intent_type": "list_payments",
        "service_category": "water",
        "date_range": {"from": "2026-01-01", "to": "2026-02-01"},
        "amount_field": "FinalSum",
        "group_by": None,
    }

    sql, params = build_payments_query(intent)
    assert "JOIN providers pr ON p.Recipient = pr.Recipient" in sql
    assert "LIMIT 200" in sql
    assert params == ["water", "2026-01-01", "2026-02-01"]


def test_build_payments_query_rejects_unknown_intent():
    with pytest.raises(HTTPException):
        build_payments_query(
            {
                "intent_type": "unknown",
                "service_category": None,
                "date_range": None,
                "amount_field": "FinalSum",
                "group_by": None,
            }
        )


def test_build_payments_query_all_records_when_date_range_is_null():
    intent = {
        "intent_type": "sum_payments",
        "service_category": "electricity",
        "date_range": None,
        "amount_field": "FinalSum",
        "group_by": None,
    }

    sql, params = build_payments_query(intent)
    assert "p.Date >= ?" not in sql
    assert "p.Date < ?" not in sql
    assert params == ["electricity"]
