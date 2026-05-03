import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from qkb.ingest.chunker import chunk_for_format
from qkb.ingest.readers import READERS, detect_format

IngestStatus = str  # "inserted" | "updated" | "skipped" | "unsupported"
IngestResult = tuple[Path, IngestStatus, int | None]
Summarizer = Callable[[str], tuple[str, str]]  # text -> (summary, tags)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def delete_document(conn: sqlite3.Connection, doc_id: int) -> None:
    """Remove a document, its chunks, and its FTS rows."""
    conn.execute(
        "DELETE FROM chunks_fts "
        "WHERE rowid IN (SELECT id FROM chunks WHERE document_id = ?)",
        (doc_id,),
    )
    conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))


def _existing(conn: sqlite3.Connection, abs_path: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, content_hash FROM documents WHERE path = ?", (abs_path,)
    ).fetchone()


def ingest_file(
    conn: sqlite3.Connection,
    path: Path,
    *,
    summarizer: Summarizer | None = None,
    force: bool = False,
) -> IngestResult:
    fmt = detect_format(path)
    if fmt is None:
        return path, "unsupported", None

    raw = path.read_text(encoding="utf-8")
    content_hash = _sha256(raw)
    abs_path = str(path.resolve())

    existing = _existing(conn, abs_path)
    if existing is not None and existing["content_hash"] == content_hash and not force:
        return path, "skipped", existing["id"]

    text, meta = READERS[fmt](path)

    summary: str | None = None
    tags: str | None = None
    if summarizer is not None:
        try:
            summary, tags = summarizer(text)
        except Exception as e:
            print(f"  warn: summary failed for {path.name}: {e}", file=sys.stderr)

    if existing is not None:
        delete_document(conn, existing["id"])

    cur = conn.execute(
        """
        INSERT INTO documents(path, content_hash, format, ingested_at, summary, tags, meta_json)
        VALUES(?,?,?,?,?,?,?)
        """,
        (
            abs_path,
            content_hash,
            fmt,
            _now_iso(),
            summary,
            tags,
            json.dumps(meta) if meta else None,
        ),
    )
    doc_id = int(cur.lastrowid)

    for ch in chunk_for_format(fmt, text):
        cur = conn.execute(
            """
            INSERT INTO chunks(document_id, seq, heading, content, start_line, end_line)
            VALUES(?,?,?,?,?,?)
            """,
            (doc_id, ch.seq, ch.heading, ch.content, ch.start_line, ch.end_line),
        )
        chunk_id = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO chunks_fts(rowid, content, heading, summary) VALUES(?,?,?,?)",
            (chunk_id, ch.content, ch.heading or "", summary or ""),
        )

    return path, ("updated" if existing is not None else "inserted"), doc_id


def _walk(path: Path, recursive: bool) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []
    glob = path.rglob("*") if recursive else path.glob("*")
    return sorted(p for p in glob if p.is_file() and detect_format(p) is not None)


def ingest_path(
    conn: sqlite3.Connection,
    path: Path,
    *,
    recursive: bool = False,
    summarizer: Summarizer | None = None,
    force: bool = False,
) -> list[IngestResult]:
    """Ingest a file or directory; returns one IngestResult per file."""
    results: list[IngestResult] = []
    for p in _walk(path, recursive):
        results.append(ingest_file(conn, p, summarizer=summarizer, force=force))
    conn.commit()
    return results
