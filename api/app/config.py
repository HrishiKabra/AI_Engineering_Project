"""Application settings.

Reconciles the repo's existing `.env` (which defines ``OPENAI_KEY``) with the
OpenAI SDK + Ragas, which both look for ``OPENAI_API_KEY``. We read either name
and export ``OPENAI_API_KEY`` into the process environment on startup.
"""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- OpenAI (accept either OPENAI_KEY or OPENAI_API_KEY) ---
    openai_key: str = Field(default="", validation_alias="OPENAI_KEY")
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")

    # --- database ---
    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/f1rag",
        validation_alias="DATABASE_URL",
    )

    # --- models ---
    chat_model: str = Field(default="gpt-4o-mini", validation_alias="CHAT_MODEL")
    embed_model: str = Field(default="openai", validation_alias="EMBED_MODEL")  # 'openai' | 'bge'
    temperature: float = Field(default=0.1, validation_alias="TEMPERATURE")
    max_tokens: int = Field(default=700, validation_alias="MAX_TOKENS")

    # --- retrieval ---
    retrieval_mode: str = Field(default="hybrid", validation_alias="RETRIEVAL_MODE")  # dense|sparse|hybrid
    top_k: int = Field(default=5, validation_alias="TOP_K")
    candidate_k: int = Field(default=20, validation_alias="CANDIDATE_K")
    rrf_k: int = Field(default=60, validation_alias="RRF_K")
    rerank_enabled: bool = Field(default=False, validation_alias="RERANK_ENABLED")

    # --- agent / guardrails ---
    grade_pass_threshold: float = Field(default=0.7, validation_alias="GRADE_PASS_THRESHOLD")
    grade_refuse_threshold: float = Field(default=0.5, validation_alias="GRADE_REFUSE_THRESHOLD")
    max_retrieval_attempts: int = Field(default=2, validation_alias="MAX_RETRIEVAL_ATTEMPTS")

    @property
    def resolved_openai_key(self) -> str:
        return self.openai_api_key or self.openai_key

    def export_openai_env(self) -> None:
        """Make the key visible to the OpenAI SDK + Ragas under their expected name.

        Overwrites an empty ``OPENAI_API_KEY`` (docker-compose may inject it as "")
        which would otherwise shadow our resolved key.
        """
        key = self.resolved_openai_key
        if key and not os.environ.get("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = key


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.export_openai_env()
    return settings
