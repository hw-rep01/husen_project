from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.core.permissions import role_has_permission
from app.db.session import get_db
from app.models import (
    Course,
    CourseInstructor,
    CourseMaterial,
    Enrollment,
    Quiz,
    QuizStatus,
    Room,
    Semester,
    User,
    UserRole,
)
from app.services.access import ensure_course_access

router = APIRouter(prefix="/api", tags=["catalog"])


class CourseOut(BaseModel):
    id: int
    code: str
    name_ar: str
    department_id: int


class RoomOut(BaseModel):
    id: int
    code: str
    name: str | None
    capacity: int
    is_available: bool


class QuizListItem(BaseModel):
    id: int
    title: str
    status: str
    question_count: int
    opens_at: datetime | None
    closes_at: datetime | None


class MaterialListItem(BaseModel):
    id: int
    title: str
    status: str
    page_count: int | None
    error_message: str | None
    created_at: datetime


@router.get("/courses", response_model=list[CourseOut])
def my_courses(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[CourseOut]:
    if user.role == UserRole.INSTRUCTOR:
        stmt = (
            select(Course)
            .join(CourseInstructor, CourseInstructor.course_id == Course.id)
            .where(CourseInstructor.instructor_id == user.id)
        )
    elif user.role in (UserRole.DEPARTMENT_COORDINATOR, UserRole.DEPARTMENT_HEAD):
        if user.department_id is None:
            return []
        stmt = select(Course).where(Course.department_id == user.department_id)
    elif user.role in (UserRole.STUDENT, UserRole.CLASS_REPRESENTATIVE):
        if user.section_id is None:
            return []
        stmt = (
            select(Course)
            .join(Enrollment, Enrollment.course_id == Course.id)
            .join(Semester, Semester.id == Enrollment.semester_id)
            .where(Enrollment.section_id == user.section_id, Semester.is_active.is_(True))
        )
    else:
        return []

    courses = db.scalars(stmt.distinct().order_by(Course.code)).all()
    return [
        CourseOut(id=c.id, code=c.code, name_ar=c.name_ar, department_id=c.department_id)
        for c in courses
    ]


@router.get("/rooms", response_model=list[RoomOut])
def available_rooms(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[RoomOut]:
    rooms = db.scalars(
        select(Room)
        .where(
            Room.is_available.is_(True),
            or_(Room.department_id.is_(None), Room.department_id == user.department_id),
        )
        .order_by(Room.code)
    ).all()
    return [
        RoomOut(id=r.id, code=r.code, name=r.name, capacity=r.capacity, is_available=r.is_available)
        for r in rooms
    ]


@router.get("/courses/{course_id}/quizzes", response_model=list[QuizListItem])
def course_quizzes(
    course_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[QuizListItem]:
    ensure_course_access(db, user, course_id)
    is_staff = role_has_permission(user.role, "quiz:create")
    stmt = select(Quiz).where(Quiz.course_id == course_id).order_by(Quiz.created_at.desc())
    if not is_staff:
        stmt = stmt.where(Quiz.status == QuizStatus.PUBLISHED)
    return [
        QuizListItem(
            id=q.id,
            title=q.title,
            status=q.status.value,
            question_count=len(q.questions),
            opens_at=q.opens_at,
            closes_at=q.closes_at,
        )
        for q in db.scalars(stmt).all()
    ]


@router.get("/courses/{course_id}/materials", response_model=list[MaterialListItem])
def course_materials(
    course_id: int,
    user: User = Depends(require_permission("rag:manage_material")),
    db: Session = Depends(get_db),
) -> list[MaterialListItem]:
    ensure_course_access(db, user, course_id)
    rows = db.scalars(
        select(CourseMaterial)
        .where(CourseMaterial.course_id == course_id)
        .order_by(CourseMaterial.created_at.desc())
    ).all()
    return [
        MaterialListItem(
            id=m.id,
            title=m.title,
            status=m.status.value,
            page_count=m.page_count,
            error_message=m.error_message,
            created_at=m.created_at,
        )
        for m in rows
    ]