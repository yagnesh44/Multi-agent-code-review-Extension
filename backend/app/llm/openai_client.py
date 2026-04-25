"""Generic OpenAI-compatible LLM client.

Works with any provider that implements the OpenAI chat completions API:
- Groq (free, fast) — https://console.groq.com
- Together AI — https://api.together.xyz
- OpenRouter — https://openrouter.ai
- Ollama (local) — http://localhost:11434/v1
- Any OpenAI-compatible endpoint

No vendor lock-in. Just set base_url + api_key + model.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Optional

import httpx
from sentence_transformers import SentenceTransformer

from app.config import settings

logger = logging.getLogger(__name__)

# Pre-configured providers — user just sets the API key
PROVIDERS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
        "models": [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
            "gemma2-9b-it",
        ],
    },
    "together": {
        "base_url": "https://api.together.xyz/v1",
        "default_model": "Qwen/Qwen2.5-Coder-32B-Instruct",
        "models": [
            "Qwen/Qwen2.5-Coder-32B-Instruct",
            "meta-llama/Llama-3.3-70B-Instruct-Turbo",
            "deepseek-ai/DeepSeek-V3",
        ],
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "qwen/qwen-2.5-coder-32b-instruct:free",
        "models": [
            "qwen/qwen-2.5-coder-32b-instruct:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "deepseek/deepseek-chat-v3-0324:free",
        ],
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "default_model": "qwen2.5-coder:7b",
        "models": [],
    },
}

# Fatal errors — never retry
_FATAL_PHRASES = ("402", "payment required", "401", "unauthorized", "403", "forbidden", "invalid api key", "invalid_api_key")
_RETRYABLE_PHRASES = ("429", "rate limit", "503", "502", "500", "overloaded", "timeout", "connection")


def _is_transient(exc: Exception) -> bool:
    msg = str(exc).lower()
    if any(p in msg for p in _FATAL_PHRASES):
        return False
    return any(p in msg for p in _RETRYABLE_PHRASES)


async def _retry_async(coro_factory, *, retries: int = 3, base_delay: float = 3.0, label: str = ""):
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return await coro_factory()
        except Exception as exc:
            last_exc = exc
            if attempt < retries and _is_transient(exc):
                msg = str(exc).lower()
                # Rate limits need longer backoff
                if "429" in msg or "rate limit" in msg:
                    delay = base_delay * (3 ** (attempt - 1))  # 3s, 9s, 27s
                else:
                    delay = base_delay * (2 ** (attempt - 1))
                logger.warning("%s attempt %d/%d failed (%s), retrying in %.1fs…", label, attempt, retries, exc, delay)
                await asyncio.sleep(delay)
            else:
                raise
    raise last_exc  # type: ignore[misc]


class OpenAICompatibleClient:
    """Async LLM client for any OpenAI-compatible API."""

    def __init__(
        self,
        provider: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        embedding_model: str = settings.embedding_model,
        timeout: float = settings.agent_timeout_seconds,
    ):
        # Resolve provider config
        provider = provider or settings.llm_provider
        provider_lower = provider.lower()
        provider_cfg = PROVIDERS.get(provider_lower, {})

        self._base_url = (base_url or settings.api_base_url or provider_cfg.get("base_url", "")).rstrip("/")
        self._api_key = api_key or settings.api_key or ""
        self._model = model or settings.api_model or provider_cfg.get("default_model", "")
        self._provider = provider_lower
        self._active_model: str | None = None
        self._timeout = timeout

        if not self._base_url:
            raise ValueError(
                f"No base_url configured for provider '{provider}'. "
                f"Set CRA_API_BASE_URL or use a known provider: {list(PROVIDERS.keys())}"
            )

        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._build_headers(),
            timeout=httpx.Timeout(timeout, connect=10.0),
        )

        # Sentence-transformers for local embeddings
        self._embed_model_name = embedding_model
        self._embed_model: SentenceTransformer | None = None
        self._model_lock = asyncio.Lock()

    def _build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def close(self):
        await self._http.aclose()

    async def health_check(self) -> dict[str, Any]:
        try:
            resp = await self._http.get("/models", timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                model_list = [m.get("id", m.get("name", "")) for m in data.get("data", data.get("models", []))]
                return {"connected": True, "models": model_list, "provider": self._provider}
            # Some providers don't have /models, try a minimal completion
            return {"connected": True, "models": [self._model], "provider": self._provider}
        except Exception as exc:
            logger.warning("Health check failed for %s: %s", self._provider, exc)
            return {"connected": False, "models": [], "error": str(exc)}

    async def select_model(self) -> str:
        if self._active_model:
            return self._active_model
        async with self._model_lock:
            if self._active_model:
                return self._active_model
            # Trust the configured model without a test call to save rate limit
            self._active_model = self._model
            logger.info("Using model: %s (provider: %s)", self._active_model, self._provider)
            return self._active_model

    # ── Generation ─────────────────────────────────────────────────────────

    async def generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = settings.temperature,
        max_tokens: int = settings.max_tokens,
        json_mode: bool = False,
    ) -> str:
        model = await self.select_model()

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        user_content = prompt
        if json_mode:
            user_content += "\n\nIMPORTANT: Respond ONLY with valid JSON, no extra text."
        messages.append({"role": "user", "content": user_content})

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": settings.top_p,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        async def _call():
            resp = await self._http.post(
                "/chat/completions",
                json=payload,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"] or ""

        return await _retry_async(_call, retries=3, label=f"generate({self._provider}/{model})")

    async def generate_json(
        self,
        prompt: str,
        system: str = "",
        temperature: float = settings.temperature,
        max_tokens: int = settings.max_tokens,
    ) -> Any:
        raw = await self.generate(prompt, system, temperature, max_tokens, json_mode=True)
        parsed = self._try_parse_json(raw)
        if parsed is not None:
            return parsed

        logger.warning("JSON parse failed, retrying with stronger prompt…")
        raw2 = await self.generate(
            prompt + "\n\nYou MUST return ONLY a JSON array/object. No markdown, no explanation, no text outside the JSON.",
            system, temperature, max_tokens, json_mode=True,
        )
        parsed2 = self._try_parse_json(raw2)
        if parsed2 is not None:
            return parsed2
        logger.error("Failed to parse JSON:\n%s", raw2[:500])
        return []

    @staticmethod
    def _try_parse_json(raw: str) -> Any | None:
        raw = raw.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass
        match = re.search(r"(\[[\s\S]*\]|\{[\s\S]*\})", raw)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        return None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._embed_model is None:
            logger.info("Loading embedding model: %s", self._embed_model_name)
            self._embed_model = SentenceTransformer(self._embed_model_name)
        embeddings = self._embed_model.encode(texts, convert_to_numpy=True)
        return [emb.tolist() for emb in embeddings]

    @property
    def active_model(self) -> str:
        return self._active_model or self._model
