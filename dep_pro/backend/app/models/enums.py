import enum


class UserRole(str, enum.Enum):
    STUDENT = "student"
    CLASS_REPRESENTATIVE = "class_representative"
    INSTRUCTOR = "instructor"
    DEPARTMENT_COORDINATOR = "department_coordinator"
    DEPARTMENT_HEAD = "department_head"


class RequestCategory(str, enum.Enum):
    ACADEMIC = "academic"
    ADMINISTRATIVE = "administrative"


class RequestStatus(str, enum.Enum):
    SUBMITTED = "submitted"
    IN_SECTION_REVIEW = "in_section_review"
    MERGED = "merged"
    FORWARDED = "forwarded"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    RESOLVED = "resolved"
    CLOSED = "closed"


class RoutingStage(str, enum.Enum):
    CLASS_REPRESENTATIVE = "class_representative"
    INSTRUCTOR = "instructor"
    DEPARTMENT_COORDINATOR = "department_coordinator"
    DEPARTMENT_HEAD = "department_head"


class ScheduleSlotType(str, enum.Enum):
    REGULAR = "regular"
    MAKEUP = "makeup"
    POSTPONED = "postponed"
    CANCELLED = "cancelled"


class ChangeType(str, enum.Enum):
    ROOM_CHANGE = "room_change"
    TIME_CHANGE = "time_change"
    POSTPONEMENT = "postponement"
    CANCELLATION = "cancellation"
    MAKEUP_ADDED = "makeup_added"


class MaterialStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class QuestionType(str, enum.Enum):
    MCQ = "mcq"
    TRUE_FALSE = "true_false"


class QuizStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"


class ClusterSource(str, enum.Enum):
    STUDENT_QUESTION = "student_question"
    QUIZ_MISTAKE = "quiz_mistake"


class GapAlertStatus(str, enum.Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class BroadcastScope(str, enum.Enum):
    DEPARTMENT = "department"
    COURSE = "course"


class NotificationType(str, enum.Enum):
    MORNING_DIGEST = "morning_digest"
    PRE_LECTURE_REMINDER = "pre_lecture_reminder"
    SCHEDULE_CHANGE = "schedule_change"
    BROADCAST = "broadcast"
    REQUEST_UPDATE = "request_update"
    GAP_ALERT = "gap_alert"


class NotificationStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Weekday(int, enum.Enum):
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6