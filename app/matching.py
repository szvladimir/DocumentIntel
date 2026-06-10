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


def _parse_invoice_pairs(text: str) -> List[Dict[str, str]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    pairs: List[Dict[str, str]] = []
    seen = set()

    def add_pair(number: str, amount: str) -> None:
        number = number.strip()
        amount = amount.strip().replace(" ", "")
        if not number or not amount:
            return
        key = (number, amount)
        if key in seen:
            return
        seen.add(key)
        pairs.append({"Номер фактура": number, "Сума": amount})

    # Search for invoice-number / amount pairs in the document
    for line in lines:
        if re.search(r'Номер\s*фактура|Invoice\s*(?:No|Number)?|фактура', line, re.I):
            matches = re.findall(r'([A-Za-zА-Яа-я0-9\-_/]{3,})\s+([0-9]+(?:[.,][0-9]{2}))', line)
            for number, amount in matches:
                add_pair(number, amount)

    if not pairs:
        # Scan around possible table headings and general lines
        for i, line in enumerate(lines):
            if re.search(r'Номер\s*фактура|Invoice\s*(?:No|Number)?', line, re.I):
                for candidate in lines[i + 1 : i + 15]:
                    if re.search(r'(?:(?:Сума|Amount)|[0-9]+(?:[.,][0-9]{2}))', candidate, re.I):
                        match = re.search(r'([A-Za-zА-Яа-я0-9\-_/]{3,})\s+([0-9]+(?:[.,][0-9]{2}))', candidate)
                        if match:
                            add_pair(match.group(1), match.group(2))
                break

    if not pairs:
        for line in lines:
            if re.search(r'ТОК|TOK|фактура', line, re.I):
                match = re.search(r'([A-Za-zА-Яа-я0-9\-_/]{3,})\b.*?([0-9]+(?:[.,][0-9]{2}))', line, re.I)
                if match:
                    add_pair(match.group(1), match.group(2))

    return pairs


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
