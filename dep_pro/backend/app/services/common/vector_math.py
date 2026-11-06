from collections.abc import Sequence

import numpy as np


def to_matrix(vectors: Sequence[Sequence[float]]) -> np.ndarray:
    return np.asarray(vectors, dtype=np.float32)


def normalize_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return matrix / norms


def cosine_similarity_matrix(queries: np.ndarray, corpus: np.ndarray) -> np.ndarray:
    """يعيد مصفوفة (عدد الاستعلامات × عدد الوثائق) من قيم التشابه بين -1 و 1."""
    return normalize_rows(queries) @ normalize_rows(corpus).T


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    va = np.asarray(a, dtype=np.float32)
    vb = np.asarray(b, dtype=np.float32)
    denominator = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if denominator == 0.0:
        return 0.0
    return float(np.dot(va, vb) / denominator)