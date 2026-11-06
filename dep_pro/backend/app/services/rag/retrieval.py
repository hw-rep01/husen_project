from dataclasses import dataclass

import numpy as np
from pgvector.sqlalchemy import Vector
from sqlalchemy import literal, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import CourseMaterial, MaterialChunk, MaterialStatus
from app.services.common.vector_math import cosine_similarity_matrix, to_matrix


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: int
    material_id: int
    material_title: str
    page_number: int | None
    content: str
    similarity: float


def search_course(
    db: Session,
    course_id: int,
    query_vector: list[float],
    top_k: int | None = None,
) -> list[RetrievedChunk]:
    """
    يعيد أقرب المقاطع لاستعلام داخل ملازم مادة معينة فقط (لا يتسرب محتوى مادة لأخرى).
    على PostgreSQL يتم الترتيب داخل قاعدة البيانات بمؤشر pgvector،
    وعلى SQLite يتم الحساب في الذاكرة للتجربة المحلية.
    """
    k = top_k or get_settings().rag_top_k
    if db.get_bind().dialect.name == "postgresql":
        return _search_postgres(db, course_id, query_vector, k)
    return _search_in_python(db, course_id, query_vector, k)


def _search_postgres(db: Session, course_id: int, query_vector: list[float], k: int) -> list[RetrievedChunk]:
    dimension = get_settings().embedding_dimension
    query_param = literal(query_vector, type_=Vector(dimension))
    distance = MaterialChunk.embedding.op("<=>")(query_param)

    stmt = (
        select(MaterialChunk, CourseMaterial.title, distance.label("distance"))
        .join(CourseMaterial, CourseMaterial.id == MaterialChunk.material_id)
        .where(
            MaterialChunk.course_id == course_id,
            CourseMaterial.status == MaterialStatus.READY,
            MaterialChunk.embedding.is_not(None),
        )
        .order_by(distance)
        .limit(k)
    )
    rows = db.execute(stmt).all()
    return [
        RetrievedChunk(
            chunk_id=chunk.id,
            material_id=chunk.material_id,
            material_title=title,
            page_number=chunk.page_number,
            content=chunk.content,
            similarity=float(1.0 - dist),
        )
        for chunk, title, dist in rows
    ]


def _search_in_python(db: Session, course_id: int, query_vector: list[float], k: int) -> list[RetrievedChunk]:
    stmt = (
        select(MaterialChunk, CourseMaterial.title)
        .join(CourseMaterial, CourseMaterial.id == MaterialChunk.material_id)
        .where(
            MaterialChunk.course_id == course_id,
            CourseMaterial.status == MaterialStatus.READY,
            MaterialChunk.embedding.is_not(None),
        )
    )
    rows = db.execute(stmt).all()
    if not rows:
        return []

    corpus = to_matrix([chunk.embedding for chunk, _ in rows])
    query = to_matrix([query_vector])
    similarities = cosine_similarity_matrix(query, corpus)[0]
    order = np.argsort(-similarities)[:k]

    results: list[RetrievedChunk] = []
    for position in order:
        chunk, title = rows[int(position)]
        results.append(
            RetrievedChunk(
                chunk_id=chunk.id,
                material_id=chunk.material_id,
                material_title=title,
                page_number=chunk.page_number,
                content=chunk.content,
                similarity=float(similarities[position]),
            )
        )
    return results