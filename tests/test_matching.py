from app.matching import parse_text, parse_document


def test_parse_document_returns_a_mapping_for_generated_pdf(tmp_path):
    import fitz

    filepath = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Date: 15.05.2026\\nSum: 100.00 EUR")
    doc.save(filepath)
    doc.close()

    result = parse_document(filepath)

    assert isinstance(result, dict)
    assert result["Date"] == "2026-05-15"



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
    Сума/Amount: 430.50 EUR
    '''

    result = parse_text(text)

    assert result["Date"] == "2026-05-15"
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


def test_extract_sender_recipient_from_generated_pdf(tmp_path):
    import fitz

    out = tmp_path / "sender_recipient.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=200)

    fontfile = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

    page.insert_font(
       fontname="dejavu",
       fontfile=fontfile
    )
    # Header labels
    page.insert_text((15, 50), "Наредител/Sender:", fontname="dejavu", fontsize=12)
    page.insert_text((250, 50), "Получател/Recipient:", fontname="dejavu", fontsize=12)
    page.insert_text((390, 50), "Енерго-Про Продажби АД", fontname="dejavu", fontsize=12)
     # Names on next line
    page.insert_text((15, 70), "MyNameXXXXXX", fontname="dejavu", fontsize=12)
    page.insert_text((250, 70), "ЕНЕРГО-ПРО", fontname="dejavu", fontsize=12)
    page.insert_text((390, 70), "тел./phone: 0700 161 61", fontname="dejavu", fontsize=12)

    # CINs
    page.insert_text((15, 90), "КИН/CIN: 2049932947", fontname="dejavu", fontsize=12)
    page.insert_text((250, 90), "КИН/CIN: 7011778568", fontname="dejavu", fontsize=12)

    doc.save(str(out))
    doc.close()
 


    result = parse_document(out)

    assert result.get("Sender") == "MyNameXXXXXX"
    assert result.get("Recipient") == "ЕНЕРГО-ПРО"
    assert result.get("Sender_CIN") == "2049932947"
    assert result.get("Recipient_CIN") == "7011778568"


def test_parse_sum_with_suma_slovom_ignores_middle_text():
    """Test that 'Сума словом' with mixed text extracts the last numeric amount."""
    text = """
    Сума словом/Amount in words: осем EUR , 96 8.96 EUR
    """
    result = parse_text(text)
    assert result["Sum"] == "8.96"


def test_parse_sum_with_suma_slovom_multiple_values():
    """Test that 'Сума словом' extracts the last amount when multiple numbers present."""
    text = """
    Сума словом/Amount in words: петдесет BGN 50.00 EUR
    """
    result = parse_text(text)
    assert result["Sum"] == "50.00"
