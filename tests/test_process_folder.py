import sqlite3
from pathlib import Path

import fitz
import shutil

from app import process_folder


def make_sample_pdf(path: Path, text: str = "Invoice sample"):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()


def test_process_and_duplicate(tmp_path: Path):
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    failed = tmp_path / "failed"
    db = tmp_path / "documentintel.db"

    inbox.mkdir()

    pdf1 = inbox / "doc1.pdf"
    make_sample_pdf(pdf1, "Client: ACME\nSum: 100\n")

    # first run
    process_folder.process_folder(inbox, processed, failed, db)

    # DB should have one row
    conn = sqlite3.connect(str(db))
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM processed_documents")
    count = cur.fetchone()[0]
    assert count == 1

    # file moved to processed
    assert (processed / "doc1.pdf").exists()
    assert not (inbox / "doc1.pdf").exists()

    # create duplicate file (same content) in inbox with different name
    dup = inbox / "doc1-copy.pdf"
    shutil.copy(str(processed / "doc1.pdf"), str(dup))
    assert dup.exists()

    # second run: duplicate should be skipped (DB unchanged) and file remains in inbox
    process_folder.process_folder(inbox, processed, failed, db)
    cur.execute("SELECT COUNT(*) FROM processed_documents")
    count2 = cur.fetchone()[0]
    conn.close()
    assert count2 == 1
    # duplicate not moved (left in inbox)
    assert (inbox / "doc1-copy.pdf").exists()
