"""تصدير كل النماذج لضمان تسجيلها في Base.metadata قبل إنشاء الجداول أو تشغيل Alembic."""

from app.models.enums import (
    BroadcastScope,
    ChangeType,
    ClusterSource,
    GapAlertStatus,
    MaterialStatus,
    NotificationStatus,
    NotificationType,
    QuestionType,
    QuizStatus,
    RequestCategory,
    RequestStatus,
    RoutingStage,
    ScheduleSlotType,
    UserRole,
    Weekday,
)
from app.models.user import Department, User
from app.models.academic import (
    AcademicYear,
    Course,
    CourseInstructor,
    Enrollment,
    Section,
    Semester,
)
from app.models.schedule import (
    Absence,
    LectureOccurrence,
    MakeupSuggestion,
    Room,
    ScheduleChangeLog,
    TimeSlot,
    WeeklyScheduleEntry,
)
from app.models.rag import CourseMaterial, MaterialChunk
from app.models.learning import Quiz, QuizAnswer, QuizAttempt, QuizQuestion, StudentQuestion
from app.models.gaps import GapAlert, TopicCluster, TopicClusterMember
from app.models.requests import RequestBatch, RequestEvent, StudentRequest
from app.models.broadcast import Broadcast, BroadcastChannel, BroadcastRead
from app.models.notifications import Notification

__all__ = [
    "AcademicYear", "Absence", "BroadcastChannel", "Broadcast", "BroadcastRead",
    "BroadcastScope", "ChangeType", "ClusterSource", "Course", "CourseInstructor",
    "CourseMaterial", "Department", "Enrollment", "GapAlert", "GapAlertStatus",
    "LectureOccurrence", "MakeupSuggestion", "MaterialChunk", "MaterialStatus",
    "Notification", "NotificationStatus", "NotificationType", "QuestionType",
    "Quiz", "QuizAnswer", "QuizAttempt", "QuizQuestion", "QuizStatus", "Room",
    "RequestBatch", "RequestCategory", "RequestEvent", "RequestStatus", "RoutingStage",
    "ScheduleChangeLog", "ScheduleSlotType", "Section", "Semester", "StudentQuestion",
    "StudentRequest", "TimeSlot", "TopicCluster", "TopicClusterMember", "User",
    "UserRole", "Weekday", "WeeklyScheduleEntry",
]