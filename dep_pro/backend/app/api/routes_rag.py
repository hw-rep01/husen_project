from datetime import datetime, timezone
from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.core.permissions import role_has_permission
from app.db.session import get_db
from app.models import CourseMaterial, GapAlert, GapAlertStatus, Quiz, QuizStatus, User
from app.services.access import ensure_course_access, ensure_quiz_access
from app.services.errors import AccessDeniedError, NotFoundError
from app.services.gaps.radar import run_radar_for_course
from app.services.rag.ingestion import register_material
from app.services.rag.quiz_service import generate_quiz, publish_quiz, submit_attempt
from app.services.rag.retrieval import RetrievedChunk
from app.services.rag.tutor import answer_question, summarize_topic
from app.workers.tasks import ingest_material_task

router = APIRouter(prefix="/api", tags=["rag"])


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=2000)


class SummaryIn(BaseModel):
    topic: str = Field(min_length=2, max_length=300)


class SourceOut(BaseModel):
    chunk_id: int
    material_title: str
    page_number: int | None
    similarity: float
    excerpt: str


class AnswerOut(BaseModel):
    answer: str
    grounded: bool
    question_id: int | None
    sources: list[SourceOut]


class QuizCreateIn(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    question_count: int = Field(ge=1, le=20)


class PublishIn(BaseModel):
    opens_at: datetime | None = None
    closes_at: datetime | None = None


class AttemptIn(BaseModel):
    answers: dict[int, int]


class QuizQuestionOut(BaseModel):
    id: int
    position: int
    question_type: str
    question_text: str
    options: list[str]
    correct_option_index: int | None = None
    explanation: str | None = None


class QuizOut(BaseModel):
    id: int
    course_id: int
    title: str
    status: str
    opens_at: datetime | None
    closes_at: datetime | None
    questions: list[QuizQuestionOut]


class AlertOut(BaseModel):
    id: int
    course_id: int
    section_id: int
    topic_label: str
    distinct_student_count: int
    section_student_total: int
    affected_ratio: float
    summary: str
    status: str
    created_at: datetime


def _source_out(chunk: RetrievedChunk) -> SourceOut:
    excerpt = chunk.content if len(chunk.content) <= 300 else chunk.content[:300] + "…"
    return SourceOut(
        chunk_id=chunk.chunk_id,
        material_title=chunk.material_title,
        page_number=chunk.page_number,
        similarity=round(chunk.similarity, 4),
        excerpt=excerpt,
    )


def _load_quiz(db: Session, quiz_id: int) -> Quiz:
    quiz = db.get(Quiz, quiz_id)
    if quiz is None:
        raise NotFoundError("الكويز غير موجود")
    return quiz


def _quiz_out(quiz: Quiz, reveal_answers: bool) -> QuizOut:
    return QuizOut(
        id=quiz.id,
        course_id=quiz.course_id,
        title=quiz.title,
        status=quiz.status.value,
        opens_at=quiz.opens_at,
        closes_at=quiz.closes_at,
        questions=[
            QuizQuestionOut(
                id=q.id,
                position=q.position,
                question_type=q.question_type.value,
                question_text=q.question_text,
                options=q.options,
                correct_option_index=q.correct_option_index if reveal_answers else None,
                explanation=q.explanation if reveal_answers else None,
            )
            for q in quiz.questions
        ],
    )


def _alert_out(a: GapAlert) -> AlertOut:
    return AlertOut(
        id=a.id,
        course_id=a.course_id,
        section_id=a.section_id,
        topic_label=a.topic_label,
        distinct_student_count=a.distinct_student_count,
        section_student_total=a.section_student_total,
        affected_ratio=a.affected_ratio,
        summary=a.summary,
        status=a.status.value,
        created_at=a.created_at,
    )


@router.post("/courses/{course_id}/materials", status_code=202)
async def upload_material(
    course_id: int,
    title: str = Form(..., min_length=3, max_length=255),
    file: UploadFile = File(...),
    user: User = Depends(require_permission("rag:manage_material")),
    db: Session = Depends(get_db),
) -> dict:
    ensure_course_access(db, user, course_id)
    data = await file.read()
    material, created = register_material(
        db,
        course_id=course_id,
        uploaded_by_user_id=user.id,
        title=title,
        original_filename=file.filename or "material.pdf",
        data=data,
    )
    if created:
        ingest_material_task.delay(material.id)
    return {"material_id": material.id, "status": material.status.value, "duplicate": not created}


@router.get("/materials/{material_id}")
def get_material_status(
    material_id: int,
    user: User = Depends(require_permission("rag:manage_material")),
    db: Session = Depends(get_db),
) -> dict:
    material = db.get(CourseMaterial, material_id)
    if material is None:
        raise NotFoundError("الملزمة غير موجودة")
    ensure_course_access(db, user, material.course_id)
    return {
        "material_id": material.id,
        "title": material.title,
        "status": material.status.value,
        "page_count": material.page_count,
        "error_message": material.error_message,
    }


@router.post("/courses/{course_id}/ask", response_model=AnswerOut)
def ask_tutor(
    course_id: int,
    payload: AskIn,
    user: User = Depends(require_permission("rag:ask")),
    db: Session = Depends(get_db),
) -> AnswerOut:
    course = ensure_course_access(db, user, course_id)
    result = answer_question(db, user, course, payload.question)
    return AnswerOut(
        answer=result.answer,
        grounded=result.grounded,
        question_id=result.question_id,
        sources=[_source_out(s) for s in result.sources],
    )


@router.post("/courses/{course_id}/summary", response_model=AnswerOut)
def summarize(
    course_id: int,
    payload: SummaryIn,
    user: User = Depends(require_permission("rag:ask")),
    db: Session = Depends(get_db),
) -> AnswerOut:
    course = ensure_course_access(db, user, course_id)
    result = summarize_topic(db, course, payload.topic)
    return AnswerOut(
        answer=result.answer,
        grounded=result.grounded,
        question_id=None,
        sources=[_source_out(s) for s in result.sources],
    )


@router.post("/courses/{course_id}/quizzes", response_model=QuizOut, status_code=201)
def create_quiz(
    course_id: int,
    payload: QuizCreateIn,
    user: User = Depends(require_permission("quiz:create")),
    db: Session = Depends(get_db),
) -> QuizOut:
    course = ensure_course_access(db, user, course_id)
    quiz = generate_quiz(db, course, user.id, payload.title, payload.question_count)
    return _quiz_out(quiz, reveal_answers=True)


@router.post("/quizzes/{quiz_id}/publish", response_model=QuizOut)
def publish(
    quiz_id: int,
    payload: PublishIn,
    user: User = Depends(require_permission("quiz:create")),
    db: Session = Depends(get_db),
) -> QuizOut:
    quiz = _load_quiz(db, quiz_id)
    ensure_quiz_access(db, user, quiz)
    quiz = publish_quiz(db, quiz, payload.opens_at, payload.closes_at)
    return _quiz_out(quiz, reveal_answers=True)


@router.get("/quizzes/{quiz_id}", response_model=QuizOut)
def get_quiz(
    quiz_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QuizOut:
    quiz = _load_quiz(db, quiz_id)
    ensure_quiz_access(db, user, quiz)
    is_staff = role_has_permission(user.role, "quiz:create")
    if not is_staff:
        if not role_has_permission(user.role, "quiz:take"):
            raise AccessDeniedError("لا تملك صلاحية عرض الكويزات")
        if quiz.status != QuizStatus.PUBLISHED:
            raise NotFoundError("الكويز غير موجود")
    return _quiz_out(quiz, reveal_answers=is_staff)


@router.post("/quizzes/{quiz_id}/attempts")
def attempt_quiz(
    quiz_id: int,
    payload: AttemptIn,
    user: User = Depends(require_permission("quiz:take")),
    db: Session = Depends(get_db),
) -> dict:
    quiz = _load_quiz(db, quiz_id)
    ensure_quiz_access(db, user, quiz)
    attempt = submit_attempt(db, quiz, user, payload.answers)
    return {"attempt_id": attempt.id, "score": attempt.score}


@router.get("/courses/{course_id}/gaps", response_model=list[AlertOut])
def list_gap_alerts(
    course_id: int,
    user: User = Depends(require_permission("gaps:view_course")),
    db: Session = Depends(get_db),
) -> list[AlertOut]:
    ensure_course_access(db, user, course_id)
    alerts = db.scalars(
        select(GapAlert)
        .where(GapAlert.course_id == course_id, GapAlert.instructor_id == user.id)
        .order_by(GapAlert.created_at.desc())
    ).all()
    return [_alert_out(a) for a in alerts]


@router.post("/courses/{course_id}/gaps/run")
def run_gap_radar(
    course_id: int,
    user: User = Depends(require_permission("gaps:view_course")),
    db: Session = Depends(get_db),
) -> dict:
    ensure_course_access(db, user, course_id)
    results = run_radar_for_course(db, course_id)
    return {
        "scopes_processed": len(results),
        "alerts_created": sum(r.alerts_created for r in results),
        "alerts_updated": sum(r.alerts_updated for r in results),
    }


@router.post("/gaps/{alert_id}/acknowledge", response_model=AlertOut)
def acknowledge_alert(
    alert_id: int,
    user: User = Depends(require_permission("gaps:view_course")),
    db: Session = Depends(get_db),
) -> AlertOut:
    alert = db.get(GapAlert, alert_id)
    if alert is None or alert.instructor_id != user.id:
        raise NotFoundError("التنبيه غير موجود")
    alert.status = GapAlertStatus.ACKNOWLEDGED
    alert.acknowledged_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(alert)
    return _alert_out(alert)