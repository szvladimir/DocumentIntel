import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from openai import OpenAI

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT_DIR / "data" / "documentintel.db"
TABLE_NAME = "processed_documents"
TABLE_COLUMNS = [
    "filename",
    "Date",
    "Sender",
    "Recipient",
    "Address",
    "Sum",
    "Fee",
    "FinalSum",
    "parsed_json",
]
FORBIDDEN_KEYWORDS = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "REPLACE", "TRUNCATE"]
OPENAI_MODEL = "gpt-4.1-mini"


def get_openai_client(api_key: str | None = None) -> OpenAI:
    return OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))


def extract_sql_from_model_response(text: str) -> str:
    text = text.strip()

    fenced = re.search(r"```(?:sql)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()

    # If the model returns a label before the SQL, strip it off.
    labeled = re.search(r"(?i)(?:sql\s*[:\-]*\s*)([\s\S]+)", text)
    if labeled:
        candidate = labeled.group(1).strip()
        if candidate and re.search(r"(?i)\b(?:SELECT|WITH)\b", candidate):
            text = candidate

    query_match = re.search(r"(?i)(?:WITH|SELECT)\b[\s\S]*", text)
    if not query_match:
        raise HTTPException(status_code=500, detail="OpenAI did not return a valid SELECT query.")

    sql = query_match.group(0).strip()
    sql = sql.rstrip(";\n ")
    return sql


def validate_safe_select_query(sql: str) -> None:
    if not sql.strip():
        raise HTTPException(status_code=400, detail="Empty SQL query is not permitted.")

    cleaned = sql.strip()
    if not re.match(r"(?i)^(WITH|SELECT)\b", cleaned):
        raise HTTPException(status_code=400, detail="Only read-only SELECT queries are permitted.")

    if re.search(r"(?i)\b(?:%s)\b" % "|".join(FORBIDDEN_KEYWORDS), cleaned):
        raise HTTPException(status_code=400, detail="Only read-only SELECT queries are permitted.")

    # Disallow multiple statements. A trailing semicolon is fine if it is the only one.
    semicolons = cleaned.count(";")
    if semicolons > 1 or (semicolons == 1 and not cleaned.endswith(";")):
        raise HTTPException(status_code=400, detail="Only a single SELECT query is permitted.")


def enforce_limit(sql: str, max_rows: int = 100) -> str:
    sql = sql.strip().rstrip(";")
    limit_match = re.search(r"(?i)\bLIMIT\s+(\d+)(\s*(?:OFFSET\s+\d+)?)?\b", sql)
    if limit_match:
        limit_value = int(limit_match.group(1))
        if limit_value > max_rows:
            sql = re.sub(
                r"(?i)\bLIMIT\s+\d+(\s*(?:OFFSET\s+\d+)?)?\b",
                f"LIMIT {max_rows}" + (limit_match.group(2) or ""),
                sql,
            )
    else:
        sql = f"{sql} LIMIT {max_rows}"
    return sql


def generate_sql_from_question(question: str, client: OpenAI) -> str:
    if not question or not question.strip():
        raise HTTPException(status_code=400, detail="Question must be provided.")

    instructions = [
        {
            "role": "system",
            "content": (
                "You are a SQL generator. Generate a single read-only SQLite SQL query "
                "that answers the user's question using only the table 'processed_documents' with the following columns: "
                f"{', '.join(TABLE_COLUMNS)}."
            ),
        },
        {
            "role": "user",
            "content": (
                "Create only one SQL SELECT query. Do not use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, "
                "REPLACE, or TRUNCATE. Return just the SQL statement without any additional explanation. "
                f"Question: {question}"
            ),
        },
    ]

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=instructions,
        temperature=0,
    )

    sql = extract_sql_from_model_response(response.choices[0].message.content)
    validate_safe_select_query(sql)
    return sql


def execute_select_query(db_path: Path, sql: str, max_rows: int = 100) -> dict[str, Any]:
    validate_safe_select_query(sql)
    sql = enforce_limit(sql, max_rows=max_rows)

    if not db_path.exists():
        raise HTTPException(status_code=500, detail=f"Database file not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        columns = [column[0] for column in cursor.description or []]
        rows = [list(row) for row in cursor.fetchall()]
    finally:
        conn.close()

    return {"columns": columns, "rows": rows}


def generate_answer(question: str, sql: str, columns: list[str], rows: list[list[Any]], client: OpenAI) -> str:
    if not question or not question.strip():
        raise HTTPException(status_code=400, detail="Question must be provided.")

    if not rows:
        return "No matching rows were found for that question."

    answer_prompt = [
        {
            "role": "system",
            "content": (
                "You are an assistant that answers questions based only on SQL query results. "
                "Do not hallucinate beyond the provided rows."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Question: {question}\n"
                f"SQL: {sql}\n"
                f"Columns: {', '.join(columns)}\n"
                f"Rows: {json.dumps(rows, ensure_ascii=False)}\n"
                "Provide a concise natural language answer based only on these rows."
            ),
        },
    ]

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=answer_prompt,
        temperature=0,
    )

    return response.choices[0].message.content.strip()
