"""API routes for the Code Review Agent backend."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from app.agents.orchestrator import Orchestrator
from app.api.schemas import (
    BenchmarkRequest,
    BenchmarkResult,
    HealthResponse,
    ReviewRequest,
    ReviewResponse,
)
from app.benchmark.evaluator import BenchmarkEvaluator
from app.benchmark.reporter import generate_text_report, save_json_report
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Singletons (initialised in lifespan) ──────────────────────────────────────
_llm = None  # HuggingFaceClient or OllamaClient
_orchestrator: Orchestrator | None = None
_knowledge_base = None
_init_lock = asyncio.Lock()
_review_semaphore = asyncio.Semaphore(3)  # max concurrent reviews


def _create_llm_client():
    """Create the appropriate LLM client based on configuration."""
    provider = settings.llm_provider.lower()

    if provider == "huggingface":
        from app.llm.hf_client import HuggingFaceClient
        logger.info("Using HuggingFace Inference API")
        return HuggingFaceClient()
    else:
        # All other providers use the OpenAI-compatible client
        # (groq, together, openrouter, ollama, custom)
        from app.llm.openai_client import OpenAICompatibleClient
        logger.info("Using OpenAI-compatible provider: %s", provider)
        return OpenAICompatibleClient(provider=provider)


async def initialize():
    """Called once during app startup."""
    async with _init_lock:
        global _llm, _orchestrator, _knowledge_base
        if _orchestrator is not None:
            return  # already initialised
        _llm = _create_llm_client()
        from app.rag.knowledge_base import KnowledgeBase, RAGRetriever
        _knowledge_base = KnowledgeBase(_llm)
        await _knowledge_base.initialize()
        _orchestrator = Orchestrator(_llm)
        await _orchestrator.set_rag_retriever(RAGRetriever(_knowledge_base))
        logger.info("Backend initialized successfully.")


async def shutdown():
    global _llm
    if _llm:
        await _llm.close()


def _get_orchestrator() -> Orchestrator:
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    return _orchestrator


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Check server health and HuggingFace connectivity."""
    if _llm is None:
        return HealthResponse(
            status="initializing",
            llm_connected=False,
            models_available=[],
            active_model="none",
        )
    info = await _llm.health_check()
    return HealthResponse(
        status="ok" if info["connected"] else "llm_disconnected",
        llm_connected=info["connected"],
        models_available=info.get("models", []),
        active_model=_llm.active_model,
    )


@router.post("/review", response_model=ReviewResponse)
async def review_code(request: ReviewRequest):
    """Run a full multi-agent code review on the submitted code."""
    orchestrator = _get_orchestrator()
    if not request.code.strip():
        raise HTTPException(status_code=400, detail="Code cannot be empty")
    if len(request.code) > 500_000:
        raise HTTPException(status_code=413, detail="Code too large (max 500KB)")

    # Backpressure: limit concurrent reviews
    if _review_semaphore.locked():
        logger.warning("Review rejected: too many concurrent requests")
        raise HTTPException(status_code=429, detail="Too many concurrent reviews. Please retry shortly.")

    async with _review_semaphore:
        try:
            return await asyncio.wait_for(
                orchestrator.review(request),
                timeout=settings.agent_timeout_seconds + 60,
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Review timed out. Try a smaller file or fewer agents.")
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        except Exception as exc:
            logger.exception("Review failed")
            raise HTTPException(status_code=500, detail="Internal review error. Check server logs.")


@router.post("/benchmark", response_model=BenchmarkResult)
async def run_benchmark(request: BenchmarkRequest):
    """Run the evaluation benchmark against a ground-truth dataset."""
    orchestrator = _get_orchestrator()
    evaluator = BenchmarkEvaluator(orchestrator)
    try:
        result = evaluator.load_dataset(request.dataset)  # validate dataset exists
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    try:
        result = await evaluator.evaluate(request.dataset)
        # Log text report
        report = generate_text_report(result)
        logger.info("\n%s", report)
        # Save JSON report
        path = save_json_report(result)
        logger.info("Report saved to %s", path)
        return result
    except Exception as exc:
        logger.exception("Benchmark failed")
        raise HTTPException(status_code=500, detail=f"Benchmark failed: {exc}")


@router.get("/models")
async def list_models():
    """List available models."""
    if _llm is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    info = await _llm.health_check()
    return {"models": info.get("models", []), "active": _llm.active_model}
