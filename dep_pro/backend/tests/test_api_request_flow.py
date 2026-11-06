"""دورة حياة الطلب عبر الأدوار: الطالب ← ممثل الشعبة ← أستاذ المادة / مقرر ← رئيس القسم."""

from sqlalchemy import select

from app.models import Course, Enrollment, Room, Section, Semester, User


def _course_id(db):
    return db.scalar(select(Course.id).where(Course.code == "SE301"))


def _submit(client, auth, course_id=None, subject="طلب تجريبي", body="نص الطلب التجريبي الكامل"):
    response = client.post(
        "/api/requests",
        headers=auth("student"),
        json={"course_id": course_id, "subject": subject, "body": body},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_student_sees_own_request_after_submit(client, auth, db):
    created = _submit(client, auth, _course_id(db), subject="تأجيل كويز الاختبار")
    assert created["status"] == "in_section_review"
    assert created["current_stage"] == "class_representative"
    mine = client.get("/api/requests/mine", headers=auth("student")).json()
    assert any(r["id"] == created["id"] for r in mine)


def test_academic_request_full_path_to_instructor_approval(client, auth, db):
    course_id = _course_id(db)
    request = _submit(client, auth, course_id, subject="تأجيل كويز المتطلبات")

    # ممثل الشعبة يرى الطلب ويصنفه أكاديمياً
    section = client.get("/api/requests/section", headers=auth("rep")).json()
    assert any(u["id"] == request["id"] for u in section)
    classified = client.post(
        f"/api/requests/{request['id']}/classify",
        headers=auth("rep"),
        json={"category": "academic"},
    )
    assert classified.status_code == 200, classified.text
    assert classified.json()["category"] == "academic"

    # يُحال إلى أستاذ المادة مع اختيار المادة
    forwarded = client.post(
        f"/api/requests/{request['id']}/actions",
        headers=auth("rep"),
        json={"action": "forward", "course_id": course_id, "note": "للمراجعة"},
    )
    assert forwarded.status_code == 200, forwarded.text
    assert forwarded.json()["current_stage"] == "instructor"

    inbox = client.get("/api/requests/inbox", headers=auth("instructor")).json()
    assert any(u["id"] == request["id"] for u in inbox)

    decided = client.post(
        f"/api/requests/{request['id']}/actions",
        headers=auth("instructor"),
        json={"action": "approve", "note": "تمت الموافقة"},
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "approved"

    mine = next(r for r in client.get("/api/requests/mine", headers=auth("student")).json() if r["id"] == request["id"])
    assert mine["status"] == "approved"

    timeline = client.get(f"/api/requests/{request['id']}/timeline", headers=auth("student")).json()
    actions = [event["action"] for event in timeline]
    assert "submitted" in actions and "forwarded" in actions and "approve" in actions


def test_administrative_request_goes_through_coordinator_and_head(client, auth):
    request = _submit(client, auth, None, subject="مشكلة في القاعة", body="القاعة مغلقة صباحاً")
    assert client.post(
        f"/api/requests/{request['id']}/classify", headers=auth("rep"), json={"category": "administrative"}
    ).status_code == 200

    assert client.post(
        f"/api/requests/{request['id']}/actions", headers=auth("rep"), json={"action": "forward"}
    ).json()["current_stage"] == "department_coordinator"

    coord_forward = client.post(
        f"/api/requests/{request['id']}/actions", headers=auth("coord"), json={"action": "forward"}
    )
    assert coord_forward.status_code == 200, coord_forward.text
    assert coord_forward.json()["current_stage"] == "department_head"
    assert coord_forward.json()["status"] == "in_review"

    head_decision = client.post(
        f"/api/requests/{request['id']}/actions", headers=auth("head"), json={"action": "approve"}
    )
    assert head_decision.status_code == 200, head_decision.text
    assert head_decision.json()["status"] == "approved"

    # بعد الإغلاق لا تُقبل أي إجراءات جديدة
    closed = client.post(
        f"/api/requests/{request['id']}/actions", headers=auth("head"), json={"action": "reject"}
    )
    assert closed.status_code == 400


def test_student_cannot_classify_or_forward(client, auth):
    request = _submit(client, auth, None, subject="طلب إداري آخر", body="نص كاف لطلب إداري آخر")
    denied = client.post(
        f"/api/requests/{request['id']}/classify", headers=auth("student"), json={"category": "academic"}
    )
    assert denied.status_code == 403

    # الطالب لا يملك إجراء الإحالة حتى بعد التصنيف، بل يُرفض على مستوى الدور
    client.post(f"/api/requests/{request['id']}/classify", headers=auth("rep"), json={"category": "administrative"})
    forward = client.post(f"/api/requests/{request['id']}/actions", headers=auth("student"), json={"action": "forward"})
    assert forward.status_code == 403


def test_coordinator_cannot_classify_student_request(client, auth):
    request = _submit(client, auth, None, subject="طلب للتصنيف فقط", body="نص يكفي لطلب تجريبي")
    response = client.post(
        f"/api/requests/{request['id']}/classify", headers=auth("coord"), json={"category": "administrative"}
    )
    assert response.status_code == 403


def test_representative_cannot_approve_academic_request(client, auth, db):
    request = _submit(client, auth, _course_id(db), subject="طلب أكاديمي للرفض", body="نص كاف لطلب أكاديمي")
    client.post(f"/api/requests/{request['id']}/classify", headers=auth("rep"), json={"category": "academic"})
    response = client.post(
        f"/api/requests/{request['id']}/actions", headers=auth("rep"), json={"action": "approve"}
    )
    assert response.status_code == 400


def test_coordinator_cannot_view_academic_request_timeline(client, auth, db):
    request = _submit(client, auth, _course_id(db), subject="سجل أكاديمي خاص", body="نص كاف لطلب أكاديمي")
    response = client.get(f"/api/requests/{request['id']}/timeline", headers=auth("coord"))
    assert response.status_code == 403


def test_similar_requests_merge_into_one_batch(client, auth, db):
    first = _submit(client, auth, None, subject="طلب موحد للتجربة", body="نطلب تمديد فترة التسجيل قليلاً")
    second = _submit(client, auth, None, subject="طلب موحد للتجربة", body="نطلب تمديد فترة التسجيل قليلاً")
    client.post(f"/api/requests/{first['id']}/classify", headers=auth("rep"), json={"category": "administrative"})
    response = client.post(
        f"/api/requests/{second['id']}/classify", headers=auth("rep"), json={"category": "administrative"}
    )
    assert response.status_code == 200, response.text

    section = client.get("/api/requests/section", headers=auth("rep")).json()
    batches = [u for u in section if u["kind"] == "batch"]
    assert len(batches) == 1
    assert batches[0]["request_count"] == 2

    batch_id = batches[0]["id"]
    forwarded = client.post(f"/api/batches/{batch_id}/actions", headers=auth("rep"), json={"action": "forward"})
    assert forwarded.status_code == 200, forwarded.text
    assert forwarded.json()["current_stage"] == "department_coordinator"


def test_stale_token_of_other_account_gets_403_not_silent_success(client, auth):
    """يثبت أن الخادم يطبّق الصلاحيات على الحساب الذي يرسل الرمز فعلاً."""
    request = _submit(client, auth, None, subject="طلب لفحص الصلاحيات", body="نص كاف لفحص الصلاحيات")
    response = client.post(
        f"/api/requests/{request['id']}/classify", headers=auth("student"), json={"category": "administrative"}
    )
    assert response.status_code == 403
    assert "صلاحية" in response.json()["detail"]
