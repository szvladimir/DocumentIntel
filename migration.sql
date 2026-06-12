PRAGMA foreign_keys = OFF;

BEGIN TRANSACTION;

ALTER TABLE processed_documents
RENAME TO processed_documents_old;

CREATE TABLE processed_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,
    source_path TEXT,
    processed_path TEXT,
     content_hash TEXT UNIQUE,

    Date TEXT,
    Sender TEXT,
    Recipient TEXT,
    Address TEXT,
    Sum REAL,
    Fee REAL,
    FinalSum REAL,

    parsed_json TEXT,
    alerts_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (Recipient)
        REFERENCES providers(Recipient)
);

INSERT INTO processed_documents (
    id,
    filename,
    source_path,
    processed_path,
     content_hash,
    Date,
    Sender,
    Recipient,
    Address,
    Sum,
    Fee,
    FinalSum,
    parsed_json,
    alerts_json,
    created_at
)
SELECT
    id,
    filename,
    source_path,
    processed_path,
    content_hash,
    Date,
    Sender,
    Recipient,
    Address,
    Sum,
    Fee,
    FinalSum,
    parsed_json,
    alerts_json,
    created_at
FROM processed_documents_old;

COMMIT;

PRAGMA foreign_keys = ON;

