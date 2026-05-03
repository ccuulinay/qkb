from dataclasses import dataclass


@dataclass
class ChunkOut:
    seq: int
    heading: str | None
    content: str
    start_line: int
    end_line: int


_MD_HEADER_PREFIXES = ("# ", "## ", "### ")
_MAX_SECTION_CHARS = 1500
_WINDOW = 800
_OVERLAP = 100


def _window_text(
    text: str,
    base_seq: int,
    heading: str | None,
    base_line: int,
) -> list[ChunkOut]:
    """Sliding-window split for long text. Returns chunks starting at base_seq."""
    if not text:
        return []
    if len(text) <= _WINDOW:
        end_line = base_line + text.count("\n")
        return [ChunkOut(base_seq, heading, text, base_line, end_line)]

    step = _WINDOW - _OVERLAP
    out: list[ChunkOut] = []
    pos = 0
    seq = base_seq
    while pos < len(text):
        piece = text[pos : pos + _WINDOW]
        start_line = base_line + text[:pos].count("\n")
        end_line = start_line + piece.count("\n")
        out.append(ChunkOut(seq, heading, piece, start_line, end_line))
        seq += 1
        if pos + _WINDOW >= len(text):
            break
        pos += step
    return out


def chunk_md(text: str) -> list[ChunkOut]:
    """Split markdown by H1/H2/H3. Long sections get sliding windows."""
    lines = text.splitlines()
    sections: list[tuple[str | None, int, int, str]] = []
    current_heading: str | None = None
    current_start = 1
    current_lines: list[str] = []

    for i, line in enumerate(lines, start=1):
        if line.startswith(_MD_HEADER_PREFIXES):
            if current_lines:
                sections.append(
                    (current_heading, current_start, i - 1, "\n".join(current_lines))
                )
            current_heading = line.lstrip("#").strip()
            current_start = i
            current_lines = [line]
        else:
            current_lines.append(line)
    if current_lines:
        sections.append(
            (current_heading, current_start, len(lines), "\n".join(current_lines))
        )

    out: list[ChunkOut] = []
    seq = 0
    for heading, start, _end, content in sections:
        if not content.strip():
            continue
        if len(content) <= _MAX_SECTION_CHARS:
            end_line = start + content.count("\n")
            out.append(ChunkOut(seq, heading, content, start, end_line))
            seq += 1
        else:
            windows = _window_text(content, seq, heading, start)
            out.extend(windows)
            seq += len(windows)
    return out


def chunk_text(text: str) -> list[ChunkOut]:
    """Plain-text or flattened structured data: char-windowed."""
    return _window_text(text, 0, None, 1)


def chunk_csv(text: str) -> list[ChunkOut]:
    """One chunk per pre-formatted 'row N: ...' line."""
    out: list[ChunkOut] = []
    for seq, line in enumerate(text.splitlines()):
        if not line.strip():
            continue
        out.append(ChunkOut(seq, None, line, seq + 1, seq + 1))
    return out


def chunk_for_format(fmt: str, text: str) -> list[ChunkOut]:
    if fmt == "md":
        return chunk_md(text)
    if fmt == "csv":
        return chunk_csv(text)
    return chunk_text(text)
