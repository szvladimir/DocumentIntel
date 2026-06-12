import argparse
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.matching import parse_document


DEFAULT_DB = Path("data/documentintel.db")


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS processed_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    source_path TEXT NOT NULL,
    processed_path TEXT,
    content_hash TEXT UNIQUE,
    Date TEXT,
    Sender TEXT,
    Recipient TEXT,
    Address TEXT,
    Sum REAL,
    Fee REAL,
    FinalSum REAL,
    parsed_json TEXT NOT NULL,
    alerts_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def ensure_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(CREATE_TABLE_SQL)
        conn.commit()
    finally:
        conn.close()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def already_processed(conn: sqlite3.Connection, content_hash: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM processed_documents WHERE content_hash = ? LIMIT 1", (content_hash,))
    return cur.fetchone() is not None


def insert_result(conn: sqlite3.Connection, filename: str, source_path: str, processed_path: Optional[str], content_hash: str, parsed: dict, alerts: Optional[dict] = None) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO processed_documents (filename, source_path, processed_path, content_hash, Date, Sender, Recipient, Address, Sum, Fee, FinalSum, parsed_json, alerts_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            filename,
            source_path,
            processed_path,
            content_hash,
            parsed.get("Date"),
            parsed.get("Sender"),
            parsed.get("Recipient"),
            parsed.get("Address"),
            parsed.get("Sum"),
            parsed.get("Fee"),
            parsed.get("FinalSum"),
            json.dumps(parsed, ensure_ascii=False),
            json.dumps(alerts, ensure_ascii=False) if alerts is not None else None,
        ),
    )
    conn.commit()


def process_one_file(filepath: Path, processed_dir: Path, failed_dir: Path, conn: sqlite3.Connection) -> None:
    filename = filepath.name
    try:
        content_hash = file_sha256(filepath)
    except Exception as e:
        print(f"failed to read {filename}: {e}")
        failed_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(filepath), str(failed_dir / filename))
        return

    if already_processed(conn, content_hash):
        print(f"skipped duplicate: {filename}")
        return

    # Parse document
    try:
        parsed = parse_document(filepath)
    except Exception as e:
        print(f"failed parsing {filename}: {e}")
        failed_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(filepath), str(failed_dir / filename))
        return

    # Insert into DB and move file
    try:
        processed_dir.mkdir(parents=True, exist_ok=True)
        dest = processed_dir / filename
        insert_result(conn, filename, str(filepath), str(dest), content_hash, parsed, alerts=None)
        shutil.move(str(filepath), str(dest))
        print(f"processed: {filename}")
    except sqlite3.IntegrityError as e:
        # unique constraint failed (race) - skip
        print(f"skipped duplicate (db): {filename}")
        return
    except Exception as e:
        print(f"failed storing/moving {filename}: {e}")
        failed_dir.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(filepath), str(failed_dir / filename))
        except Exception:
            pass


def process_folder(input_dir: Path, processed_dir: Path, failed_dir: Path, db_path: Path) -> None:
    ensure_db(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        input_dir.mkdir(parents=True, exist_ok=True)
        for entry in sorted(input_dir.glob("*.pdf")):
            if not entry.is_file():
                continue
            process_one_file(entry, processed_dir, failed_dir, conn)
    finally:
        conn.close()


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Process PDF folder into SQLite DB")
    parser.add_argument("--input-dir", default="data/uploads")
    parser.add_argument("--processed-dir", default="data/processed")
    parser.add_argument("--failed-dir", default="data/failed")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    args = parser.parse_args(argv)

    input_dir = Path(args.input_dir)
    processed_dir = Path(args.processed_dir)
    failed_dir = Path(args.failed_dir)
    db_path = Path(args.db)

    print(f"Starting processing: input={input_dir} db={db_path}")
    process_folder(input_dir, processed_dir, failed_dir, db_path)


if __name__ == "__main__":
    main()
