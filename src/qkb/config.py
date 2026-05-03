import os
import tomllib
from pathlib import Path

from qkb.models import Config


def _default_data_dir() -> Path:
    return Path.home() / ".qkb"


def _read_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def load_config() -> Config:
    data_dir = Path(os.getenv("QKB_DATA_DIR") or _default_data_dir())
    file_data = _read_toml(data_dir / "config.toml")

    db_path_str = os.getenv("QKB_DB_PATH") or file_data.get("db_path")
    db_path = Path(db_path_str) if db_path_str else data_dir / "index.sqlite"

    return Config(
        data_dir=data_dir,
        db_path=db_path,
        llm_provider=os.getenv("QKB_LLM_PROVIDER") or file_data.get("llm_provider") or "disabled",
        llm_base_url=os.getenv("QKB_LLM_BASE_URL") or file_data.get("llm_base_url"),
        llm_model=os.getenv("QKB_LLM_MODEL") or file_data.get("llm_model"),
        llm_api_key=os.getenv("QKB_LLM_API_KEY") or file_data.get("llm_api_key"),
    )
