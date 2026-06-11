import re
from pathlib import Path
from typing import List, Dict, Optional, Any, Union

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


def _parse_address(text: str) -> str:
    patterns = [
        r"(?:Адрес|Адреc|Address)\s*[:\-]?\s*(.+?)\.?\s*\n",
        r"^(?:Адрес|Адреc|Address)\s*[:\-]?\s*(.+?)\.?\s*$",
    ]
    addr = _first_match(patterns, text, flags=re.I | re.M)
    if addr and "Visible at" not in addr:
        pass
    else:
        if addr and "Visible at" in addr:
            addr = None
        # try to find line that starts with postal code, city, street pattern
        m = re.search(r"\b(\d{3,4}\s*,\s*[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё\-]+\b.*)$", text, flags=re.M)
        if m:
            addr = m.group(1)
        else:
            # if no postal/city/street match, extract address after Описание/Description
            m = re.search(
                r"(?m)^(?:Описание/Description)\s*[:\-]?\s*(.+)$",
                text,
                flags=re.I,
            )
            if m:
                addr = m.group(1)
            else:
                # fallback: look for a standalone address line without explicit label
                m = re.search(
                    r"(?m)^(?:ул\.?|улица|street|гр\.?|град)\s+(.+)$",
                    text,
                    flags=re.I,
                )
                if m:
                    addr = m.group(1)

    return _clean_value(addr)


def _parse_amount(text: str, labels: List[str]) -> str:
    label_pattern = r"(?:" + r"|".join(re.escape(label) for label in labels) + r")"
    
    # Special handling for "Сума словом" - extract the LAST valid amount from that line
    if any(label.lower() == "сума словом" for label in labels):
        sum_match = re.search(
            r"(?:Сума словом|Amount in words)\s*[:\-]?\s*(.+?)(?:\n|$)",
            text,
            flags=re.I
        )
        if sum_match:
            line_content = sum_match.group(1)
            # Find all amounts (number with optional 2 decimals) potentially followed by currency
            amounts = re.findall(r"([0-9]+(?:[.,][0-9]{2})?)\s*(?:EUR|€|лв|BGN)?", line_content)
            if amounts:
                # Return the last amount found in the line
                return _clean_value(amounts[-1].replace(",", "."))
    
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
        "Address": _parse_address(text),
        "Invoices": _parse_invoice_pairs(text),
        "Sum": _parse_amount(text, ["Обща сума","Сума общо", "Сума словом","Total amount", "Total"]),
        "Fee": _parse_amount(text, ["такса", "Fee"]),
        "FinalSum": _parse_amount(text, ["Amount", "Total payable", "Final sum"]),
    }
    return data


def parse_document(filename: Path) -> Dict[str, Any]:
    filepath = Path(filename)
    if not filepath.exists():
        raise FileNotFoundError(f"Document not found: {filepath}")

    text = extract_text_in_reading_order(filepath)
    data = parse_text(text)

    # Try coordinate-based extraction for sender/recipient block and merge results
    try:
        coord_res = extract_sender_recipient_by_coords(filepath)
        # add new keys without removing existing ones
        data["Sender"] = coord_res.get("sender_name", "")
        data["Recipient"] = coord_res.get("recipient_name", "")
        data["Sender_CIN"] = coord_res.get("sender_cin", "")
        data["Recipient_CIN"] = coord_res.get("recipient_cin", "")
    except Exception:
        # don't fail parsing if coords extraction fails
        data["Sender_CIN"] = ""
        data["Recipient_CIN"] = ""

    return data


def extract_text_in_reading_order(pdf_path: Union[Path, str]) -> str:
    """Extract text from PDF pages in reading order using word coordinates.

    Groups words by similar Y coordinate (same visual line) and sorts by X.
    Returns full document text with reconstructed lines joined by newlines.
    """
    pdf_path = Path(pdf_path)
    doc = fitz.open(pdf_path)
    all_lines: List[str] = []

    for page in doc:
        words = page.get_text("words")  # list of tuples (x0, y0, x1, y1, word, ...)
        if not words:
            continue

        # Sort by y (top coordinate) then x (left)
        words_sorted = sorted(words, key=lambda w: (w[1], w[0]))

        current_y = None
        current_line: List[tuple[float, str]] = []
        y_threshold = 3.0

        for w in words_sorted:
            x0, y0, x1, y1, word = w[0], w[1], w[2], w[3], w[4]

            if current_y is None:
                current_y = y0

            if abs(y0 - current_y) <= y_threshold:
                current_line.append((x0, word))
            else:
                # flush current line
                current_line.sort(key=lambda t: t[0])
                line_text = " ".join([t[1] for t in current_line])
                all_lines.append(line_text)
                current_line = [(x0, word)]
                current_y = y0

        if current_line:
            current_line.sort(key=lambda t: t[0])
            all_lines.append(" ".join([t[1] for t in current_line]))

    return "\n".join(all_lines)


def extract_sender_recipient_by_coords(pdf_path: Union[Path, str], left_cut: float = 245.0, mid_cut: float = 385.0) -> Dict[str, str]:
    """Extract sender/recipient block by word coordinates.

    - Words with x0 < left_cut -> sender column
    - Words with left_cut <= x0 < mid_cut -> recipient column
    - x0 >= mid_cut -> ignored

    Returns dict with keys: sender_name, recipient_name, sender_cin, recipient_cin
    """
    df_path = Path(pdf_path)
    doc = fitz.open(pdf_path)

    # Collect words across pages
    all_words = []
    for page_no, page in enumerate(doc, start=1):
        words = page.get_text("words")  # list of tuples (x0, y0, x1, y1, word, ...)
        for w in words:
            x0, y0, word = w[0], w[1], w[4]
            all_words.append((page_no, x0, y0, word))

    if not all_words:
        return {"sender_name": "", "recipient_name": "", "sender_cin": "", "recipient_cin": ""}

    # Group words into lines by y coordinate (per page)
    from collections import defaultdict

    lines_by_page = defaultdict(list)  # page_no -> list of (y, x, word)
    for page_no, x0, y0, word in all_words:
        lines_by_page[page_no].append((y0, x0, word))

    sender_name = ""
    recipient_name = ""
    sender_cin = ""
    recipient_cin = ""

    y_threshold = 3.0

    for page_no, items in lines_by_page.items():
        # cluster by y into visual lines
        items_sorted = sorted(items, key=lambda t: (t[0], t[1]))
        lines = []  # each line is list of (x, word)
        current_y = None
        current_line = []
        for y0, x0, word in items_sorted:
            if current_y is None:
                current_y = y0
            if abs(y0 - current_y) <= y_threshold:
                current_line.append((x0, word))
            else:
                lines.append(current_line)
                current_line = [(x0, word)]
                current_y = y0
        if current_line:
            lines.append(current_line)

        # For each visual line, build column strings
        col_lines = []  # list of tuples (left_text, mid_text, right_text)
        for line in lines:
            left_words = [w for x, w in sorted(line, key=lambda t: t[0]) if x < left_cut]
            mid_words = [w for x, w in sorted(line, key=lambda t: t[0]) if left_cut <= x < mid_cut]
            right_words = [w for x, w in sorted(line, key=lambda t: t[0]) if x >= mid_cut]
            left_text = " ".join(left_words).strip()
            mid_text = " ".join(mid_words).strip()
            right_text = " ".join(right_words).strip()
            col_lines.append((left_text, mid_text, right_text))

        # Search for header lines and extract next-line values
        for idx, (left, mid, right) in enumerate(col_lines):
            left_l = left.lower()
            mid_l = mid.lower()
            if ("наредител" in left_l) or ("sender" in left_l):
                if idx + 1 < len(col_lines):
                    sender_name_candidate = col_lines[idx + 1][0]
                    if sender_name_candidate:
                        sender_name = sender_name_candidate
            if ("получател" in mid_l) or ("recipient" in mid_l):
                if idx + 1 < len(col_lines):
                    recipient_name_candidate = col_lines[idx + 1][1]
                    if recipient_name_candidate:
                        recipient_name = recipient_name_candidate

        # Extract CIN numbers and explicit addresses from each column
        for left, mid, right in col_lines:
            # match patterns like 'КИН/CIN: 2049932947' or 'КИН: 2049932947'
            m_left = re.search(r"КИН\s*/?\s*CIN\s*[:\-]?\s*([0-9]+)", left, flags=re.I)
            if m_left and not sender_cin:
                sender_cin = m_left.group(1)
            m_mid = re.search(r"КИН\s*/?\s*CIN\s*[:\-]?\s*([0-9]+)", mid, flags=re.I)
            if m_mid and not recipient_cin:
                recipient_cin = m_mid.group(1)

    return {
        "sender_name": sender_name,
        "recipient_name": recipient_name,
        "sender_cin": sender_cin,
        "recipient_cin": recipient_cin,
    }


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
