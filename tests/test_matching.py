from pathlib import Path
import json

from app.matching import parse_text, parse_document


def test_parse_text_extracts_expected_fields():
    text = '''
    Дата: 15.05.2026
    Издател: ООО Пример
    Получател: Фирма Клиент ООД
    Клиентски номер: 12345

    Номер фактура  Сума
    TOK100  250.00
    TOK101  175.50

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
    assert {pair["Номер фактура"]: pair["Сума"] for pair in result["Invoices"]} == {
        "TOK100": "250.00",
        "TOK101": "175.50",
    }


def test_parse_tokrm_1_pdf_prints_json():
    filepath = Path("data/uploads/TOKRM_1.pdf")
    assert filepath.exists(), f"Expected file not found: {filepath}"

    result = parse_document(filepath)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    assert isinstance(result, dict)
