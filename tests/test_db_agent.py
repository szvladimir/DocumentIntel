import json
import sqlite3
from pathlib import Path

import pytest
from fastapi import HTTPException

from app import db_agent


def make_temp_db(tmp_path: Path):
    db_path = tmp_path / "documentintel.db"
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE processed_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            Date TEXT,
            Sender TEXT,
            Recipient TEXT,
            Address TEXT,
            Sum REAL,
            Fee REAL,
            FinalSum REAL,
            parsed_json TEXT
        )
        """
    )
    cur.execute(
        "INSERT INTO processed_documents (filename, Date, Sender, Recipient, Address, Sum, Fee, FinalSum, parsed_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        ,
        (
            "invoice.pdf",
            "2026-06-12",
            "My Sender",
            "My Recipient",
            "123 Street",
            100.0,
            5.0,
            105.0,
            json.dumps({"example": True}),
        ),
    )
    conn.commit()
    conn.close()
    return db_path


def test_validate_safe_select_query_rejects_non_select():
    with pytest.raises(HTTPException):
        db_agent.validate_safe_select_query("DELETE FROM processed_documents")

    with pytest.raises(HTTPException):
        db_agent.validate_safe_select_query("UPDATE processed_documents SET Sum = 0")

    with pytest.raises(HTTPException):
        db_agent.validate_safe_select_query("DROP TABLE processed_documents")


def test_validate_safe_select_query_allows_select():
    db_agent.validate_safe_select_query("SELECT filename, Sum FROM processed_documents")


def test_enforce_limit_adds_limit_when_missing():
    sql = "SELECT * FROM processed_documents"
    assert db_agent.enforce_limit(sql) == "SELECT * FROM processed_documents LIMIT 100"


def test_enforce_limit_reduces_large_limit():
    sql = "SELECT * FROM processed_documents LIMIT 500"
    assert db_agent.enforce_limit(sql) == "SELECT * FROM processed_documents LIMIT 100"


def test_execute_select_query_returns_rows(tmp_path: Path):
    db_path = make_temp_db(tmp_path)
    result = db_agent.execute_select_query(db_path, "SELECT filename, Sum FROM processed_documents")
    assert result["columns"] == ["filename", "Sum"]
    assert result["rows"] == [["invoice.pdf", 100.0]]


def test_execute_select_query_rejects_forbidden_keyword(tmp_path: Path):
    db_path = make_temp_db(tmp_path)
    with pytest.raises(HTTPException):
        db_agent.execute_select_query(db_path, "SELECT * FROM processed_documents; DROP TABLE processed_documents;")


def test_extract_sql_from_model_response_handles_fenced_code():
    response = "Here is the query:\n```sql\nSELECT filename FROM processed_documents;\n```"
    sql = db_agent.extract_sql_from_model_response(response)
    assert sql == "SELECT filename FROM processed_documents"


def test_generate_answer_returns_message_for_rows(tmp_path: Path):
    class StubClient:
        class chat:
            class completions:
                @staticmethod
                def create(*args, **kwargs):
                    class Message:
                        content = "The sum is 100."

                    class Choice:
                        def __init__(self):
                            self.message = Message()

                    return type("Response", (), {"choices": [Choice()]})()

    answer = db_agent.generate_answer(
        "What is the sum?",
        "SELECT Sum FROM processed_documents",
        ["Sum"],
        [[100.0]],
        StubClient(),
    )
    assert answer == "The sum is 100."


def test_generate_answer_returns_no_match_when_empty_rows(tmp_path: Path):
    class StubClient:
        class chat:
            class completions:
                @staticmethod
                def create(*args, **kwargs):
                    raise RuntimeError("Should not be called")

    answer = db_agent.generate_answer(
        "How many?",
        "SELECT COUNT(*) FROM processed_documents",
        ["count"],
        [],
        StubClient(),
    )
    assert answer == "No matching rows were found for that question."
