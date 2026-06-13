from datetime import datetime

def normalize_date_to_iso(value: str | None) -> str | None:
    if not value:
        return None

    value = value.strip()

    # already ISO
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError:
        pass

    # DD.MM.YYYY
    try:
        return datetime.strptime(value, "%d.%m.%Y").date().isoformat()
    except ValueError:
        pass

    return value
    