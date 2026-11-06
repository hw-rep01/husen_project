import numpy as np
from sklearn.cluster import AgglomerativeClustering

from app.services.common.vector_math import normalize_rows


def cluster_embeddings(vectors: np.ndarray, min_similarity: float) -> np.ndarray:
    """
    تجميع هرمي تراكمي بمسافة جيب التمام. النقاط التي تتشابه بمقدار
    أكبر من min_similarity بمتوسط الربط تُجمع في عنقود واحد.
    """
    if vectors.ndim != 2:
        raise ValueError("المدخل يجب أن يكون مصفوفة ثنائية الأبعاد")
    if not 0.0 < min_similarity < 1.0:
        raise ValueError("min_similarity يجب أن يكون بين 0 و 1")

    count = vectors.shape[0]
    if count == 0:
        return np.zeros(0, dtype=int)
    if count == 1:
        return np.zeros(1, dtype=int)

    model = AgglomerativeClustering(
        n_clusters=None,
        metric="cosine",
        linkage="average",
        distance_threshold=1.0 - min_similarity,
    )
    return model.fit_predict(normalize_rows(vectors))


def centroid_of(vectors: np.ndarray) -> np.ndarray:
    """مركز ثقل متجهات العنقود بعد التطبيع، وهو مركز على سطح الوحدة."""
    mean = normalize_rows(vectors).mean(axis=0, keepdims=True)
    return normalize_rows(mean)[0]


def most_central_index(vectors: np.ndarray, centroid: np.ndarray) -> int:
    """فهرس العضو الأقرب إلى المركز، ويُستخدم نصه كعنوان للعنقود."""
    similarities = normalize_rows(vectors) @ centroid
    return int(np.argmax(similarities))