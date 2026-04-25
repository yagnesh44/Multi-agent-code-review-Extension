"""Ollama LLM client — fully local, no API keys needed.

Uses Ollama's OpenAI-compatible API endpoint for chat completions.
Provides the same interface as HuggingFaceClient so the orchestrator
doesn't need to know which backend is in use.
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

# Default Ollama URL
_DEFAULT_OLLAMA_URL = "http://localhost:11434"

# Models ranked by quality for code review (Ollama names)
_CODE_MODELS = [
    "qwen2.5-coder:14b",
    "qwen2.5-coder:7b",
    "qwen2.5-coder:3b",
    "codellama:13b",
    "codellama:7b",
    "deepseek-coder-v2:16b",
    "deepseek-coder:6.7b",
    "llama3.1:8b",
]


async def _retry_async(coro_factory, *, retries: int = 2, base_delay: float = 1.0, label: str = ""):
    """Retry with exponential back-off on transient failures."""
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return await coro_factory()
        except Exception as exc:
            last_exc = exc
            msg = str(exc).lower()
            transient = any(k in msg for k in ("timeout", "503", "502", "connection"))
            if attempt < retries and transient:
                delay = base_delay * (2 ** (attempt - 1))
                logger.warning("%s attempt %d/%d failed (%s), retrying…", label, attempt, retries, exc, )
                await asyncio.sleep(delay)
            else:
                raise
    raise last_exc  # type: ignore[misc]


class OllamaClient:
    """Async client for Ollama local models."""

    def __init__(
        self,
        ollama_url: str = _DEFAULT_OLLAMA_URL,
        primary_model: str | None = None,
        embedding_model: str = settings.embedding_model,
        timeout: float = settings.agent_timeout_seconds,
    ):
        self._base_url = ollama_url.rstrip("/")
        self._requested_model = primary_model
        self._active_model: str | None = None
        self._timeout = timeout

        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout, connect=10.0),
        )

        # Sentence-transformers for local embeddings (same as HF client)
        self._embed_model_name = embedding_model
        self._embed_model: SentenceTransformer | None = None

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def close(self):
        await self._http.aclose()

    async def health_check(self) -> dict[str, Any]:
        """Check Ollama connectivity and list local models."""
        try:
            resp = await self._http.get("/api/tags", timeout=5.0)
            resp.raise_for_status()
            data = resp.json()
            model_names = [m["name"] for m in data.get("models", [])]
            return {
                "connected": True,
                "models": model_names,
                "provider": "Ollama (local)",
            }
        except Exception as exc:
            logger.warning("Ollama health-check failed: %s", exc)
            return {"connected": False, "models": [], "error": str(exc)}

    async def select_model(self) -> str:
        """Pick the best available model from Ollama's local models."""
        if self._active_model:
            return self._active_model

        # Get list of locally available models
        try:
            resp = await self._http.get("/api/tags", timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            local_models = {m["name"] for m in data.get("models", [])}
            # Also match without tag (e.g. "qwen2.5-coder:7b" matches "qwen2.5-coder:7b")
            local_base = set()
            for m in local_models:
                local_base.add(m)
                # Add variant without :latest
                if ":latest" in m:
                    local_base.add(m.replace(":latest", ""))
        except Exception as exc:
            raise RuntimeError(f"Cannot connect to Ollama at {self._base_url}: {exc}")

        if not local_models:
            raise RuntimeError(
                "No models found in Ollama. Pull one with:\n"
                "  ollama pull qwen2.5-coder:7b"
            )

        # If user specified a model, try that first
        if self._requested_model and self._requested_model in local_base:
            self._active_model = self._requested_model
            logger.info("Using requested model: %s", self._active_model)
            return self._active_model

        # Auto-select best available code model
        for candidate in _CODE_MODELS:
            if candidate in local_base:
                self._active_model = candidate
                logger.info("Auto-selected model: %s", self._active_model)
                return self._active_model

        # Fall back to whatever is available
        self._active_model = next(iter(local_models))
        logger.info("Falling back to first available model: %s", self._active_model)
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
        """Generate a chat completion via Ollama's OpenAI-compatible API."""
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
            "options": {
                "temperature": temperature,
                "top_p": settings.top_p,
                "num_predict": max_tokens,
            },
            "stream": False,
        }
        if json_mode:
            payload["format"] = "json"

        async def _call():
            resp = await self._http.post(
                "/api/chat",
                json=payload,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "")

        return await _retry_async(_call, retries=2, label=f"ollama({model})")

    async def generate_json(
        self,
        prompt: str,
        system: str = "",
        temperature: float = settings.temperature,
        max_tokens: int = settings.max_tokens,
    ) -> Any:
        """Generate and parse JSON output."""
        raw = await self.generate(prompt, system, temperature, max_tokens, json_mode=True)
        parsed = self._try_parse_json(raw)
        if parsed is not None:
            return parsed

        # Retry with explicit instruction
        logger.warning("JSON parse failed, retrying with stronger prompt…")
        raw2 = await self.generate(
            prompt + "\n\nYou MUST return ONLY a JSON array/object. No markdown, no explanation.",
            system, temperature, max_tokens, json_mode=True,
        )
        parsed2 = self._try_parse_json(raw2)
        if parsed2 is not None:
            return parsed2
        logger.error("Failed to parse JSON from Ollama output:\n%s", raw2[:500])
        return []

    @staticmethod
    def _try_parse_json(raw: str) -> Any | None:
        """Parse JSON from raw LLM output using multiple strategies."""
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
        """Generate embeddings using sentence-transformers (local)."""
        if self._embed_model is None:
            logger.info("Loading embedding model: %s", self._embed_model_name)
            self._embed_model = SentenceTransformer(self._embed_model_name)
        embeddings = self._embed_model.encode(texts, convert_to_numpy=True)
        return [emb.tolist() for emb in embeddings]

    @property
    def active_model(self) -> str:
        return self._active_model or "none"
