from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import (
    CourseInstructor,
    RequestBatch,
    RequestCategory,
    RequestEvent,
    RoutingStage,
    Section,
    StudentRequest,
    User,
    UserRole,
)
from app.services.errors import AccessDeniedError

ROLE_STAGE: dict[UserRole, RoutingStage] = {
    UserRole.INSTRUCTOR: RoutingStage.INSTRUCTOR,
    UserRole.DEPARTMENT_COORDINATOR: RoutingStage.DEPARTMENT_COORDINATOR,
    UserRole.DEPARTMENT_HEAD: RoutingStage.DEPARTMENT_HEAD,
}


@dataclass(frozen=True)
class UnitView:
    kind: str
    id: int
    section_id: int
    category: str | None
    course_id: int | None
    title: str
    summary: str
    request_count: int
    status: str
    current_stage: str
    created_at: datetime


def view_of_unit(batch: RequestBatch | None, requests: list[StudentRequest]) -> UnitView:
    if batch is not None:
        return UnitView(
            kind="batch",
            id=batch.id,
            section_id=batch.section_id,
            category=batch.category.value,
            course_id=batch.course_id,
            title=batch.title,
            summary=batch.formal_summary,
            request_count=batch.request_count,
            status=batch.status.value,
            current_stage=batch.current_stage.value,
            created_at=batch.created_at,
        )
    first = requests[0]
    return UnitView(
        kind="request",
        id=first.id,
        section_id=first.section_id,
        category=first.category.value if first.category else None,
        course_id=first.course_id,
        title=first.subject,
        summary=first.body,
        request_count=1,
        status=first.status.value,
        current_stage=first.current_stage.value,
        created_at=first.created_at,
    )


def build_unit_views(db: Session, requests: list[StudentRequest]) -> list[UnitView]:
    batch_ids = {r.batch_id for r in requests if r.batch_id is not None}
    batches: dict[int, RequestBatch] = {}
    if batch_ids:
        batches = {
            b.id: b
            for b in db.scalars(select(RequestBatch).where(RequestBatch.id.in_(batch_ids))).all()
        }

    views: list[UnitView] = []
    seen: set[int] = set()
    for request in requests:
        if request.batch_id is None:
            views.append(view_of_unit(None, [request]))
            continue
        if request.batch_id in seen:
            continue
        seen.add(request.batch_id)
        views.append(view_of_unit(batches[request.batch_id], [request]))
    return views


def taught_course_ids(db: Session, user: User) -> list[int]:
    return list(
        db.scalars(
            select(CourseInstructor.course_id).where(CourseInstructor.instructor_id == user.id)
        ).all()
    )


def _reached(db: Session, request_id: int, stage: RoutingStage) -> bool:
    return db.scalar(
        select(RequestEvent.id)
        .where(RequestEvent.request_id == request_id, RequestEvent.to_stage == stage)
        .limit(1)
    ) is not None


def can_view_request(db: Session, user: User, request: StudentRequest) -> bool:
    if user.role == UserRole.STUDENT:
        return request.student_id == user.id
    if user.role == UserRole.CLASS_REPRESENTATIVE:
        return user.section_id is not None and request.section_id == user.section_id
    if user.role == UserRole.INSTRUCTOR:
        return (
            request.category == RequestCategory.ACADEMIC
            and request.course_id is not None
            and request.course_id in taught_course_ids(db, user)
            and _reached(db, request.id, RoutingStage.INSTRUCTOR)
        )
    if user.role in ROLE_STAGE and user.role != UserRole.INSTRUCTOR:
        section_department = db.scalar(select(Section.department_id).where(Section.id == request.section_id))
        return (
            request.category == RequestCategory.ADMINISTRATIVE
            and user.department_id is not None
            and section_department == user.department_id
            and _reached(db, request.id, ROLE_STAGE[user.role])
        )
    return False


def student_requests(db: Session, user: User) -> list[StudentRequest]:
    return list(
        db.scalars(
            select(StudentRequest)
            .where(StudentRequest.student_id == user.id)
            .order_by(desc(StudentRequest.created_at))
        ).all()
    )


def section_requests(db: Session, user: User) -> list[StudentRequest]:
    if user.section_id is None:
        return []
    return list(
        db.scalars(
            select(StudentRequest)
            .where(StudentRequest.section_id == user.section_id)
            .order_by(desc(StudentRequest.created_at))
        ).all()
    )


def inbox_requests(db: Session, user: User) -> list[StudentRequest]:
    """قائمة الوارد للمراحل الإدارية والأكاديمية: الطلبات الموجودة في مرحلة هذا المستخدم."""
    if user.role == UserRole.INSTRUCTOR:
        course_ids = taught_course_ids(db, user)
        if not course_ids:
            return []
        stmt = select(StudentRequest).where(
            StudentRequest.category == RequestCategory.ACADEMIC,
            StudentRequest.course_id.in_(course_ids),
            StudentRequest.current_stage == RoutingStage.INSTRUCTOR,
        )
    elif user.role in (UserRole.DEPARTMENT_COORDINATOR, UserRole.DEPARTMENT_HEAD):
        if user.department_id is None:
            return []
        stmt = (
            select(StudentRequest)
            .join(Section, Section.id == StudentRequest.section_id)
            .where(
                Section.department_id == user.department_id,
                StudentRequest.category == RequestCategory.ADMINISTRATIVE,
                StudentRequest.current_stage == ROLE_STAGE[user.role],
            )
        )
    else:
        raise AccessDeniedError("لا يوجد وارد مخصص لهذا الدور")
    return list(db.scalars(stmt.order_by(desc(StudentRequest.created_at))).all())