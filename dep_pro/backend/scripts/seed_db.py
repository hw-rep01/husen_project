from datetime import datetime, time, timezone

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import (
    AcademicYear,
    Course,
    CourseInstructor,
    Department,
    Enrollment,
    Room,
    Section,
    Semester,
    TimeSlot,
    User,
    UserRole,
)


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()
    try:
        if db.query(Department).count() > 0:
            print("Database already seeded.")
            return

        dept = Department(name_ar="قسم هندسة البرمجيات", name_en="Software Engineering", code="SE")
        db.add(dept)
        db.flush()

        year = AcademicYear(label="2026-2027")
        db.add(year)
        db.flush()

        semester = Semester(
            academic_year_id=year.id,
            name="الأول",
            starts_on=datetime(2026, 9, 1, tzinfo=timezone.utc),
            ends_on=datetime(2027, 1, 15, tzinfo=timezone.utc),
            is_active=True,
        )
        db.add(semester)

        section = Section(department_id=dept.id, name="أ", stage=2)
        db.add(section)
        db.flush()

        head = User(full_name="رئيس القسم", email="head@sdp.local",
                    password_hash=hash_password("ChangeMe123!"), role=UserRole.DEPARTMENT_HEAD,
                    department_id=dept.id)
        coord = User(full_name="مقرر القسم", email="coord@sdp.local",
                     password_hash=hash_password("ChangeMe123!"), role=UserRole.DEPARTMENT_COORDINATOR,
                     department_id=dept.id)
        instructor = User(full_name="د. أستاذ المادة", email="dr@sdp.local",
                          password_hash=hash_password("ChangeMe123!"), role=UserRole.INSTRUCTOR,
                          department_id=dept.id)
        rep = User(full_name="ممثل الشعبة", email="rep@sdp.local",
                   password_hash=hash_password("ChangeMe123!"), role=UserRole.CLASS_REPRESENTATIVE,
                   department_id=dept.id, section_id=section.id)
        student = User(full_name="طالب تجريبي", email="student@sdp.local",
                       password_hash=hash_password("ChangeMe123!"), role=UserRole.STUDENT,
                       department_id=dept.id, section_id=section.id)
        db.add_all([head, coord, instructor, rep, student])
        db.flush()

        dept.head_user_id = head.id
        dept.coordinator_user_id = coord.id

        course = Course(department_id=dept.id, code="SE301", name_ar="هندسة المتطلبات",
                        name_en="Requirements Engineering", stage=2)
        db.add(course)
        db.flush()

        db.add(CourseInstructor(course_id=course.id, instructor_id=instructor.id, is_primary=True))
        db.add(Enrollment(section_id=section.id, course_id=course.id, semester_id=semester.id))

        db.add(Room(department_id=dept.id, code="B-203", name="قاعة 203", capacity=60))
        db.add(TimeSlot(starts_at=time(8, 0), ends_at=time(9, 30), label="08:00-09:30"))

        db.commit()
        print("Seed completed.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()