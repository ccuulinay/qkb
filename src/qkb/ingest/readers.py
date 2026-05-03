import csv
import json
from pathlib import Path
from typing import Callable

import yaml


def read_md(path: Path) -> tuple[str, dict]:
    return path.read_text(encoding="utf-8"), {}


def read_txt(path: Path) -> tuple[str, dict]:
    return path.read_text(encoding="utf-8"), {}


def _flatten(data, prefix: str = "") -> str:
    """Flatten dict/list/scalar JSON-or-YAML data to one 'key.path: value' line per leaf."""
    lines: list[str] = []
    if isinstance(data, dict):
        for k, v in data.items():
            new_prefix = f"{prefix}.{k}" if prefix else str(k)
            sub = _flatten(v, new_prefix)
            if sub:
                lines.append(sub)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            new_prefix = f"{prefix}[{i}]" if prefix else f"[{i}]"
            sub = _flatten(item, new_prefix)
            if sub:
                lines.append(sub)
    else:
        lines.append(f"{prefix}: {data}" if prefix else str(data))
    return "\n".join(lines)


def read_json(path: Path) -> tuple[str, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return _flatten(data), {}


def read_yaml(path: Path) -> tuple[str, dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return _flatten(data), {}


def read_csv(path: Path) -> tuple[str, dict]:
    rows: list[str] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=1):
            pairs = "; ".join(f"{k}={v}" for k, v in row.items() if v is not None)
            rows.append(f"row {i}: {pairs}")
    return "\n".join(rows), {"row_count": len(rows)}


EXT_MAP: dict[str, str] = {
    ".md": "md",
    ".markdown": "md",
    ".txt": "txt",
    ".text": "txt",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".csv": "csv",
}

READERS: dict[str, Callable[[Path], tuple[str, dict]]] = {
    "md": read_md,
    "txt": read_txt,
    "json": read_json,
    "yaml": read_yaml,
    "csv": read_csv,
}


def detect_format(path: Path) -> str | None:
    return EXT_MAP.get(path.suffix.lower())
