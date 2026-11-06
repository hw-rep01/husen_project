from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "sdp",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.timezone,
    enable_utc=True,
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=True,
    beat_schedule={
        "gap-radar-nightly": {
            "task": "sdp.run_gap_radar",
            "schedule": crontab(hour=2, minute=0),
        },
        "plan-notifications-every-minute": {
            "task": "sdp.plan_notifications",
            "schedule": crontab(minute="*"),
        },
        "dispatch-notifications-every-minute": {
            "task": "sdp.dispatch_notifications",
            "schedule": crontab(minute="*"),
        },
    },
)