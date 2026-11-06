from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Smart Department Platform"
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = True

    database_url: str = "sqlite:///./sdp_local.db"
    redis_url: str = "redis://localhost:6379/0"
    celery_task_always_eager: bool = False

    jwt_secret_key: str = "change-me-to-a-long-random-string-at-least-32-chars"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60

    embedding_provider: Literal["huggingface", "openai", "stub"] = "huggingface"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 384
    openai_api_key: str | None = None

    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.0

    storage_dir: str = "./storage/materials"
    max_upload_mb: int = 50
    chunk_size: int = 1000
    chunk_overlap: int = 150

    rag_top_k: int = 5
    rag_min_similarity: float = 0.35
    quiz_max_questions: int = 20

    gap_alert_threshold: float = 0.30
    gap_cluster_similarity: float = 0.75
    gap_min_members: int = 2
    gap_alert_merge_similarity: float = 0.85

    request_classification_min_confidence: float = 0.6
    request_dedup_similarity: float = 0.85
    request_batch_sample_size: int = 30
    request_body_max_chars: int = 5000

    makeup_search_days: int = 14
    makeup_max_suggestions: int = 5
    makeup_excluded_weekdays: str = "4"
    lecture_reminder_minutes: int = 15
    schedule_stream_poll_seconds: float = 3.0
    schedule_stream_max_seconds: int = 300
    broadcast_body_max_chars: int = 5000

    cors_origins: str = "http://localhost:3000"

    timezone: str = "Asia/Baghdad"
    morning_digest_hour: int = 7

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def excluded_weekdays(self) -> frozenset[int]:
        return frozenset(int(x) for x in self.makeup_excluded_weekdays.split(",") if x.strip())

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()