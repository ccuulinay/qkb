import json

from qkb.llm.client import LLMClient

_PROMPT = """\
Summarize the following document. Output JSON with these keys:
- "summary": 2-3 sentence summary, max 300 characters.
- "tags": 3-7 lowercase keyword tags as a JSON array of strings.

Document:
---
{content}
---
"""


def summarize_file(
    client: LLMClient, content: str, *, max_chars: int = 24_000
) -> tuple[str, str]:
    """Returns (summary, comma-separated tags)."""
    truncated = content[:max_chars]
    messages = [
        {
            "role": "system",
            "content": "You summarize documents. Output only valid JSON.",
        },
        {"role": "user", "content": _PROMPT.format(content=truncated)},
    ]
    raw = client.chat(messages, json_mode=True)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw[:500], ""

    summary = str(data.get("summary", ""))[:500]
    tags_field = data.get("tags", [])
    if isinstance(tags_field, list):
        tags = ",".join(str(t).strip() for t in tags_field if str(t).strip())
    else:
        tags = str(tags_field)
    return summary, tags
