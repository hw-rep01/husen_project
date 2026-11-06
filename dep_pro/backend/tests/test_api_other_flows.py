"""الكويزات، رادار الفجوات، التبليغات، الجدول، والإشعارات عبر الـ API."""

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select

from app.models import (
    Course,
    Enrollment,
    LectureOccurrence,
    Quiz,
    QuizQuestion,
    QuizStatus,
    Room,
    Semester,
    StudentQuestion,
    TimeSlot,
    User,
    UserRole,
)
from app.services.common.timeutil import local_today, local_to_utc
from app.services.notify.dispatch import dispatch_due_notifications
from app.services.common.timeutil import utc_now


def _course(db):
    return db.scalar(select(Course).where(Course.code == "SE301"))


def _user(db, email):
    return db.scalar(select(User).where(User.email == email))


# ---------- الكويزات ----------

def _create_draft_quiz(db, course, instructor):
    quiz = Quiz(course_id=course.id, created_by_user_id=instructor.id, title="كويز تجريبي", status=QuizStatus.DRAFT)
    db.add(quiz)
    db.flush()
    db.add(
        QuizQuestion(
            quiz_id=quiz.id,
            position=0,
            question_type="mcq",
            question_text="ما المتجه المرجح؟",
            options=["خيار أ", "خيار ب", "خيار ج", "خيار د"],
            correct_option_index=1,
            explanation="الدليل من الملزمة",
        )
    )
    db.commit()
    return quiz


def test_quiz_publish_hides_answers_from_student_and_scores_attempt(client, auth, db):
    quiz = _create_draft_quiz(db, _course(db), _user(db, "dr@sdp.local"))

    published = client.post(f"/api/quizzes/{quiz.id}/publish", headers=auth("instructor"), json={})
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"

    as_student = client.get(f"/api/quizzes/{quiz.id}", headers=auth("student")).json()
    assert as_student["questions"][0]["correct_option_index"] is None
    assert as_student["questions"][0]["explanation"] is None

    question_id = as_student["questions"][0]["id"]
    attempt = client.post(
        f"/api/quizzes/{quiz.id}/attempts", headers=auth("student"), json={"answers": {str(question_id): 1}}
    )
    assert attempt.status_code == 200, attempt.text
    assert attempt.json()["score"] == 100.0

    again = client.post(
        f"/api/quizzes/{quiz.id}/attempts", headers=auth("student"), json={"answers": {str(question_id): 1}}
    )
    assert again.status_code == 400


def test_student_cannot_create_or_publish_quiz(client, auth, db):
    course = _course(db)
    response = client.post(
        f"/api/courses/{course.id}/quizzes", headers=auth("student"), json={"title": "محاولة", "question_count": 3}
    )
    assert response.status_code == 403


def test_quiz_closed_for_attempts_after_deadline(client, auth, db):
    quiz = _create_draft_quiz(db, _course(db), _user(db, "dr@sdp.local"))
    past = datetime.now(timezone.utc) - timedelta(days=2)
    client.post(
        f"/api/quizzes/{quiz.id}/publish",
        headers=auth("instructor"),
        json={"opens_at": (past - timedelta(days=1)).isoformat(), "closes_at": past.isoformat()},
    )
    question_id = client.get(f"/api/quizzes/{quiz.id}", headers=auth("instructor")).json()["questions"][0]["id"]
    response = client.post(
        f"/api/quizzes/{quiz.id}/attempts", headers=auth("student"), json={"answers": {str(question_id): 0}}
    )
    assert response.status_code == 400


# ---------- رادار الفجوات ----------

def test_gap_radar_raises_alert_when_most_of_section_struggles(client, auth, db):
    course = _course(db)
    semester = db.scalar(select(Semester).where(Semester.is_active.is_(True)))
    section_id = db.scalar(select(Enrollment.section_id).where(Enrollment.course_id == course.id))
    vector = [1.0] + [0.0] * 383
    for email in ("student@sdp.local", "rep@sdp.local"):
        user = _user(db, email)
        db.add(
            StudentQuestion(
                student_id=user.id,
                course_id=course.id,
                section_id=section_id,
                question_text="ما الفرق بين المتطلبات الوظيفية وغير الوظيفية؟",
                was_grounded=True,
                embedding=vector,
                created_at=datetime(2026, 10, 10, tzinfo=timezone.utc),
            )
        )
    db.commit()

    run = client.post(f"/api/courses/{course.id}/gaps/run", headers=auth("instructor"))
    assert run.status_code == 200, run.text
    assert run.json()["alerts_created"] >= 1

    alerts = client.get(f"/api/courses/{course.id}/gaps", headers=auth("instructor")).json()
    assert alerts and alerts[0]["affected_ratio"] > 0.3

    ack = client.post(f"/api/gaps/{alerts[0]['id']}/acknowledge", headers=auth("instructor"))
    assert ack.status_code == 200
    assert ack.json()["status"] == "acknowledged"


def test_gap_alerts_are_private_to_the_instructor(client, auth, db):
    course = _course(db)
    response = client.get(f"/api/courses/{course.id}/gaps", headers=auth("student"))
    assert response.status_code == 403


# ---------- التبليغات والإشعارات ----------

def test_broadcast_read_counter_counts_each_student_once(client, auth, db):
    response = client.post(
        "/api/broadcasts",
        headers=auth("coord"),
        json={"scope": "department", "title": "تعميم للقسم", "body": "يرجى مراجعة الجدول الجديد"},
    )
    assert response.status_code == 201, response.text
    broadcast = response.json()
    assert broadcast["audience_count"] >= 2

    first = client.post(f"/api/broadcasts/{broadcast['id']}/read", headers=auth("student"))
    assert first.status_code == 200
    client.post(f"/api/broadcasts/{broadcast['id']}/read", headers=auth("student"))
    refreshed = client.get("/api/broadcasts", headers=auth("student")).json()
    row = next(b for b in refreshed if b["id"] == broadcast["id"])
    assert row["seen_count"] == 1

    readers = client.get(f"/api/broadcasts/{broadcast['id']}/readers", headers=auth("coord")).json()
    assert [r["full_name"] for r in readers] == ["طالب تجريبي"]


def test_student_cannot_read_readers_list(client, auth, db):
    broadcast = client.get("/api/broadcasts", headers=auth("student")).json()[0]
    response = client.get(f"/api/broadcasts/{broadcast['id']}/readers", headers=auth("student"))
    assert response.status_code == 403


def test_broadcast_notification_is_delivered_to_student_inbox(client, auth, db):
    client.post(
        "/api/broadcasts",
        headers=auth("coord"),
        json={"scope": "department", "title": "تبليغ للتسليم", "body": "نص التبليغ للتسليم"},
    )
    dispatch_due_notifications(db, utc_now())
    titles = [n["title"] for n in client.get("/api/notifications/mine", headers=auth("student")).json()]
    assert any("تبليغ للتسليم" in t for t in titles)


def test_instructor_broadcast_is_scoped_to_course(client, auth, db):
    course = _course(db)
    response = client.post(
        "/api/broadcasts",
        headers=auth("instructor"),
        json={"scope": "course", "course_id": course.id, "title": "تبليغ المادة", "body": "موعد المحاضرة القادمة"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["channel_name"].startswith("تبليغات مادة")


# ---------- الجدول والتغييرات والتعويض ----------

def _occurrence(db, day, hour=8):
    course_enrollment = db.scalar(select(Enrollment).join(Course).where(Course.code == "SE301"))
    room = db.scalar(select(Room).where(Room.code == "B-203"))
    occ = LectureOccurrence(
        enrollment_id=course_enrollment.id,
        occurrence_date=day,
        starts_at=local_to_utc(day, time(hour, 0)),
        ends_at=local_to_utc(day, time(hour + 1, 30)),
        room_id=room.id,
    )
    db.add(occ)
    db.commit()
    return occ


def test_student_sees_lecture_and_instructor_changes_room(client, auth, db):
    day = local_today() + timedelta(days=3)
    occ = _occurrence(db, day)
    db.add(Room(department_id=_user(db, "dr@sdp.local").department_id, code="B-101", capacity=40, is_available=True))
    db.commit()
    room2 = db.scalar(select(Room).where(Room.code == "B-101"))

    week = client.get(f"/api/schedule/week?day={day.isoformat()}", headers=auth("student")).json()
    assert any(row["id"] == occ.id for row in week)

    changed = client.post(
        f"/api/schedule/occurrences/{occ.id}/room", headers=auth("instructor"), json={"room_id": room2.id}
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["room_code"] == "B-101"

    changes = client.get("/api/schedule/changes?after_id=0", headers=auth("student")).json()
    assert any(c["occurrence_id"] == occ.id and c["change_type"] == "room_change" for c in changes)


def test_postponement_then_makeup_suggestion_is_accepted(client, auth, db):
    day = local_today() + timedelta(days=4)
    occ = _occurrence(db, day, hour=10)
    enrollment_id = occ.enrollment_id

    postponed = client.post(
        f"/api/schedule/occurrences/{occ.id}/cancel",
        headers=auth("instructor"),
        json={"as_postponement": True, "note": "ظرف طارئ"},
    )
    assert postponed.status_code == 200, postponed.text
    assert postponed.json()["slot_type"] == "postponed"

    suggestions = client.post(
        "/api/schedule/makeup/suggest",
        headers=auth("instructor"),
        json={"enrollment_id": enrollment_id, "from_date": (local_today() + timedelta(days=1)).isoformat(),
              "days_ahead": 14, "limit": 5},
    )
    assert suggestions.status_code == 200, suggestions.text
    options = suggestions.json()
    assert options, "يجب أن يقترح النظام موعداً فارغاً"
    assert all(o["room_code"] for o in options)

    accepted = client.post(f"/api/schedule/makeup/suggestions/{options[0]['id']}/accept", headers=auth("instructor"))
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["slot_type"] == "makeup"

    again = client.post(f"/api/schedule/makeup/suggestions/{options[0]['id']}/accept", headers=auth("instructor"))
    assert again.status_code == 400


def test_student_cannot_edit_schedule(client, auth, db):
    occ = _occurrence(db, local_today() + timedelta(days=5), hour=12)
    response = client.post(f"/api/schedule/occurrences/{occ.id}/cancel", headers=auth("student"), json={})
    assert response.status_code == 403


def test_schedule_conflict_is_rejected_with_reason(client, auth, db):
    day = local_today() + timedelta(days=6)
    first = _occurrence(db, day, hour=14)
    second = _occurrence(db, day, hour=16)
    slot = TimeSlot(starts_at=time(14, 0), ends_at=time(15, 30), label="14:00-15:30")
    db.add(slot)
    db.commit()
    # نقل المحاضرة الثانية إلى الفترة نفسها للمحاضرة الأولى في القاعة نفسها: يجب أن يُرفض
    response = client.post(
        f"/api/schedule/occurrences/{second.id}/reschedule",
        headers=auth("instructor"),
        json={"new_date": day.isoformat(), "time_slot_id": slot.id, "room_id": first.room_id},
    )
    assert response.status_code == 400, response.text
    assert "القاعة" in response.json()["detail"] or "الشعبة" in response.json()["detail"]


def test_rooms_endpoint_lists_available_rooms(client, auth):
    rooms = client.get("/api/rooms", headers=auth("instructor")).json()
    assert any(r["code"] == "B-203" for r in rooms)


def test_courses_endpoint_returns_course_for_student_and_instructor(client, auth):
    for role in ("student", "instructor", "rep"):
        codes = [c["code"] for c in client.get("/api/courses", headers=auth(role)).json()]
        assert "SE301" in codes, role
