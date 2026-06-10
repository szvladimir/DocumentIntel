from pathlib import Path
import json

from app.matching import parse_text, parse_document


def test_parse_text_extracts_expected_fields():
    text = '''
    Дата: 15.05.2026
    Издател: ООО Пример
    Получател: Фирма Клиент ООД
    Клиентски номер: 12345

    Номер фактура: TOK100/15.05.2026, Сума: 250.00 EUR
    Номер фактура: TOK101/16.05.2026, Сума: 175.50 EUR

    Обща сума: 425.50 EUR
    такса: 5.00 EUR
    Сумаf: 430.50 EUR
    '''

    result = parse_text(text)

    assert result["Date"] == "15.05.2026"
    assert result["Sender"] == "ООО Пример"
    assert result["Recipient"] == "Фирма Клиент ООД"
    assert result["Client"] == "12345"
    assert result["Sum"] == "425.50"
    assert result["Fee"] == "5.00"
    assert result["FinalSum"] == "430.50"
    assert result["Invoices"] == [
        {"invoice": "TOK100", "from": "15.05.2026", "amount": "250.00"},
        {"invoice": "TOK101", "from": "16.05.2026", "amount": "175.50"},
    ]


def test_parse_invoice_lines_with_date_and_amount():
    text = '''
    Номер фактура: 0374411355/23.01.2026, Сума: 42.53 EUR
    Номер фактура: 0374413557/23.01.2026, Сума: 0.31 EUR
    Номер фактура: 0374414265/23.01.2026, Сума: 0.79 EUR
    '''

    result = parse_text(text)

    assert result["Invoices"] == [
        {"invoice": "0374411355", "from": "23.01.2026", "amount": "42.53"},
        {"invoice": "0374413557", "from": "23.01.2026", "amount": "0.31"},
        {"invoice": "0374414265", "from": "23.01.2026", "amount": "0.79"},
    ]


def test_parse_tokrm_1_pdf_prints_json():
    filepath = Path("data/uploads/TOKRM_1.pdf")
    assert filepath.exists(), f"Expected file not found: {filepath}"

    result = parse_document(filepath)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    assert isinstance(result, dict)
