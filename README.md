# qkb — local knowledge-base CLI

A small CLI for ingesting and querying local knowledge files (markdown, plain text, JSON, YAML, CSV) using SQLite FTS5 BM25, with optional LLM-powered summarization on ingest and reranking on query.

## Install

Requires Python 3.12+.

### From PyPI

```bash
pip install qkb
# or, with uv:
uv tool install qkb
```

### From source

```bash
git clone https://github.com/ccuulinay/qkb
cd qkb
uv sync
uv pip install -e .
```

After install, `qkb` is on your PATH. (Or run any command via `uv run qkb …`.)

## Quick start

```bash
# Initialize the database (creates ~/.qkb/index.sqlite)
qkb init

# Ingest some files
qkb ingest examples/

# See what's there
qkb list
qkb status

# BM25 search — no LLM required
qkb search "user_id"
qkb search "Postgres"

# Show a single document's metadata + chunk layout
qkb show 1

# Drop a document
qkb delete 1
```

## LLM features (optional)

With an LLM configured, ingest stores a generated summary and tags per document, and `qkb query` does BM25 → LLM rerank for higher-quality results.

Configure once via env vars or `qkb config set`:

```bash
# OpenAI
export QKB_LLM_PROVIDER=openai
export QKB_LLM_MODEL=gpt-4o-mini
export QKB_LLM_API_KEY=sk-...

# Or local Ollama
qkb config set llm_provider ollama
qkb config set llm_base_url http://localhost:11434/v1
qkb config set llm_model llama3.1:8b

# Then:
qkb ingest examples/
qkb query "how do we handle authentication?"
```

`qkb config list` prints the effective configuration. Env vars override `~/.qkb/config.toml`.

## Commands

| Command | Purpose |
| --- | --- |
| `qkb init` | Create the data directory and database |
| `qkb ingest <paths>... [-r] [--no-llm] [--force]` | Ingest files or directories |
| `qkb list [--format md] [--json]` | List ingested documents |
| `qkb show <id\|path>` | Show metadata and chunk layout |
| `qkb delete <id\|path>` | Remove a document |
| `qkb reindex [<path>] [--force]` | Reprocess changed (or all) documents |
| `qkb search <query> [-n 20] [--json]` | BM25 search, no LLM needed |
| `qkb query <question> [-n 5] [--pool 20] [--json]` | BM25 → LLM rerank |
| `qkb status` | Database stats |
| `qkb config list\|get\|set` | Read/write configuration |

## Storage

Single SQLite file at `~/.qkb/index.sqlite` (override with `QKB_DATA_DIR` or `QKB_DB_PATH`). Schema: `documents` (one row per file), `chunks` (header- or window-bounded fragments), `chunks_fts` (FTS5 BM25 index over chunk content + heading + summary).

## Supported formats

| Extension | Strategy |
| --- | --- |
| `.md`, `.markdown` | Split by H1/H2/H3 headings; long sections sliding-windowed |
| `.txt`, `.text` | Sliding 800-char windows with 100-char overlap |
| `.json` | Flattened to `key.path: value` lines per leaf |
| `.yaml`, `.yml` | Flattened to `key.path: value` lines per leaf |
| `.csv` | One chunk per row, formatted `row N: col=val; …` |

## Testing

```bash
pytest -q
```

The test suite uses an in-memory SQLite database and a mocked LLM client — no network required.
