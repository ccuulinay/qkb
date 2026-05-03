import json

from qkb.llm.client import LLMClient
from qkb.models import SearchHit

_PROMPT = """\
User query: {query}

Below are {n} candidate snippets, numbered. Rank them by relevance to the query.
Output JSON: {{"ranked": [{{"id": <int>, "score": <float 0-10>}}, ...]}}.
Most relevant first. Include only items with score >= 1.

Snippets:
{snippets}
"""


def rerank(
    client: LLMClient,
    query: str,
    hits: list[SearchHit],
    *,
    top_n: int = 5,
) -> list[SearchHit]:
    if not hits:
        return []

    snippets = "\n".join(f"[{i}] {h.snippet}" for i, h in enumerate(hits))
    messages = [
        {
            "role": "system",
            "content": "You rank search snippets by relevance. Output only valid JSON.",
        },
        {
            "role": "user",
            "content": _PROMPT.format(query=query, n=len(hits), snippets=snippets),
        },
    ]
    raw = client.chat(messages, json_mode=True)
    try:
        data = json.loads(raw)
        ranked = data.get("ranked", [])
    except json.JSONDecodeError:
        return hits[:top_n]

    out: list[SearchHit] = []
    seen: set[int] = set()
    for entry in ranked:
        idx = entry.get("id") if isinstance(entry, dict) else None
        score = entry.get("score", 0) if isinstance(entry, dict) else 0
        if not isinstance(idx, int) or idx in seen or not (0 <= idx < len(hits)):
            continue
        seen.add(idx)
        try:
            score_f = float(score)
        except (TypeError, ValueError):
            score_f = 0.0
        out.append(hits[idx].model_copy(update={"score": score_f}))
        if len(out) >= top_n:
            break

    return out or hits[:top_n]
