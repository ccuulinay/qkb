import json as _json
import sqlite3
import tomllib
from pathlib import Path

import httpx
import typer

from qkb.config import load_config
from qkb.db import bootstrap, get_connection
from qkb.ingest.pipeline import delete_document, ingest_path
from qkb.ingest.summarizer import summarize_file
from qkb.llm.client import LLMClient, LLMNotConfigured
from qkb.models import Config
from qkb.search.bm25 import run_search
from qkb.search.reranker import rerank as llm_rerank

app = typer.Typer(help="qkb — local knowledge-base CLI.", no_args_is_help=True)
config_app = typer.Typer(help="Read/write qkb configuration.", no_args_is_help=True)
app.add_typer(config_app, name="config")


def _require_db(cfg: Config) -> None:
    if not cfg.db_path.exists():
        typer.echo("Database not initialized. Run `qkb init` first.", err=True)
        raise typer.Exit(1)


def _find_doc(conn: sqlite3.Connection, target: str) -> sqlite3.Row | None:
    if target.isdigit():
        return conn.execute(
            "SELECT * FROM documents WHERE id = ?", (int(target),)
        ).fetchone()
    p = Path(target)
    if p.exists():
        resolved = str(p.resolve())
        row = conn.execute(
            "SELECT * FROM documents WHERE path = ?", (resolved,)
        ).fetchone()
        if row is not None:
            return row
    return conn.execute(
        "SELECT * FROM documents WHERE path LIKE ? ORDER BY id LIMIT 1",
        (f"%{target}",),
    ).fetchone()


_SETTABLE_KEYS = {"db_path", "llm_provider", "llm_base_url", "llm_model", "llm_api_key"}


def _toml_string(s: str) -> str:
    """JSON-style string is a valid TOML basic string for our character set."""
    return _json.dumps(s)


def _write_toml(path: Path, data: dict) -> None:
    lines = []
    for k, v in sorted(data.items()):
        if v is None:
            continue
        if isinstance(v, bool):
            lines.append(f"{k} = {str(v).lower()}")
        elif isinstance(v, (int, float)):
            lines.append(f"{k} = {v}")
        else:
            lines.append(f"{k} = {_toml_string(str(v))}")
    path.write_text("\n".join(lines) + "\n")


@app.command()
def init() -> None:
    """Create the qkb data directory and database."""
    cfg = load_config()
    bootstrap(cfg.db_path)
    typer.echo(f"Initialized qkb at {cfg.data_dir}")
    typer.echo(f"Database: {cfg.db_path}")


@app.command()
def status() -> None:
    """Show database statistics."""
    cfg = load_config()
    _require_db(cfg)
    conn = get_connection(cfg.db_path)
    try:
        n_docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        n_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    finally:
        conn.close()
    size_bytes = cfg.db_path.stat().st_size
    typer.echo(f"Database: {cfg.db_path}")
    typer.echo(f"Documents: {n_docs}")
    typer.echo(f"Chunks:    {n_chunks}")
    typer.echo(f"Size:      {size_bytes:,} bytes")


@config_app.command("list")
def config_list() -> None:
    """Print the effective configuration."""
    cfg = load_config()
    typer.echo(f"data_dir:     {cfg.data_dir}")
    typer.echo(f"db_path:      {cfg.db_path}")
    typer.echo(f"llm_provider: {cfg.llm_provider}")
    typer.echo(f"llm_base_url: {cfg.llm_base_url or '-'}")
    typer.echo(f"llm_model:    {cfg.llm_model or '-'}")
    typer.echo(f"llm_api_key:  {'***' if cfg.llm_api_key else '-'}")


@config_app.command("get")
def config_get(key: str) -> None:
    """Print one config value."""
    cfg = load_config()
    if not hasattr(cfg, key):
        typer.echo(f"Unknown key: {key}", err=True)
        raise typer.Exit(1)
    val = getattr(cfg, key)
    typer.echo("(unset)" if val is None else str(val))


@config_app.command("set")
def config_set(key: str, value: str) -> None:
    """Set a config value (persists to ~/.qkb/config.toml)."""
    if key not in _SETTABLE_KEYS:
        typer.echo(
            f"Cannot set {key!r}. Settable keys: {sorted(_SETTABLE_KEYS)}",
            err=True,
        )
        raise typer.Exit(1)
    cfg = load_config()
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    config_file = cfg.data_dir / "config.toml"
    existing: dict = {}
    if config_file.exists():
        with config_file.open("rb") as f:
            existing = tomllib.load(f)
    existing[key] = value
    _write_toml(config_file, existing)
    typer.echo(f"Set {key} in {config_file}")


@app.command()
def ingest(
    paths: list[Path] = typer.Argument(..., help="Files or directories to ingest."),
    recursive: bool = typer.Option(False, "--recursive", "-r"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Skip LLM summarization."),
    force: bool = typer.Option(False, "--force", help="Re-ingest even if hash unchanged."),
) -> None:
    """Ingest one or more files into the knowledge base."""
    cfg = load_config()
    _require_db(cfg)

    summarizer = None
    if not no_llm:
        client = LLMClient(cfg)
        if client.is_configured():
            summarizer = lambda text: summarize_file(client, text)

    conn = get_connection(cfg.db_path)
    try:
        all_results = []
        for p in paths:
            if not p.exists():
                typer.echo(f"  missing      {p}", err=True)
                continue
            results = ingest_path(
                conn, p, recursive=recursive, summarizer=summarizer, force=force
            )
            all_results.extend(results)
            if not results and p.is_file():
                typer.echo(f"  unsupported  {p}", err=True)
    finally:
        conn.close()

    counts: dict[str, int] = {}
    for path, status, _doc_id in all_results:
        counts[status] = counts.get(status, 0) + 1
        typer.echo(f"  {status:10s} {path}")
    if all_results:
        summary = "  ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        typer.echo(f"\nTotal: {len(all_results)} files. {summary}")
    else:
        typer.echo("No files ingested.")


@app.command("list")
def list_docs(
    fmt: str | None = typer.Option(None, "--format", help="Filter by format (md/txt/json/yaml/csv)."),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """List ingested documents."""
    cfg = load_config()
    _require_db(cfg)
    conn = get_connection(cfg.db_path)
    try:
        sql = "SELECT id, path, format, ingested_at, summary, tags FROM documents"
        params: tuple = ()
        if fmt:
            sql += " WHERE format = ?"
            params = (fmt,)
        sql += " ORDER BY id"
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    if as_json:
        typer.echo(_json.dumps([dict(r) for r in rows], indent=2))
        return

    if not rows:
        typer.echo("No documents.")
        return
    for r in rows:
        typer.echo(f"{r['id']:>4}  {r['format']:<6}  {r['path']}")
        if r["summary"]:
            short = r["summary"].splitlines()[0][:90]
            typer.echo(f"      ↳ {short}")


@app.command()
def show(target: str) -> None:
    """Show metadata and chunks for a document (by id or path)."""
    cfg = load_config()
    _require_db(cfg)
    conn = get_connection(cfg.db_path)
    try:
        doc = _find_doc(conn, target)
        if doc is None:
            typer.echo(f"No document found for '{target}'.", err=True)
            raise typer.Exit(1)
        chunks = conn.execute(
            "SELECT id, seq, heading, content, start_line, end_line "
            "FROM chunks WHERE document_id = ? ORDER BY seq",
            (doc["id"],),
        ).fetchall()
    finally:
        conn.close()

    typer.echo(f"id:       {doc['id']}")
    typer.echo(f"path:     {doc['path']}")
    typer.echo(f"format:   {doc['format']}")
    typer.echo(f"ingested: {doc['ingested_at']}")
    typer.echo(f"hash:     {doc['content_hash']}")
    if doc["summary"]:
        typer.echo(f"summary:  {doc['summary']}")
    if doc["tags"]:
        typer.echo(f"tags:     {doc['tags']}")
    typer.echo(f"\nchunks ({len(chunks)}):")
    for c in chunks:
        head = f" [{c['heading']}]" if c["heading"] else ""
        typer.echo(f"  #{c['seq']}{head}  L{c['start_line']}-L{c['end_line']}")


@app.command()
def delete(target: str) -> None:
    """Delete a document from the knowledge base."""
    cfg = load_config()
    _require_db(cfg)
    conn = get_connection(cfg.db_path)
    try:
        doc = _find_doc(conn, target)
        if doc is None:
            typer.echo(f"No document found for '{target}'.", err=True)
            raise typer.Exit(1)
        delete_document(conn, doc["id"])
        conn.commit()
        typer.echo(f"Deleted document {doc['id']}: {doc['path']}")
    finally:
        conn.close()


@app.command()
def reindex(
    path: Path | None = typer.Argument(None, help="Optional file or dir to reindex; default: all known docs."),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Re-process documents whose content has changed (or all with --force)."""
    cfg = load_config()
    _require_db(cfg)
    conn = get_connection(cfg.db_path)
    try:
        if path is None:
            rows = conn.execute("SELECT path FROM documents ORDER BY id").fetchall()
            targets = [Path(r["path"]) for r in rows]
        else:
            targets = [path]

        results = []
        for p in targets:
            if not p.exists():
                typer.echo(f"  missing      {p}", err=True)
                continue
            results.extend(ingest_path(conn, p, force=force))
    finally:
        conn.close()

    counts: dict[str, int] = {}
    for path, status, _doc_id in results:
        counts[status] = counts.get(status, 0) + 1
        typer.echo(f"  {status:10s} {path}")
    if results:
        summary = "  ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        typer.echo(f"\nTotal: {len(results)} files. {summary}")
    else:
        typer.echo("Nothing to reindex.")


@app.command()
def search(
    text: str,
    limit: int = typer.Option(20, "--limit", "-n"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """BM25 search across the knowledge base."""
    cfg = load_config()
    _require_db(cfg)
    conn = get_connection(cfg.db_path)
    try:
        hits = run_search(conn, text, limit=limit)
    finally:
        conn.close()

    if as_json:
        typer.echo(_json.dumps([h.model_dump() for h in hits], indent=2))
        return

    if not hits:
        typer.echo("No matches.")
        return

    for h in hits:
        head = f" [{h.heading}]" if h.heading else ""
        typer.echo(f"score={h.score:.3f}  doc={h.document_id}{head}")
        typer.echo(f"  {h.path}")
        typer.echo(f"  {h.snippet}")
        typer.echo()


@app.command()
def query(
    text: str,
    limit: int = typer.Option(5, "--limit", "-n", help="Top-N reranked hits to return."),
    pool: int = typer.Option(20, "--pool", help="BM25 candidate pool size."),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """LLM-augmented search (BM25 → LLM rerank)."""
    cfg = load_config()
    _require_db(cfg)

    client = LLMClient(cfg)
    if not client.is_configured():
        typer.echo(
            "LLM not configured. Use `qkb search` for BM25-only, or set "
            "QKB_LLM_PROVIDER + QKB_LLM_MODEL (and QKB_LLM_BASE_URL / QKB_LLM_API_KEY).",
            err=True,
        )
        raise typer.Exit(1)

    conn = get_connection(cfg.db_path)
    try:
        bm25_hits = run_search(conn, text, limit=pool)
    finally:
        conn.close()

    if not bm25_hits:
        typer.echo("No matches.")
        return

    try:
        hits = llm_rerank(client, text, bm25_hits, top_n=limit)
    except LLMNotConfigured as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)
    except httpx.HTTPError as e:
        typer.echo(f"LLM request failed: {e}", err=True)
        raise typer.Exit(1)

    if as_json:
        typer.echo(_json.dumps([h.model_dump() for h in hits], indent=2))
        return

    for h in hits:
        head = f" [{h.heading}]" if h.heading else ""
        typer.echo(f"score={h.score:.2f}  doc={h.document_id}{head}")
        typer.echo(f"  {h.path}")
        typer.echo(f"  {h.snippet}")
        typer.echo()
