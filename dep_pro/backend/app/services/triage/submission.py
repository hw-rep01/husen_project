from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import RequestCategory, RequestStatus, RoutingStage, Section, StudentRequest, User
from app.services.access import ensure_course_access
from app.services.errors import BusinessRuleError
from app.services.rag.embeddings import get_embedder
from app.services.triage.classifier import classify_request
from app.services.triage.deduplication import attach_on_submit
from app.services.triage.events import record_event
from app.services.triage.notify import notify_stage


def submit_request(
    db: Session,
    actor: User,
    *,
    subject: str,
    body: str,
    course_id: int | None,
) -> StudentRequest:
    if actor.section_id is None:
        raise BusinessRuleError("الحساب غير مرتبط بشعبة، لا يمكن تقديم طلب")

    subject = subject.strip()
    body = body.strip()
    if len(body) < 10:
        raise BusinessRuleError("نص الطلب قصير جداً")

    if course_id is not None:
        ensure_course_access(db, actor, course_id)

    settings = get_settings()
    text = f"{subject}\n{body}"

    # التضمين مطلوب للدمج الدلالي، فإن تعذر (مثلاً مفتاح مفقود) يفشل الإرسال بوضوح
    embedding = get_embedder().embed_query(text)

    result = classify_request(subject, body)
    category: RequestCategory | None = None
    confidence: float | None = None
    if result is not None:
        confidence = result.confidence
        if result.confidence >= settings.request_classification_min_confidence:
            category = RequestCategory(result.category)

    now = datetime.now(timezone.utc)
    request = StudentRequest(
        student_id=actor.id,
        section_id=actor.section_id,
        course_id=course_id,
        subject=subject[:255],
        body=body[: settings.request_body_max_chars],
        category=category,
        classification_confidence=confidence,
        status=RequestStatus.IN_SECTION_REVIEW,
        current_stage=RoutingStage.CLASS_REPRESENTATIVE,
        embedding=embedding,
    )
    db.add(request)
    db.flush()

    record_event(
        db,
        action="submitted",
        actor_user_id=actor.id,
        request_id=request.id,
        to_stage=RoutingStage.CLASS_REPRESENTATIVE,
    )
    attach_on_submit(db, request, actor.id)

    section = db.get(Section, actor.section_id)
    notify_stage(
        db,
        RoutingStage.CLASS_REPRESENTATIVE,
        section.id,
        None,
        title="طلب جديد من طلاب الشعبة",
        body=f"وصل طلب جديد بعنوان: {request.subject}",
        now=now,
    )

    db.commit()
    db.refresh(request)
    return request