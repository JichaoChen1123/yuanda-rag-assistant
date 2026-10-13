"""源答 · SaaS 知识助手配置。

通过环境变量或 .env 覆盖设置，本机认证与配置不写入公开文档。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- App ----
    app_name: str = "源答 · SaaS 知识助手"
    app_version: str = "0.1.0"
    environment: Literal["dev", "staging", "prod"] = "dev"
    log_level: str = "INFO"

    # ---- Paths ----
    project_root: Path = Path(__file__).resolve().parents[2]
    documents_dir: Path = Field(default_factory=lambda: Path("documents"))
    data_dir: Path = Field(default_factory=lambda: Path("data"))

    # ---- Vector DB ----
    vector_backend: Literal["chroma", "qdrant"] = "chroma"
    chroma_persist_dir: str = "data/chroma"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    collection_name: str = "enterprise_docs"

    # ---- Embeddings ----
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_device: Literal["cpu", "cuda", "mps"] = "cpu"
    embedding_batch_size: int = 32
    embedding_dim: int = 384  # bge-small / e5-small

    # ---- Chunking ----
    chunk_size: int = 512  # tokens (approximate)
    chunk_overlap: int = 64
    min_chunk_chars: int = 50

    # ---- Retrieval ----
    top_k_vector: int = 20
    top_k_bm25: int = 20
    top_k_final: int = 5
    hybrid_alpha: float = 0.5  # weight for vector vs bm25 in RRF fallback

    # ---- Reranking ----
    enable_reranking: bool = True
    reranker_model: str = "BAAI/bge-reranker-base"
    rerank_top_n: int = 5

    # ---- LLM Providers ----
    llm_provider: Literal["ollama", "openai", "anthropic", "codex"] = "ollama"
    llm_fallback_order: list[str] = ["ollama", "openai", "anthropic"]

    # Optional subscription adapter; the original RAG pipeline is unchanged.
    codex_binary: str = "codex"
    codex_model: str = ""
    codex_timeout: int = 180

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "mistral"
    ollama_timeout: int = 120

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-3-5-haiku-20241022"

    # ---- Generation ----
    max_tokens: int = 1024
    temperature: float = 0.1  # low for factuality
    confidence_threshold: float = 0.5

    # ---- API ----
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list[str] = ["*"]

    # ---- Cache ----
    redis_url: str | None = None  # if set, enables response caching


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
