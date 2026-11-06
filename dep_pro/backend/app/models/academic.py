from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AcademicYear(Base):
    __tablename__ = "academic_years"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(32), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    semesters: Mapped[list["Semester"]] = relationship(back_populates="academic_year", cascade="all, delete-orphan")


class Semester(Base):
    __tablename__ = "semesters"

    id: Mapped[int] = mapped_column(primary_key=True)
    academic_year_id: Mapped[int] = mapped_column(ForeignKey("academic_years.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    starts_on: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_on: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(default=False)

    academic_year: Mapped["AcademicYear"] = relationship(back_populates="semesters")


class Section(Base):
    __tablename__ = "sections"
    __table_args__ = (UniqueConstraint("department_id", "name", "stage", name="uq_section_per_dept_stage"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    stage: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    department: Mapped["Department"] = relationship(back_populates="sections")
    members: Mapped[list["User"]] = relationship(back_populates="section", foreign_keys="User.section_id")
    enrollments: Mapped[list["Enrollment"]] = relationship(back_populates="section", cascade="all, delete-orphan")


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (UniqueConstraint("department_id", "code", name="uq_course_code_per_dept"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(32))
    name_ar: Mapped[str] = mapped_column(String(255))
    name_en: Mapped[str | None] = mapped_column(String(255))
    stage: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    department: Mapped["Department"] = relationship(back_populates="courses")
    instructors: Mapped[list["CourseInstructor"]] = relationship(back_populates="course", cascade="all, delete-orphan")
    enrollments: Mapped[list["Enrollment"]] = relationship(back_populates="course", cascade="all, delete-orphan")


class CourseInstructor(Base):
    __tablename__ = "course_instructors"
    __table_args__ = (UniqueConstraint("course_id", "instructor_id", name="uq_course_instructor"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    instructor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    is_primary: Mapped[bool] = mapped_column(default=True)

    course: Mapped["Course"] = relationship(back_populates="instructors")
    instructor: Mapped["User"] = relationship(back_populates="taught_courses")


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("section_id", "course_id", "semester_id", name="uq_enrollment"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id", ondelete="CASCADE"), index=True)

    section: Mapped["Section"] = relationship(back_populates="enrollments")
    course: Mapped["Course"] = relationship(back_populates="enrollments")