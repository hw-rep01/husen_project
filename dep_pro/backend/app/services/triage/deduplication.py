from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import RequestBatch, RequestCategory, RequestStatus, RoutingStage, StudentRequest
from app.services.common.vector_math import cosine_similarity, to_matrix
from app.services.gaps.clustering import centroid_of, cluster_embeddings
from app.services.triage.events import record_event
from app.services.triage.summarizer import summarize_batch

REP = RoutingStage.CLASS_REPRESENTATIVE
OPEN_STATUS = RequestStatus.IN_SECTION_REVIEW


def _scope_conditions(model, section_id: int, category: RequestCategory, course_id: int | None) -> list:
    """
    نطاق الدمج: الأكاديمي يُدمج فقط داخل المادة نفسها، والإداري داخل القسم كله.
    """
    conditions = [model.section_id == section_id, model.category == category]
    if category == RequestCategory.ACADEMIC:
        conditions.append(model.course_id == course_id)
    return conditions


def _open_conditions(model) -> list:
    return [model.current_stage == REP, model.status == OPEN_STATUS]


def _batch_centroid(vectors: list[list[float]]) -> list[float]:
    return centroid_of(to_matrix(vectors)).tolist()


def _members(db: Session, batch_id: int) -> list[StudentRequest]:
    return list(
        db.scalars(
            select(StudentRequest)
            .where(StudentRequest.batch_id == batch_id)
            .order_by(StudentRequest.id)
        ).all()
    )


def _loose_candidates(
    db: Session,
    section_id: int,
    category: RequestCategory,
    course_id: int | None,
    exclude_id: int | None = None,
) -> list[StudentRequest]:
    stmt = select(StudentRequest).where(
        *_scope_conditions(StudentRequest, section_id, category, course_id),
        *_open_conditions(StudentRequest),
        StudentRequest.batch_id.is_(None),
        StudentRequest.embedding.is_not(None),
    )
    if exclude_id is not None:
        stmt = stmt.where(StudentRequest.id != exclude_id)
    return list(db.scalars(stmt).all())


def _create_batch(db: Session, members: list[StudentRequest], actor_user_id: int | None) -> RequestBatch:
    first = members[0]
    category = first.category
    course_id = first.course_id if category == RequestCategory.ACADEMIC else None

    texts = [f"{m.subject}\n{m.body}" for m in members]
    summary = summarize_batch(texts, category, len(members))

    batch = RequestBatch(
        section_id=first.section_id,
        course_id=course_id,
        category=category,
        title=summary.title,
        formal_summary=summary.formal_summary,
        request_count=len(members),
        centroid=_batch_centroid([m.embedding for m in members]),
        status=OPEN_STATUS,
        current_stage=REP,
    )
    db.add(batch)
    db.flush()

    for member in members:
        member.batch_id = batch.id
        member.status = RequestStatus.MERGED
        record_event(
            db,
            action="merged",
            actor_user_id=actor_user_id,
            request_id=member.id,
            batch_id=batch.id,
            from_stage=REP,
            to_stage=REP,
        )
    record_event(
        db,
        action="batch_created",
        actor_user_id=actor_user_id,
        batch_id=batch.id,
        from_stage=REP,
        to_stage=REP,
        note=f"{len(members)} طلبات متشابهة",
    )
    return batch


def attach_on_submit(db: Session, request: StudentRequest, actor_user_id: int | None) -> int | None:
    """
    يُستدعى عند تقديم طلب جديد أو تصنيفه. يحاول إلحاقه ببطاقة مفتوحة متشابهة،
    فإن لم يجد يبحث عن طلب منفرد متشابه ليشكّلا بطاقة جديدة.
    يعيد معرّف البطاقة إن وُجدت.
    """
    if request.category is None or request.embedding is None or request.batch_id is not None:
        return None
    if request.category == RequestCategory.ACADEMIC and request.course_id is None:
        return None

    threshold = get_settings().request_dedup_similarity
    course_id = request.course_id if request.category == RequestCategory.ACADEMIC else None

    # 1) إلحاق بالبطاقة القائمة الأقرب
    best_batch: RequestBatch | None = None
    best_score = threshold
    open_batches = db.scalars(
        select(RequestBatch).where(
            *_scope_conditions(RequestBatch, request.section_id, request.category, course_id),
            *_open_conditions(RequestBatch),
        )
    ).all()
    for batch in open_batches:
        if batch.centroid is None:
            continue
        score = cosine_similarity(batch.centroid, request.embedding)
        if score >= best_score:
            best_batch, best_score = batch, score

    if best_batch is not None:
        request.batch_id = best_batch.id
        request.status = RequestStatus.MERGED
        record_event(
            db,
            action="merged",
            actor_user_id=actor_user_id,
            request_id=request.id,
            batch_id=best_batch.id,
            from_stage=REP,
            to_stage=REP,
        )
        db.flush()
        members = _members(db, best_batch.id)
        best_batch.request_count = len(members)
        best_batch.centroid = _batch_centroid([m.embedding for m in members if m.embedding is not None])
        return best_batch.id

    # 2) تكوين بطاقة جديدة مع طلب منفرد متشابه
    best_peer: StudentRequest | None = None
    best_score = threshold
    for peer in _loose_candidates(db, request.section_id, request.category, course_id, exclude_id=request.id):
        score = cosine_similarity(peer.embedding, request.embedding)
        if score >= best_score:
            best_peer, best_score = peer, score

    if best_peer is None:
        return None
    return _create_batch(db, [best_peer, request], actor_user_id).id


def consolidate_section(db: Session, section_id: int, actor_user_id: int | None) -> int:
    """
    تجميع شامل: يعيد تجميع كل الطلبات المنفردة المفتوحة في الشعبة بالتجميع الهرمي،
    ويُنشئ بطاقة لكل عنقود يضم طلبين أو أكثر. يعيد عدد البطاقات المنشأة.
    """
    threshold = get_settings().request_dedup_similarity
    candidates = list(
        db.scalars(
            select(StudentRequest).where(
                StudentRequest.section_id == section_id,
                *_open_conditions(StudentRequest),
                StudentRequest.batch_id.is_(None),
                StudentRequest.category.is_not(None),
                StudentRequest.embedding.is_not(None),
            )
        ).all()
    )

    groups: dict[tuple[RequestCategory, int | None], list[StudentRequest]] = {}
    for request in candidates:
        if request.category == RequestCategory.ACADEMIC and request.course_id is None:
            continue
        key = (request.category, request.course_id if request.category == RequestCategory.ACADEMIC else None)
        groups.setdefault(key, []).append(request)

    created = 0
    for members in groups.values():
        if len(members) < 2:
            continue
        labels = cluster_embeddings(to_matrix([m.embedding for m in members]), threshold).tolist()
        for label in sorted(set(labels)):
            picked = [members[i] for i, current in enumerate(labels) if current == label]
            if len(picked) >= 2:
                _create_batch(db, picked, actor_user_id)
                created += 1

    db.commit()
    return created


def refresh_batch_summary(db: Session, batch: RequestBatch) -> RequestBatch:
    members = _members(db, batch.id)
    summary = summarize_batch(
        [f"{m.subject}\n{m.body}" for m in members],
        batch.category,
        len(members),
    )
    batch.title = summary.title
    batch.formal_summary = summary.formal_summary
    db.commit()
    db.refresh(batch)
    return batch