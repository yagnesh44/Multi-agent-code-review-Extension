import os
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── LLM Provider ──────────────────────────────────────────────
    # Supported: "groq" (free, fast), "together", "openrouter",
    #            "huggingface", "ollama" (local), or any OpenAI-compatible
    llm_provider: str = "groq"

    # ── Generic OpenAI-compatible settings (Groq, Together, etc.) ─
    api_key: Optional[str] = None       # CRA_API_KEY — provider API key
    api_base_url: Optional[str] = None  # CRA_API_BASE_URL — override base URL
    api_model: Optional[str] = None     # CRA_API_MODEL — override model name

    # ── Ollama (local) ────────────────────────────────────────────
    ollama_url: str = "http://localhost:11434"
    ollama_model: Optional[str] = None

    # ── HuggingFace (legacy) ──────────────────────────────────────
    hf_token: Optional[str] = None
    tgi_url: Optional[str] = None
    primary_model: str = "Qwen/Qwen2.5-Coder-32B-Instruct"
    fallback_model: str = "bigcode/starcoder2-15b-instruct-v0.1"
    embedding_model: str = "all-MiniLM-L6-v2"  # sentence-transformers (runs locally)

    # LLM Parameters
    max_tokens: int = 2048
    temperature: float = 0.1
    top_p: float = 0.95
    repeat_penalty: float = 1.1

    # Agent Configuration
    concurrent_agents: int = 4
    agent_timeout_seconds: int = 600
    consensus_threshold: float = 0.6  # Min agreement ratio for findings

    # RAG Configuration
    chroma_persist_dir: str = "./data/chromadb"
    knowledge_base_dir: str = "./data/knowledge_base"
    rag_top_k: int = 5
    chunk_size: int = 512
    chunk_overlap: int = 64

    # Server
    host: str = "127.0.0.1"
    port: int = 19280
    cors_origins: list[str] = ["vscode-webview://*"]

    # Benchmark
    benchmark_dataset_dir: str = "./data/benchmark_datasets"

    @field_validator("temperature")
    @classmethod
    def _validate_temperature(cls, v: float) -> float:
        if not 0.0 <= v <= 2.0:
            raise ValueError("temperature must be between 0.0 and 2.0")
        return v

    @field_validator("top_p")
    @classmethod
    def _validate_top_p(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("top_p must be between 0.0 and 1.0")
        return v

    @field_validator("max_tokens")
    @classmethod
    def _validate_max_tokens(cls, v: int) -> int:
        if v < 1 or v > 32768:
            raise ValueError("max_tokens must be between 1 and 32768")
        return v

    @field_validator("concurrent_agents")
    @classmethod
    def _validate_concurrent_agents(cls, v: int) -> int:
        if v < 1 or v > 16:
            raise ValueError("concurrent_agents must be between 1 and 16")
        return v

    model_config = {
        "env_prefix": "CRA_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()

# Ensure data directories exist
for _dir in (settings.chroma_persist_dir, settings.benchmark_dataset_dir):
    os.makedirs(_dir, exist_ok=True)
