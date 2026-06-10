import re
from pathlib import Path
from typing import List, Dict, Optional, Any

import fitz

UPLOAD_DIR = Path("data/uploads")


def _normalize_text(text: str) -> str:
    text = text.replace("\u2013", "-")
    text = text.replace("\u2014", "-")
    text = text.replace("\u00A0", " ")
    text = re.sub(r"[\t\r]+", " ", text)
    text = re.sub(r" +", " ", text)
    return text


def _clean_value(value: Optional[str]) -> str:
    if value is None:
        return ""
    return value.strip().replace("\n", " ").strip()


def _first_match(patterns: List[str], text: str, flags=0) -> Optional[str]:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return match.group(1).strip()
    return None


def _parse_date(text: str) -> str:
    patterns = [
        r"(?:Дата|Date)\s*[:\-]?\s*([0-3]?\d[./-][0-1]?\d[./-]\d{4})",
        r"([0-3]?\d[./-][0-1]?\d[./-]\d{4})",
    ]
    return _clean_value(_first_match(patterns, text, flags=re.I))


def _parse_sender(text: str) -> str:
    patterns = [
        r"(?:Издател|От|Sender|Продавач|Supplier)\s*[:\-]?\s*(.+?)\n",
        r"^(?:Издател|От|Sender|Продавач|Supplier)\s*[:\-]?\s*(.+)$",
    ]
    return _clean_value(_first_match(patterns, text, flags=re.I | re.M))


def _parse_recipient(text: str) -> str:
    patterns = [
        r"(?:Получател|До|Recipient|Buyer)\s*[:\-]?\s*(.+?)\n",
        r"^(?:Получател|До|Recipient|Buyer)\s*[:\-]?\s*(.+)$",
    ]
    return _clean_value(_first_match(patterns, text, flags=re.I | re.M))


def _parse_client(text: str) -> str:
    patterns = [
        r"(?:Клиентски номер|Client\s*(?:№|No\.?|Number))\s*[:\-]?\s*([A-Za-zА-Яа-я0-9\-_/]+)",
    ]
    return _clean_value(_first_match(patterns, text, flags=re.I))


def _parse_amount(text: str, labels: List[str]) -> str:
    label_pattern = r"(?:" + r"|".join(re.escape(label) for label in labels) + r")"
    patterns = [
        rf"{label_pattern}\s*[:\-]?\s*([0-9]+(?:[.,][0-9]{{2}})?)(?:\s*EUR|\s*€|\s*лв|\s*BGN)?",
    ]
    return _clean_value(_first_match(patterns, text, flags=re.I))


def _split_invoice_number_and_date(value: str) -> tuple[str, str]:
    value = value.strip()
    if "/" in value:
        invoice_part, date_candidate = value.rsplit("/", 1)
        date_candidate = date_candidate.strip()
        if re.match(r"^[0-3]?\d[./-][0-1]?\d[./-]\d{4}$", date_candidate):
            return invoice_part.strip(), date_candidate
    return value, ""


def _parse_invoice_pairs(text: str) -> List[Dict[str, str]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    invoices: List[Dict[str, str]] = []
    seen = set()

    def add_invoice(invoice: str, from_date: str, amount: str) -> None:
        invoice = invoice.strip()
        from_date = from_date.strip()
        amount = amount.strip().replace(" ", "").replace(",", ".")
        if not invoice or not amount:
            return
        key = (invoice, from_date, amount)
        if key in seen:
            return
        seen.add(key)
        invoices.append({"invoice": invoice, "from": from_date, "amount": amount})

    invoice_line_pattern = re.compile(
        r"Номер\s*фактура\s*[:\-]?\s*([0-9A-Za-zА-Яа-я]+/[0-3]?\d[./-][0-1]?\d[./-]\d{4})\s*,?\s*Сума\s*[:\-]?\s*([0-9]+(?:[.,][0-9]{2}))",
        flags=re.I,
    )
    generic_line_pattern = re.compile(
        r"([0-9A-Za-zА-Яа-я]+/[0-3]?\d[./-][0-1]?\d[./-]\d{4})\s*,?\s*Сума\s*[:\-]?\s*([0-9]+(?:[.,][0-9]{2}))",
        flags=re.I,
    )

    for line in lines:
        match = invoice_line_pattern.search(line)
        if match:
            invoice_raw = match.group(1)
            invoice, from_date = _split_invoice_number_and_date(invoice_raw)
            add_invoice(invoice, from_date, match.group(2))
            continue

        if "Сума" in line and "/" in line:
            match = generic_line_pattern.search(line)
            if match:
                invoice_raw = match.group(1)
                invoice, from_date = _split_invoice_number_and_date(invoice_raw)
                add_invoice(invoice, from_date, match.group(2))
                continue

    if not invoices:
        for line in lines:
            match = re.search(
                r"([0-9A-Za-zА-Яа-я]+?)/(?:([0-3]?\d[./-][0-1]?\d[./-]\d{4}))\s*,?\s*Сума\s*[:\-]?\s*([0-9]+(?:[.,][0-9]{2}))",
                line,
                flags=re.I,
            )
            if match:
                add_invoice(match.group(1), match.group(2), match.group(3))

    return invoices


def parse_text(text: str) -> Dict[str, Any]:
    text = _normalize_text(text)
    data = {
        "Date": _parse_date(text),
        "Sender": _parse_sender(text),
        "Recipient": _parse_recipient(text),
        "Client": _parse_client(text),
        "Invoices": _parse_invoice_pairs(text),
        "Sum": _parse_amount(text, ["Обща сума", "Total amount", "Total"]),
        "Fee": _parse_amount(text, ["такса", "Fee"]),
        "FinalSum": _parse_amount(text, ["Сумаf", "Amount", "Total payable", "Final sum"]),
    }
    return data


def parse_document(filename: Path) -> Dict[str, Any]:
    filepath = Path(filename)
    if not filepath.exists():
        raise FileNotFoundError(f"Document not found: {filepath}")

    doc = fitz.open(filepath)
    text = "\n".join(page.get_text() for page in doc)
    return parse_text(text)


def parse_uploads(pattern: str = "TOK*.pdf") -> Dict[str, Dict[str, Any]]:
    results: Dict[str, Dict[str, Any]] = {}
    if not UPLOAD_DIR.exists():
        return results

    for filepath in sorted(UPLOAD_DIR.glob(pattern)):
        if filepath.is_file():
            results[filepath.name] = parse_document(filepath)
    return results


if __name__ == "__main__":
    import json

    results = parse_uploads()
    print(json.dumps(results, ensure_ascii=False, indent=2))
