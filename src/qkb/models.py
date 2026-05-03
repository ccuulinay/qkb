from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class Config(BaseModel):
    data_dir: Path
    db_path: Path
    llm_provider: Literal["openai", "ollama", "disabled"] = "disabled"
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None


class Document(BaseModel):
    id: int
    path: str
    content_hash: str
    format: str
    ingested_at: datetime
    summary: str | None = None
    tags: str | None = None


class Chunk(BaseModel):
    id: int
    document_id: int
    seq: int
    heading: str | None = None
    content: str
    start_line: int | None = None
    end_line: int | None = None


class SearchHit(BaseModel):
    chunk_id: int
    document_id: int
    path: str
    heading: str | None = None
    snippet: str
    score: float
