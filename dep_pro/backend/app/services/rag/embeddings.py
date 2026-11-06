import hashlib
import math
import re
from functools import lru_cache
from typing import Protocol

from app.core.config import get_settings
from app.services.errors import LLMNotConfiguredError


class Embedder(Protocol):
    dimension: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class HuggingFaceEmbedder:
    """تضمين محلي عبر sentence-transformers. يعمل بدون إنترنت بعد أول تحميل للنموذج."""

    def __init__(self, model_name: str, dimension: int) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        actual = self._model.get_sentence_embedding_dimension()
        if actual != dimension:
            raise ValueError(
                f"بُعد النموذج {actual} لا يطابق EMBEDDING_DIMENSION={dimension}. "
                "حدّث الإعداد وأعد تضمين الملازم."
            )
        self.dimension = dimension

    def _encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(
            texts,
            batch_size=32,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return vectors.astype(float).tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._encode([text])[0]


class OpenAIEmbedder:
    def __init__(self, model: str, dimension: int, api_key: str) -> None:
        from langchain_openai import OpenAIEmbeddings

        # dimensions تضمن أن الناتج يطابق الجدول حتى لو كان النموذج يدعم أبعاداً أكبر
        self._client = OpenAIEmbeddings(model=model, dimensions=dimension, api_key=api_key)
        self.dimension = dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._client.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._client.embed_query(text)


class StubEmbedder:
    """
    مُضمِّن حتمي بالتجزئة (feature hashing) للاختبارات وبيئة E2E فقط.
    لا يفهم المعنى، بل يشابه النصوص التي تشترك في كلماتها.
    ممنوع في بيئة الإنتاج، ويُرفض في get_embedder إذا كانت APP_ENV=production.
    """

    def __init__(self, dimension: int) -> None:
        self.dimension = dimension

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dimension
        for token in re.findall(r"\w+", text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[index] += sign
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


@lru_cache
def get_embedder() -> Embedder:
    settings = get_settings()
    if settings.embedding_provider == "stub":
        if settings.app_env == "production":
            raise LLMNotConfiguredError("مُضمِّن الاختبار (stub) ممنوع في بيئة الإنتاج.")
        return StubEmbedder(settings.embedding_dimension)
    if settings.embedding_provider == "openai":
        if not settings.openai_api_key:
            raise LLMNotConfiguredError("OPENAI_API_KEY غير مضبوط لاستخدام تضمينات OpenAI.")
        return OpenAIEmbedder(
            model=settings.openai_embedding_model,
            dimension=settings.embedding_dimension,
            api_key=settings.openai_api_key,
        )
    return HuggingFaceEmbedder(
        model_name=settings.embedding_model,
        dimension=settings.embedding_dimension,
    )