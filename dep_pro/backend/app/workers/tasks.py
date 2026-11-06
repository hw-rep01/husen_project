from app.db.session import SessionLocal
from app.services.common.timeutil import utc_now
from app.services.gaps.radar import run_radar_all_active
from app.services.notify.dispatch import (
    dispatch_due_notifications,
    plan_morning_digests,
    plan_pre_lecture_reminders,
)
from app.services.rag.ingestion import run_ingestion
from app.workers.celery_app import celery_app
from app.workers.locks import task_lock


@celery_app.task(name="sdp.ingest_material")
def ingest_material_task(material_id: int) -> str:
    db = SessionLocal()
    try:
        return run_ingestion(db, material_id)
    finally:
        db.close()


@celery_app.task(name="sdp.run_gap_radar")
def run_gap_radar_task() -> int:
    with task_lock("gap-radar", timeout=3600) as acquired:
        if not acquired:
            return -1
        db = SessionLocal()
        try:
            return len(run_radar_all_active(db))
        finally:
            db.close()


@celery_app.task(name="sdp.plan_notifications")
def plan_notifications_task() -> dict:
    with task_lock("plan-notifications", timeout=55) as acquired:
        if not acquired:
            return {"skipped": "locked"}
        db = SessionLocal()
        try:
            now = utc_now()
            reminders = plan_pre_lecture_reminders(db, now)
            digests = plan_morning_digests(db, now)
            db.commit()
            return {"reminders": reminders, "digests": digests}
        finally:
            db.close()


@celery_app.task(name="sdp.dispatch_notifications")
def dispatch_notifications_task() -> dict:
    with task_lock("dispatch-notifications", timeout=55) as acquired:
        if not acquired:
            return {"skipped": "locked"}
        db = SessionLocal()
        try:
            return dispatch_due_notifications(db, utc_now())
        finally:
            db.close()