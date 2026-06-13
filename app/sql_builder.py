from pathlib import Path
from typing import Any, Iterable

from fastapi import HTTPException


SAFE_SELECT_PATTERNS = ["SELECT", "FROM", "JOIN", "WHERE", "ORDER BY", "LIMIT", "GROUP BY"]


def build_payments_query(intent: dict[str, Any]) -> tuple[str, list[Any]]:
    intent_type = intent.get("intent_type")
    service_category = intent.get("service_category")
    date_range = intent.get("date_range")
    group_by = intent.get("group_by")

    if intent_type not in {"sum_payments", "list_payments", "unknown"}:
        raise HTTPException(status_code=400, detail="Invalid intent_type.")

    if intent_type == "unknown":
        raise HTTPException(status_code=400, detail="Cannot build SQL for unknown intent.")

    if service_category is None:
        raise HTTPException(status_code=400, detail="service_category is required for payment queries.")

    params: list[Any] = [service_category]
    if date_range:
        range_from = date_range.get("from") or date_range.get("from_")
        range_to = date_range.get("to")
        if range_from is None or range_to is None:
            raise HTTPException(status_code=400, detail="date_range.from and date_range.to are required when date_range is provided.")
        date_clause = " AND p.Date >= ? AND p.Date < ?"
        params.extend([range_from, range_to])
    else:
        date_clause = ""

    where_clause = f"WHERE pr.category = ?{date_clause}"

    if intent_type == "sum_payments":
        if group_by == "month":
            sql = (
                "SELECT strftime('%Y-%m', p.Date) AS month, SUM(p.FinalSum) AS total_payment "
                "FROM processed_documents p "
                "JOIN providers pr ON p.Recipient = pr.Recipient "
                f"{where_clause} "
                "GROUP BY month ORDER BY month"
            )
        elif group_by == "recipient":
            sql = (
                "SELECT p.Recipient, SUM(p.FinalSum) AS total_payment "
                "FROM processed_documents p "
                "JOIN providers pr ON p.Recipient = pr.Recipient "
                f"{where_clause} "
                "GROUP BY p.Recipient ORDER BY p.Recipient"
            )
        else:
            sql = (
                "SELECT SUM(p.FinalSum) AS total_payment "
                "FROM processed_documents p "
                "JOIN providers pr ON p.Recipient = pr.Recipient "
                f"{where_clause}"
            )
    else:
        sql = (
            "SELECT p.Date, p.Recipient, pr.category, p.FinalSum, p.filename "
            "FROM processed_documents p "
            "JOIN providers pr ON p.Recipient = pr.Recipient "
            f"{where_clause} "
            "ORDER BY p.Date LIMIT 200"
        )

    return sql, params


def validate_safe_select_query(sql: str) -> None:
    cleaned = sql.strip().upper()
    if not cleaned.startswith("SELECT"):
        raise HTTPException(status_code=400, detail="Only SELECT queries are permitted.")

    forbidden = {"INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "REPLACE", "TRUNCATE"}
    if any(keyword in cleaned for keyword in forbidden):
        raise HTTPException(status_code=400, detail="Only read-only SELECT queries are permitted.")

    if ";" in cleaned and not cleaned.endswith(";"):
        raise HTTPException(status_code=400, detail="Only a single SELECT query is permitted.")


def execute_parameterized_query(db_path: Path, sql: str, params: Iterable[Any]) -> dict[str, Any]:
    validate_safe_select_query(sql)

    if not db_path.exists():
        raise HTTPException(status_code=500, detail=f"Database file not found: {db_path}")

    import sqlite3

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.execute(sql, list(params))
        columns = [column[0] for column in cursor.description or []]
        rows = [list(row) for row in cursor.fetchall()]
    finally:
        conn.close()

    return {"columns": columns, "rows": rows}
