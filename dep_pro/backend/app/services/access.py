from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Course, CourseInstructor, Enrollment, Quiz, Semester, User, UserRole
from app.services.errors import AccessDeniedError, NotFoundError

DEPARTMENT_ROLES = {UserRole.DEPARTMENT_HEAD, UserRole.DEPARTMENT_COORDINATOR}
SECTION_ROLES = {UserRole.STUDENT, UserRole.CLASS_REPRESENTATIVE}


def ensure_course_access(db: Session, user: User, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise NotFoundError("المادة غير موجودة")

    if user.role == UserRole.INSTRUCTOR:
        allowed = db.scalar(
            select(CourseInstructor.id).where(
                CourseInstructor.course_id == course.id,
                CourseInstructor.instructor_id == user.id,
            )
        ) is not None
    elif user.role in DEPARTMENT_ROLES:
        allowed = user.department_id == course.department_id
    elif user.role in SECTION_ROLES:
        allowed = user.section_id is not None and db.scalar(
            select(Enrollment.id)
            .join(Semester, Semester.id == Enrollment.semester_id)
            .where(
                Enrollment.course_id == course.id,
                Enrollment.section_id == user.section_id,
                Semester.is_active.is_(True),
            )
            .limit(1)
        ) is not None
    else:
        allowed = False

    if not allowed:
        raise AccessDeniedError("لا تملك صلاحية الوصول لهذه المادة")
    return course


def ensure_quiz_access(db: Session, user: User, quiz: Quiz) -> Course:
    return ensure_course_access(db, user, quiz.course_id)