import hashlib
import logging
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import CourseMaterial, MaterialChunk, MaterialStatus
from app.services.errors import IngestionError, NotFoundError
from app.services.rag.chunking import chunk_pages
from app.services.rag.embeddings import get_embedder
from app.services.rag.pdf_loader import extract_document

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 64


def _validate_pdf(data: bytes) -> None:
    settings = get_settings()
    if not data:
        raise IngestionError("الملف فارغ")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise IngestionError(f"حجم الملف يتجاوز {settings.max_upload_mb} ميغابايت")
    if not data.startswith(b"%PDF-"):
        raise IngestionError("الملف ليس PDF صالحاً")


def _store_pdf(course_id: int, data: bytes, sha256: str) -> Path:
    settings = get_settings()
    directory = Path(settings.storage_dir).resolve() / str(course_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{sha256}.pdf"
    if not path.exists():
        path.write_bytes(data)
    return path


def register_material(
    db: Session,
    *,
    course_id: int,
    uploaded_by_user_id: int,
    title: str,
    original_filename: str,
    data: bytes,
) -> tuple[CourseMaterial, bool]:
    """
    يسجل الملزمة ويعيد (السجل، هل أُنشئ جديداً). إذا كانت النسخة نفسها جاهزة مسبقاً
    في المادة نفسها يُعاد السجل القائم دون معالجة مكررة.
    """
    _validate_pdf(data)
    sha256 = hashlib.sha256(data).hexdigest()

    existing = db.scalar(
        select(CourseMaterial).where(
            CourseMaterial.course_id == course_id,
            CourseMaterial.file_sha256 == sha256,
            CourseMaterial.status == MaterialStatus.READY,
        )
    )
    if existing is not None:
        return existing, False

    path = _store_pdf(course_id, data, sha256)
    material = CourseMaterial(
        course_id=course_id,
        uploaded_by_user_id=uploaded_by_user_id,
        title=title.strip()[:255],
        original_filename=original_filename[:512],
        storage_path=str(path),
        file_sha256=sha256,
        status=MaterialStatus.PENDING,
    )
    db.add(material)
    db.commit()
    db.refresh(material)
    return material, True


def run_ingestion(db: Session, material_id: int) -> str:
    """
    يستخرج النص ويقسمه ويضمّنه ويخزنه. يعيد الحالة النهائية (ready أو failed).
    أي فشل يُسجَّل في error_message ولا يترك الملزمة معلقة.
    """
    settings = get_settings()
    material = db.get(CourseMaterial, material_id)
    if material is None:
        raise NotFoundError("الملزمة غير موجودة")
    if material.status == MaterialStatus.READY:
        return MaterialStatus.READY.value

    material.status = MaterialStatus.PROCESSING
    db.commit()

    try:
        document = extract_document(material.storage_path)
        chunks = chunk_pages(document.pages, settings.chunk_size, settings.chunk_overlap)
        if not chunks:
            raise IngestionError("لم يُنتج التقسيم أي مقطع صالح")

        embedder = get_embedder()
        vectors: list[list[float]] = []
        for start in range(0, len(chunks), EMBED_BATCH_SIZE):
            batch = chunks[start:start + EMBED_BATCH_SIZE]
            vectors.extend(embedder.embed_documents([chunk.content for chunk in batch]))
        if len(vectors) != len(chunks):
            raise IngestionError("عدد التضمينات لا يطابق عدد المقاطع")

        db.execute(delete(MaterialChunk).where(MaterialChunk.material_id == material.id))
        for chunk, vector in zip(chunks, vectors):
            db.add(
                MaterialChunk(
                    material_id=material.id,
                    course_id=material.course_id,
                    chunk_index=chunk.index,
                    page_number=chunk.page_number,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    embedding=vector,
                )
            )

        material.page_count = document.total_pages
        material.status = MaterialStatus.READY
        material.error_message = None
        db.commit()
        return MaterialStatus.READY.value

    except Exception as exc:
        db.rollback()
        material = db.get(CourseMaterial, material_id)
        if material is not None:
            material.status = MaterialStatus.FAILED
            material.error_message = str(exc)[:1000]
            db.commit()
        if not isinstance(exc, IngestionError):
            logger.exception("فشل غير متوقع في معالجة الملزمة %s", material_id)
        return MaterialStatus.FAILED.value