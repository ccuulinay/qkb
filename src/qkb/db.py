import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  id           INTEGER PRIMARY KEY,
  path         TEXT UNIQUE NOT NULL,
  content_hash TEXT NOT NULL,
  format       TEXT NOT NULL,
  ingested_at  TEXT NOT NULL,
  summary      TEXT,
  tags         TEXT,
  meta_json    TEXT
);

CREATE TABLE IF NOT EXISTS chunks (
  id          INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  seq         INTEGER NOT NULL,
  heading     TEXT,
  content     TEXT NOT NULL,
  start_line  INTEGER,
  end_line    INTEGER
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(document_id);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  content, heading, summary,
  tokenize='porter unicode61'
);
"""


def get_connection(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def bootstrap(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)
    try:
        init_schema(conn)
    finally:
        conn.close()
