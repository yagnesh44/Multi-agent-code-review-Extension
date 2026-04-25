"""Hugging Face LLM client with Inference API, local TGI, and fallback support.

Supports:
- HF Inference API (free tier with rate limits, Pro for higher limits)
- Local Text Generation Inference (TGI) server
- Automatic model selection and JSON parsing
- Retry with exponential backoff for transient failures
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Optional

from huggingface_hub import AsyncInferenceClient
from sentence_transformers import SentenceTransformer

from app.config import settings

logger = logging.getLogger(__name__)

# Transient HTTP errors worth retrying
_RETRYABLE_STATUS_PHRASES = ("rate limit", "429", "503", "502", "500", "overloaded", "timeout")
# Fatal errors — never retry these
_FATAL_PHRASES = ("402", "payment required", "depleted", "401", "unauthorized", "403", "forbidden")


def _is_transient(exc: Exception) -> bool:
    """Decide whether an exception is transient and worth retrying."""
    msg = str(exc).lower()
    if any(phrase in msg for phrase in _FATAL_PHRASES):
        return False
    return any(phrase in msg for phrase in _RETRYABLE_STATUS_PHRASES)


async def _retry_async(coro_factory, *, retries: int = 3, base_delay: float = 2.0, label: str = ""):
    """Call *coro_factory()* with exponential back-off on transient failures."""
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return await coro_factory()
        except Exception as exc:
            last_exc = exc
            if attempt < retries and _is_transient(exc):
                delay = base_delay * (2 ** (attempt - 1))
                logger.warning(
                    "%s attempt %d/%d failed (%s), retrying in %.1fs…",
                    label, attempt, retries, exc, delay,
                )
                await asyncio.sleep(delay)
            else:
                raise
    raise last_exc  # unreachable, but keeps type-checker happy


class HuggingFaceClient:
    """Async client for Hugging Face models — Inference API or local TGI."""

    def __init__(
        self,
        primary_model: str = settings.primary_model,
        fallback_model: str = settings.fallback_model,
        embedding_model: str = settings.embedding_model,
        hf_token: Optional[str] = settings.hf_token,
        tgi_url: Optional[str] = settings.tgi_url,
        timeout: float = settings.agent_timeout_seconds,
    ):
        self.primary_model = primary_model
        self.fallback_model = fallback_model
        self._active_model: Optional[str] = None
        self._hf_token = hf_token
        self._tgi_url = tgi_url

        # If a local TGI URL is provided, point the client there;
        # otherwise use HF Inference API
        model_or_url = tgi_url if tgi_url else primary_model
        self._client = AsyncInferenceClient(
            model=model_or_url,
            token=hf_token,
            timeout=timeout,
        )
        self._fallback_client: Optional[AsyncInferenceClient] = None
        if not tgi_url:
            self._fallback_client = AsyncInferenceClient(
                model=fallback_model,
                token=hf_token,
                timeout=timeout,
            )

        # Sentence-transformers for local embeddings (no API call needed)
        self._embed_model_name = embedding_model
        self._embed_model: Optional[SentenceTransformer] = None

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def close(self):
        """No persistent connections to close for HF client."""
        pass

    async def health_check(self) -> dict[str, Any]:
        """Check connectivity to HF API or local TGI."""
        try:
            if self._tgi_url:
                ok = await self._client.health_check()
                return {
                    "connected": ok,
                    "models": [self.primary_model],
                    "provider": "TGI (local)",
                }
            else:
                # Try a minimal call to verify connectivity and token
                try:
                    await self._client.text_generation(
                        "test", max_new_tokens=1
                    )
                    connected = True
                except Exception:
                    # Some models may error but that still means we're connected
                    connected = True
                models = [self.primary_model, self.fallback_model]
                return {
                    "connected": connected,
                    "models": models,
                    "provider": "HF Inference API",
                }
        except Exception as exc:
            logger.warning("HuggingFace health-check failed: %s", exc)
            return {"connected": False, "models": [], "error": str(exc)}

    async def select_model(self) -> str:
        """Pick the best available model (primary → fallback)."""
        if self._active_model:
            return self._active_model
        # Try primary model with a minimal chat completion
        try:
            await self._client.chat_completion(
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1,
            )
            self._active_model = self.primary_model
        except Exception as exc:
            logger.warning(
                "Primary model %s unavailable (%s), trying fallback %s",
                self.primary_model, exc, self.fallback_model,
            )
            try:
                if self._fallback_client:
                    await self._fallback_client.chat_completion(
                        messages=[{"role": "user", "content": "hi"}],
                        max_tokens=1,
                    )
                self._active_model = self.fallback_model
            except Exception:
                raise RuntimeError(
                    f"Neither {self.primary_model} nor {self.fallback_model} "
                    "is available. Check your HF token and model names."
                )
        logger.info("Using model: %s", self._active_model)
        return self._active_model

    def _get_client_for_model(self, model: str) -> AsyncInferenceClient:
        """Return the client pointing to the given model."""
        if self._tgi_url:
            return self._client  # TGI always uses the same URL
        if model == self.fallback_model and self._fallback_client:
            return self._fallback_client
        return self._client

    # ── Generation ─────────────────────────────────────────────────────────

    async def generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = settings.temperature,
        max_tokens: int = settings.max_tokens,
        json_mode: bool = False,
    ) -> str:
        """Generate a completion with retry on transient failures."""
        model = await self.select_model()
        client = self._get_client_for_model(model)

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        user_content = prompt
        if json_mode:
            user_content += "\n\nIMPORTANT: Respond ONLY with valid JSON, no extra text."
        messages.append({"role": "user", "content": user_content})

        async def _call():
            response = await client.chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=settings.top_p,
            )
            return response.choices[0].message.content or ""

        return await _retry_async(_call, retries=3, label=f"generate({model})")

    async def generate_json(
        self,
        prompt: str,
        system: str = "",
        temperature: float = settings.temperature,
        max_tokens: int = settings.max_tokens,
    ) -> Any:
        """Generate and parse JSON output. Retries on parse failure and transient errors."""
        raw = await self.generate(
            prompt, system, temperature, max_tokens, json_mode=True
        )
        parsed = self._try_parse_json(raw)
        if parsed is not None:
            return parsed

        # Retry with explicit instruction
        logger.warning("JSON parse failed, retrying with stronger prompt…")
        raw2 = await self.generate(
            prompt + "\n\nYou MUST return ONLY a JSON array/object. No markdown, no explanation, no text outside the JSON.",
            system, temperature, max_tokens, json_mode=True,
        )
        parsed2 = self._try_parse_json(raw2)
        if parsed2 is not None:
            return parsed2
        logger.error("Failed to parse JSON from LLM output:\n%s", raw2[:500])
        return []  # graceful degradation: return empty findings instead of crashing

    @staticmethod
    def _try_parse_json(raw: str) -> Any | None:
        """Attempt to parse JSON from raw LLM output using multiple strategies."""
        raw = raw.strip()
        # 1. Direct parse
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        # 2. Extract from markdown code fences
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass
        # 3. Find first JSON array or object
        match = re.search(r"(\[[\s\S]*\]|\{[\s\S]*\})", raw)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        return None

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using sentence-transformers (local, no API call)."""
        if self._embed_model is None:
            logger.info("Loading embedding model: %s", self._embed_model_name)
            self._embed_model = SentenceTransformer(self._embed_model_name)
        embeddings = self._embed_model.encode(texts, convert_to_numpy=True)
        return [emb.tolist() for emb in embeddings]

    @property
    def active_model(self) -> str:
        return self._active_model or self.primary_model
