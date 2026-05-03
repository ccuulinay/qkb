import httpx

from qkb.models import Config

_DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "ollama": "http://localhost:11434/v1",
}


class LLMNotConfigured(RuntimeError):
    pass


class LLMClient:
    """Thin OpenAI-compatible chat-completions client."""

    def __init__(self, cfg: Config, *, timeout: float = 120.0):
        self.cfg = cfg
        self.timeout = timeout

    def is_configured(self) -> bool:
        return (
            self.cfg.llm_provider != "disabled"
            and self.cfg.llm_model is not None
        )

    def _base_url(self) -> str:
        return self.cfg.llm_base_url or _DEFAULT_BASE_URLS.get(
            self.cfg.llm_provider, ""
        )

    def chat(
        self,
        messages: list[dict],
        *,
        json_mode: bool = False,
        temperature: float = 0.0,
    ) -> str:
        if not self.is_configured():
            raise LLMNotConfigured(
                "LLM not configured. Set QKB_LLM_PROVIDER, QKB_LLM_MODEL, "
                "QKB_LLM_BASE_URL (and QKB_LLM_API_KEY for hosted providers)."
            )

        base = self._base_url()
        if not base:
            raise LLMNotConfigured(
                f"No base URL for provider {self.cfg.llm_provider!r}; "
                "set QKB_LLM_BASE_URL."
            )

        url = f"{base.rstrip('/')}/chat/completions"
        payload: dict = {
            "model": self.cfg.llm_model,
            "messages": messages,
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {"Content-Type": "application/json"}
        if self.cfg.llm_api_key:
            headers["Authorization"] = f"Bearer {self.cfg.llm_api_key}"

        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()

        return data["choices"][0]["message"]["content"]
