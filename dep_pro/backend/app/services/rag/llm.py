from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.services.errors import LLMNotConfiguredError


@lru_cache
def get_chat_model() -> ChatOpenAI:
    settings = get_settings()
    if not settings.openai_api_key:
        raise LLMNotConfiguredError(
            "OPENAI_API_KEY غير مضبوط. مطلوب لتوليد الإجابات والتلخيصات والكويزات."
        )
    return ChatOpenAI(
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        api_key=settings.openai_api_key,
        timeout=60,
        max_retries=2,
    )