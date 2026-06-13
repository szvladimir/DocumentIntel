import json
import re
from datetime import datetime
from typing import Any, Dict, Literal, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError, field_validator


class DateRange(BaseModel):
    from_: str = Field(..., alias="from")
    to: str

    @field_validator("from_", "to")
    def validate_iso_date(cls, value: str) -> str:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
            raise ValueError("Date must be in ISO format YYYY-MM-DD")
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("Date must be a valid calendar date") from exc
        return value


class QueryIntent(BaseModel):
    intent_type: Literal["sum_payments", "list_payments", "unknown"]
    service_category: Optional[Literal["electricity", "water", "internet_tv", "housekeeper"]]
    date_range: Optional[DateRange] = None
    amount_field: Literal["FinalSum"] = "FinalSum"
    group_by: Optional[Literal["month", "recipient"]] = None

    @field_validator("service_category", mode="after")
    def validate_service_category(cls, value, info):
        if info.data.get("intent_type") != "unknown" and value is None:
            raise ValueError("service_category is required for known payment intents")
        return value


def extract_json_from_model_response(text: str) -> Dict[str, Any]:
    text = text.strip()

    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()

    json_match = re.search(r"(\{[\s\S]*\})", text)
    if not json_match:
        raise HTTPException(status_code=500, detail="OpenAI did not return valid JSON for QueryIntent.")

    try:
        return json.loads(json_match.group(1))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to parse QueryIntent JSON: {exc}") from exc


def generate_query_intent(question: str, client: Any) -> QueryIntent:
    if not question or not question.strip():
        raise HTTPException(status_code=400, detail="Question must be provided.")

    current_date = datetime.utcnow().date().isoformat()
    messages = [
        {
            "role": "system",
            "content": (
                "You are a JSON generator. Convert the user's natural language question into a strict QueryIntent JSON object. "
                "Do not generate SQL or any other code. Output only a single JSON object with the exact schema."
            ),
        },
        {
            "role": "user",
            "content": (
                "Schema:\n"
                "{\n"
                "  \"intent_type\": \"sum_payments\" | \"list_payments\" | \"unknown\",\n"
                "  \"service_category\": \"electricity\" | \"water\" | \"internet_tv\" | \"housekeeper\" | null,\n"
                "  \"date_range\": {\n"
                "    \"from\": \"YYYY-MM-DD\",\n"
                "    \"to\": \"YYYY-MM-DD\"\n"
                "  } | null,\n"
                "  \"amount_field\": \"FinalSum\",\n"
                "  \"group_by\": \"month\" | \"recipient\" | null\n"
                "}\n\n"
                "Business rules:\n"
                "- Words \"ток\", \"электричество\", \"електроенергия\" map to service_category = \"electricity\".\n"
                "- Words \"вода\", \"канализация\", \"ВиК\" map to service_category = \"water\".\n"
                "- Words \"интернет\", \"телевидение\", \"VIVACOM\" map to service_category = \"internet_tv\".\n"
                "- Words \"почистка\", \"household\", \"управление\", \"домоуправление\", \"домоуправител\" map to service_category = \"housekeeper\".\n"
                "- Recipient is the service provider. Sender is the payer. For service questions, use providers.category for service categories and do not search service words inside Sender, Recipient, Address or filename.\n"
                "- Dates must be ISO format YYYY-MM-DD.\n"
                "- Only create date_range when the user explicitly mentions a specific date, a month, a season, a year, or a relative time period such as today, yesterday, this week, last month, this year, or last year.\n"
                "- If no explicit date or time period is mentioned, set date_range to null and search all available records.\n"
                f"- CurrentDate = {current_date}\n"
                "- Interpret relative periods using CurrentDate:\n"
                "  - this year = calendar year containing CurrentDate\n"
                "  - last year = previous calendar year\n"
                "  - this month = month containing CurrentDate\n"
                "  - last month = previous month\n"
                "  - this week = week containing CurrentDate\n"
                "- If a month, season, or specific date is mentioned without a year, assume the year of CurrentDate.\n"
                "- Never return an error because date_range is missing.\n"
                "- \"зима 2026\" means from 2025-12-01 inclusive to 2026-03-01 exclusive.\n"
                "- \"январь 2026\" means from 2026-01-01 inclusive to 2026-02-01 exclusive.\n"
                "- \"2026 год\" means from 2026-01-01 inclusive to 2027-01-01 exclusive.\n"
                "- Use null when a field is not applicable.\n"
                f"Question: {question}"
            ),
        },
    ]

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        temperature=0,
    )

    intent_data = extract_json_from_model_response(response.choices[0].message.content)
    try:
        return QueryIntent.model_validate(intent_data)
    except ValidationError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid QueryIntent returned by model: {exc}") from exc
