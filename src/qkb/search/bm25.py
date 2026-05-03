import re
import sqlite3

from qkb.models import SearchHit

_SPECIAL = re.compile(r"""[\"\(\)\*\^\+\-\:\.\,\?\!\;]""")
_FTS_KEYWORDS = {"AND", "OR", "NOT", "NEAR"}


def build_fts_query(text: str) -> str:
    """Sanitize free-form input into a safe FTS5 OR query."""
    cleaned = _SPECIAL.sub(" ", text)
    terms = [t for t in cleaned.split() if t and t.upper() not in _FTS_KEYWORDS]
    if not terms:
        return ""
    quoted = [f'"{t}"' for t in terms]
    return " OR ".join(quoted)


_SEARCH_SQL = """
SELECT
    chunks.id           AS chunk_id,
    chunks.document_id  AS document_id,
    chunks.heading      AS heading,
    documents.path      AS path,
    bm25(chunks_fts)    AS score,
    snippet(chunks_fts, 0, '<<', '>>', '…', 24) AS snippet
FROM chunks_fts
JOIN chunks    ON chunks.id = chunks_fts.rowid
JOIN documents ON documents.id = chunks.document_id
WHERE chunks_fts MATCH ?
ORDER BY score
LIMIT ?
"""


def run_search(
    conn: sqlite3.Connection, query: str, limit: int = 20
) -> list[SearchHit]:
    fts_query = build_fts_query(query)
    if not fts_query:
        return []
    rows = conn.execute(_SEARCH_SQL, (fts_query, limit)).fetchall()
    return [
        SearchHit(
            chunk_id=r["chunk_id"],
            document_id=r["document_id"],
            path=r["path"],
            heading=r["heading"],
            snippet=r["snippet"],
            score=-r["score"],
        )
        for r in rows
    ]
